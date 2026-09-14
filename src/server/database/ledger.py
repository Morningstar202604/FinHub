"""Database access for the ledger (accounts + entries + lines).

Layering note: this module owns SQL and nothing else. Validation lives in
``services/finance/ledger.py`` and is *called* here before writes, so the
balance rule has one definition rather than two. The database repeats the
check as a deferred constraint trigger, which is deliberate redundancy — the
kernel is not the only conceivable writer, so the invariant belongs where no
writer can skip it.

Every write is parameterised. The ledger is the one table where a SQL
injection would be indistinguishable from fraud, so nothing here interpolates
a value into a statement.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection
from src.server.services.finance.ledger import (
    Account,
    ChartOfAccounts,
    JournalEntry,
    LedgerError,
    default_chart,
)

logger = logging.getLogger(__name__)


class DuplicateEntryError(Exception):
    """An entry with this idempotency key already exists.

    Separate from :class:`LedgerError` (a validation failure) because the
    caller's remedy differs entirely: a validation failure means "fix the
    entry", this means "you already booked it, stop retrying".
    """


async def load_chart(user_id: str | None) -> ChartOfAccounts:
    """Build the effective chart: the built-in CAS chart, shadowed per-code by
    any account this user has defined.

    Shadowing rather than merging matters — if a user redefines 6602 with a
    different normal balance, the user's definition must win, or every entry
    they book against it would validate against rules they didn't choose.
    """
    chart = default_chart()
    if user_id is None:
        return chart

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT code, name, category, normal_balance
                FROM ledger_accounts
                WHERE user_id = %s AND is_active = TRUE
                """,
                (user_id,),
            )
            for row in await cur.fetchall():
                chart.add(
                    Account(
                        code=row["code"],
                        name=row["name"],
                        category=row["category"],
                        normal_balance=row["normal_balance"],
                    )
                )
    return chart


async def upsert_account(user_id: str, account: Account) -> None:
    """Create or update a user-defined account."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO ledger_accounts
                    (user_id, code, name, category, normal_balance)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid), code)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    normal_balance = EXCLUDED.normal_balance,
                    updated_at = NOW()
                """,
                (user_id, account.code, account.name, account.category, account.normal_balance),
            )


async def list_accounts(user_id: str, include_inactive: bool = False) -> list[dict[str, Any]]:
    """The user's effective chart: built-ins plus their overrides, one row per code."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT DISTINCT ON (code)
                    code, name, category, normal_balance, is_active,
                    (user_id IS NOT NULL) AS is_custom
                FROM ledger_accounts
                WHERE (user_id IS NULL OR user_id = %s)
                  AND (%s OR is_active = TRUE)
                -- User rows win over built-ins for the same code.
                ORDER BY code, user_id NULLS LAST
                """,
                (user_id, include_inactive),
            )
            return [dict(row) for row in await cur.fetchall()]


async def insert_entry(
    user_id: str,
    entry: JournalEntry,
    *,
    source: str = "agent",
    idempotency_key: str | None = None,
    entry_id: UUID | None = None,
) -> UUID:
    """Validate then persist one journal entry in a single transaction.

    Validation runs here (not only in the tool layer) so any caller gets it.
    The DB trigger is the second line of defence, not the first — failing in
    Python produces a message naming the account or the imbalance, which is far
    more useful to a model than a plpgsql RAISE.

    Returns the entry id. Raises :class:`LedgerError` on a validation failure
    and :class:`DuplicateEntryError` when ``idempotency_key`` was already used.
    """
    chart = await load_chart(user_id)
    entry.validate_against(chart)

    eid = entry_id or uuid4()
    lines = [
        (eid, line.account_code, line.direction, line.amount_cents)
        for line in entry.lines
    ]

    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO ledger_entries
                        (entry_id, user_id, entry_date, memo, source, idempotency_key)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (eid, user_id, entry.entry_date, entry.memo, source, idempotency_key),
                )
                # executemany keeps the lines in one statement; the deferred
                # trigger fires at COMMIT, so the balance is checked once on
                # the complete entry rather than on a partial one.
                await cur.executemany(
                    """
                    INSERT INTO ledger_entry_lines
                        (entry_id, account_code, direction, amount_minor, line_no)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (line[0], line[1], line[2], line[3], idx)
                        for idx, line in enumerate(lines)
                    ],
                )
    except psycopg.errors.UniqueViolation as exc:
        raise DuplicateEntryError(
            f"幂等键 {idempotency_key!r} 已存在——该分录此前已入账，请勿重复提交"
        ) from exc
    except psycopg.errors.CheckViolation as exc:
        # The DB trigger rejected something the kernel let through. That is a
        # bug in the kernel or a schema drift, not a user error, so surface it
        # as a LedgerError carrying the DB's own message.
        raise LedgerError(f"数据库拒绝了该分录：{exc}") from exc

    return eid


async def list_entries(
    user_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    account_code: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Entries with their lines, newest first.

    Filters by account by joining lines — an entry matches if *any* of its
    lines touches that account, which is what a "show me 应付账款 activity"
    question actually means.
    """
    limit = max(1, min(limit, 1000))
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT
                    e.entry_id, e.entry_date, e.memo, e.source, e.created_at,
                    l.account_code, l.direction, l.amount_minor, l.line_no
                FROM ledger_entries e
                JOIN ledger_entry_lines l ON l.entry_id = e.entry_id
                WHERE e.user_id = %s
                  AND (%s::date IS NULL OR e.entry_date >= %s::date)
                  AND (%s::date IS NULL OR e.entry_date <= %s::date)
                  AND (
                        %s::text IS NULL
                        OR e.entry_id IN (
                            SELECT entry_id FROM ledger_entry_lines
                            WHERE account_code = %s::text
                        )
                  )
                ORDER BY e.entry_date DESC, e.created_at DESC, l.line_no ASC
                LIMIT %s
                """,
                (
                    user_id,
                    start_date, start_date,
                    end_date, end_date,
                    account_code, account_code,
                    limit,
                ),
            )
            return [dict(row) for row in await cur.fetchall()]


async def load_entries_as_objects(
    user_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[JournalEntry]:
    """Rehydrate stored rows into :class:`JournalEntry` objects for reporting.

    Grouping happens here rather than in SQL because the trial balance needs
    the same objects the kernel validates, and re-deriving them in a second
    shape is how two definitions of "an entry" start to drift.
    """
    rows = await list_entries(user_id, start_date=start_date, end_date=end_date, limit=1000)

    grouped: dict[str, JournalEntry] = {}
    for row in rows:
        key = str(row["entry_id"])
        entry = grouped.get(key)
        if entry is None:
            entry = JournalEntry(entry_date=row["entry_date"], memo=row["memo"] or "")
            grouped[key] = entry
        entry.lines.append(
            # Bypasses EntryLine.__post_init__ deliberately: these rows already
            # passed both the kernel and the DB trigger on the way in, and a
            # stored row that cannot be rehydrated would make the ledger
            # unreadable rather than safer.
            _RawLine(row["account_code"], row["direction"], row["amount_minor"])
        )

    return list(grouped.values())


class _RawLine:
    """Duck-typed line for rehydration (see load_entries_as_objects)."""

    __slots__ = ("account_code", "direction", "amount_cents")

    def __init__(self, account_code: str, direction: str, amount_cents: int) -> None:
        self.account_code = account_code
        self.direction = direction
        self.amount_cents = amount_cents


async def delete_entry(user_id: str, entry_id: str) -> bool:
    """Delete one entry. Scoped by user_id so an id alone is not sufficient."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM ledger_entries WHERE entry_id = %s AND user_id = %s",
                (entry_id, user_id),
            )
            return cur.rowcount > 0
