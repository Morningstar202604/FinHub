"""The ledger is the one table where a SQL injection is indistinguishable from
fraud, so its write path is pinned here.

Two properties matter more than the rest:

1. every value reaches the driver as a *parameter*, never spliced into the
   statement — tested with an actual injection payload as the memo;
2. the balance rule is enforced in Python *before* the write, so an unbalanced
   entry never reaches the database at all.

The DB trigger is the second line of defence; the CheckViolation case below
pins what happens when it fires anyway.
"""

from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import psycopg
import pytest

from src.server.database import ledger as ledger_db
from src.server.services.finance.ledger import (
    Account,
    JournalEntry,
    LedgerError,
)

USER = "11111111-1111-1111-1111-111111111111"
# A payload, not a decoration: if this string ever appears inside a SQL
# statement rather than in the parameter tuple, the guard failed.
INJECTION = "'; DROP TABLE ledger_entries; --"


def _balanced(memo: str = "收到投资款") -> JournalEntry:
    entry = JournalEntry(entry_date=dt.date(2026, 1, 5), memo=memo)
    entry.add("1001", "debit", 100_00)     # 库存现金
    entry.add("4001", "credit", 100_00)    # 实收资本
    return entry


def _cursor(*, execute_side_effect=None, fetchall_return=None):
    cursor = AsyncMock()
    cursor.execute = AsyncMock(side_effect=execute_side_effect)
    cursor.executemany = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=fetchall_return or [])
    cursor.rowcount = 1
    return cursor


@asynccontextmanager
async def _fake_pool(cursor):
    """Stand in for ``get_db_connection``: one connection, one cursor."""
    conn = AsyncMock()

    @asynccontextmanager
    async def _cur(**_kwargs):
        yield cursor

    conn.cursor = _cur
    yield conn


def _patched(cursor):
    return patch(
        "src.server.database.ledger.get_db_connection",
        lambda: _fake_pool(cursor),
    )


def _writes(cursor):
    """Only the statements that mutate the ledger.

    ``insert_entry`` reads the chart first, so a plain ``assert_not_awaited``
    can never hold; what must not happen is the INSERT.
    """
    return [c for c in cursor.execute.await_args_list if "INSERT" in c.args[0]]


def _raise_on_insert(exc: Exception):
    """Fail the INSERT only, so the preceding chart read still succeeds."""

    async def _execute(sql, params=None):
        if "INSERT" in sql:
            raise exc

    return _execute


# ---------------------------------------------------------------------------
# Parameterisation — the fraud boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_injection_payload_in_the_memo_reaches_the_driver_as_a_parameter():
    """Nothing user-supplied may be spliced into the statement."""
    cursor = _cursor()
    with _patched(cursor):
        await ledger_db.insert_entry(USER, _balanced(memo=INJECTION))

    sql, params = cursor.execute.await_args.args
    assert INJECTION not in sql
    assert INJECTION in params
    assert "%s" in sql


@pytest.mark.asyncio
async def test_every_write_passes_a_parameter_tuple():
    """A statement with no placeholders and no params is the failure shape."""
    cursor = _cursor()
    with _patched(cursor):
        await ledger_db.insert_entry(USER, _balanced())

    for call in cursor.execute.await_args_list:
        sql, params = call.args
        assert params, f"statement executed without parameters: {sql}"


@pytest.mark.asyncio
async def test_delete_is_scoped_by_user_id():
    """An entry id alone must not be enough to delete someone else's row."""
    cursor = _cursor()
    with _patched(cursor):
        assert await ledger_db.delete_entry(USER, "some-entry-id") is True

    sql, params = cursor.execute.await_args.args
    assert "user_id" in sql
    assert params == ("some-entry-id", USER)


@pytest.mark.asyncio
async def test_delete_reports_whether_a_row_went():
    """rowcount 0 means the id was wrong or belonged to another user."""
    cursor = _cursor()
    cursor.rowcount = 0
    with _patched(cursor):
        assert await ledger_db.delete_entry(USER, "not-mine") is False


# ---------------------------------------------------------------------------
# Validation happens before the write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unbalanced_entry_never_reaches_the_database():
    entry = JournalEntry(entry_date=dt.date(2026, 1, 5), memo="漏记税额")
    entry.add("1001", "debit", 100_00)
    entry.add("4001", "credit", 90_00)

    cursor = _cursor()
    with _patched(cursor), pytest.raises(LedgerError, match="不平衡"):
        await ledger_db.insert_entry(USER, entry)

    assert _writes(cursor) == []
    cursor.executemany.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unknown_account_is_refused_before_the_write():
    entry = JournalEntry(entry_date=dt.date(2026, 1, 5), memo="科目写错")
    entry.add("9999", "debit", 100_00)
    entry.add("4001", "credit", 100_00)

    cursor = _cursor()
    with _patched(cursor), pytest.raises(LedgerError, match="不在科目表中"):
        await ledger_db.insert_entry(USER, entry)

    assert _writes(cursor) == []


# ---------------------------------------------------------------------------
# Driver errors become domain errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_duplicate_idempotency_key_is_not_a_validation_failure():
    """The remedy differs: stop retrying, rather than fix the entry."""
    cursor = _cursor(
        execute_side_effect=_raise_on_insert(psycopg.errors.UniqueViolation("dup"))
    )
    with _patched(cursor), pytest.raises(
        ledger_db.DuplicateEntryError, match="已存在"
    ):
        await ledger_db.insert_entry(USER, _balanced(), idempotency_key="k-1")


@pytest.mark.asyncio
async def test_the_db_trigger_rejection_surfaces_as_a_ledger_error():
    """The trigger fired on something the kernel allowed — a bug or schema
    drift, so it must not be presented to the user as their mistake."""
    cursor = _cursor(
        execute_side_effect=_raise_on_insert(psycopg.errors.CheckViolation("balance"))
    )
    with _patched(cursor), pytest.raises(LedgerError, match="数据库拒绝"):
        await ledger_db.insert_entry(USER, _balanced())


# ---------------------------------------------------------------------------
# Shape of the write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lines_are_numbered_from_zero_in_order():
    entry = JournalEntry(entry_date=dt.date(2026, 1, 5), memo="三行分录")
    entry.add("1001", "debit", 60_00)
    entry.add("6602", "debit", 40_00)
    entry.add("1002", "credit", 100_00)

    cursor = _cursor()
    with _patched(cursor):
        await ledger_db.insert_entry(USER, entry)

    _sql, rows = cursor.executemany.await_args.args
    assert [row[4] for row in rows] == [0, 1, 2]
    assert [row[1] for row in rows] == ["1001", "6602", "1002"]


@pytest.mark.asyncio
async def test_a_supplied_entry_id_is_honoured():
    import uuid

    fixed = uuid.uuid4()
    cursor = _cursor()
    with _patched(cursor):
        assert await ledger_db.insert_entry(USER, _balanced(), entry_id=fixed) == fixed


# ---------------------------------------------------------------------------
# The effective chart: user accounts shadow built-ins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_user_account_shadows_the_builtin_of_the_same_code():
    """If they redefine 1001 with another normal balance, theirs must win —
    otherwise every entry they book validates against rules they didn't choose."""
    cursor = _cursor(
        fetchall_return=[
            {
                "code": "1001",
                "name": "我的现金",
                "category": "资产",
                "normal_balance": "credit",  # deliberately unconventional
            }
        ]
    )
    with _patched(cursor):
        chart = await ledger_db.load_chart(USER)

    assert chart.get("1001").name == "我的现金"
    assert chart.get("1001").normal_balance == "credit"


@pytest.mark.asyncio
async def test_load_chart_without_a_user_is_the_pure_builtin_chart():
    """No user, no query: the built-in CAS chart must not need a round trip."""
    cursor = _cursor()
    with _patched(cursor):
        chart = await ledger_db.load_chart(None)

    assert chart.has("1001")
    cursor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_account_parameterises_the_user_id():
    cursor = _cursor()
    with _patched(cursor):
        await ledger_db.upsert_account(
            USER, Account("1001", "库存现金", "资产", "debit")
        )

    sql, params = cursor.execute.await_args.args
    assert USER in params
    assert "INSERT INTO ledger_accounts" in sql
