"""Database access for personal-finance snapshots (个人财务快照).

Layering note (same as ``database/ledger.py``): this module owns SQL and
nothing else. The arithmetic lives in ``services/finance/personal.py`` and is
never duplicated here — the DB stores ``BIGINT`` minor units and hands them
back untouched, so a balance sheet read from the database and one assembled in
memory produce identical numbers.

Why the items live in JSONB rather than a second table
======================================================

A journal entry line is a *fact* with its own identity — it can be filtered,
joined, and audited line by line, which is why the ledger gives lines their
own table. A personal-finance snapshot item is not that: it is a *stated
value* that belongs wholly to its snapshot and is meaningful only in
aggregate. There is no query of the form "show me every 房产 row across all
users" that a personal balance sheet needs to answer.

The ledger's balance invariant — the reason lines got a table — has no
analogue here: a balance sheet is not required to balance, so there is no
cross-row constraint to push into the database. A JSONB column therefore buys
the same durability with none of the schema surface, and keeps the snapshot
self-contained when read back.

Money is still integer minor units inside the JSON (``{"amount_minor": ...}``)
rather than decimal strings, so a JSON round-trip cannot reintroduce the
float drift the whole finance package exists to prevent.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection
from src.server.services.finance.personal import (
    DEFAULT_ASSET_CLASSES,
    Asset,
    BalanceSheet,
    CashFlowItem,
    CashFlowStatement,
    Liability,
)

logger = logging.getLogger(__name__)

SnapshotKind = Literal["balance_sheet", "cash_flow"]


async def save_snapshot(
    user_id: str,
    kind: SnapshotKind,
    *,
    period_start: date,
    period_end: date,
    items: list[dict[str, Any]],
    currency: str = "CNY",
    note: str = "",
    snapshot_id: UUID | None = None,
) -> UUID:
    """Persist one snapshot's items.

    ``period_start``/``period_end`` are both stored even for a point-in-time
    balance sheet (where they are equal): giving both kinds the same period
    columns means a "net worth over time" query is one index scan over one
    table rather than a UNION of two shapes.
    """
    sid = snapshot_id or uuid4()
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO personal_finance_snapshots
                    (snapshot_id, user_id, kind, period_start, period_end,
                     currency, note, items)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (sid, user_id, kind, period_start, period_end, currency, note, _to_json(items)),
            )
    return sid


async def list_snapshots(
    user_id: str,
    *,
    kind: SnapshotKind | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Snapshots newest first, each with its raw JSONB items."""
    limit = max(1, min(limit, 500))
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT snapshot_id, kind, period_start, period_end,
                       currency, note, items, created_at
                FROM personal_finance_snapshots
                WHERE user_id = %s
                  AND (%s::text IS NULL OR kind = %s::text)
                  AND (%s::date IS NULL OR period_end >= %s::date)
                  AND (%s::date IS NULL OR period_start <= %s::date)
                ORDER BY period_end DESC, created_at DESC
                LIMIT %s
                """,
                (
                    user_id,
                    kind, kind,
                    start_date, start_date,
                    end_date, end_date,
                    limit,
                ),
            )
            return [dict(row) for row in await cur.fetchall()]


async def get_latest_snapshot(
    user_id: str, kind: SnapshotKind
) -> dict[str, Any] | None:
    rows = await list_snapshots(user_id, kind=kind, limit=1)
    return rows[0] if rows else None


async def delete_snapshot(user_id: str, snapshot_id: str) -> bool:
    """Delete one snapshot. Scoped by user_id so an id alone is not enough."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM personal_finance_snapshots "
                "WHERE snapshot_id = %s AND user_id = %s",
                (snapshot_id, user_id),
            )
            return cur.rowcount > 0


# ── item <-> dataclass conversion ────────────────────────────────────────
# Snapshot rows store *stated values*, so unlike the ledger there is no
# validation invariant to re-run on read. These converters only undo the
# storage encoding; they deliberately do not "fix up" bad data, because a
# silently corrected net worth is worse than an obviously wrong one.


def items_from_balance_sheet(sheet: BalanceSheet) -> list[dict[str, Any]]:
    return [
        {
            "side": "asset",
            "key": a.key,
            "label": a.label,
            "amount_minor": a.amount_cents,
            "liquid": a.liquid,
        }
        for a in sheet.assets
    ] + [
        {
            "side": "liability",
            "key": li.key,
            "label": li.label,
            "amount_minor": li.amount_cents,
            "monthly_payment_minor": li.monthly_payment_cents,
        }
        for li in sheet.liabilities
    ]


def balance_sheet_from_row(row: dict[str, Any]) -> BalanceSheet:
    assets: list[Asset] = []
    liabilities: list[Liability] = []
    for item in row["items"] or []:
        if item.get("side") == "asset":
            assets.append(
                Asset(
                    key=item["key"],
                    label=item["label"],
                    amount_cents=int(item["amount_minor"]),
                    liquid=bool(item.get("liquid", False)),
                )
            )
        elif item.get("side") == "liability":
            monthly = item.get("monthly_payment_minor")
            liabilities.append(
                Liability(
                    key=item["key"],
                    label=item["label"],
                    amount_cents=int(item["amount_minor"]),
                    monthly_payment_cents=int(monthly) if monthly is not None else None,
                )
            )
    return BalanceSheet(
        as_of=row["period_end"], assets=assets, liabilities=liabilities
    )


def items_from_cash_flow(statement: CashFlowStatement) -> list[dict[str, Any]]:
    return [
        {
            "category": i.category,
            "label": i.label,
            "amount_minor": i.amount_cents,
        }
        for i in statement.items
    ]


def cash_flow_from_row(row: dict[str, Any]) -> CashFlowStatement:
    return CashFlowStatement(
        start=row["period_start"],
        end=row["period_end"],
        items=[
            CashFlowItem(
                category=item["category"],
                label=item["label"],
                amount_cents=int(item["amount_minor"]),
            )
            for item in row["items"] or []
        ],
    )


def _to_json(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False, default=str)


def asset_class_catalog() -> list[dict[str, Any]]:
    """The class keys the agent may use, with their liquidity semantics.

    Exposed so the tool layer can enumerate valid ``key`` values instead of
    rejecting them after the fact.
    """
    return [
        {"key": c.key, "label": c.label, "liquid": c.liquid}
        for c in DEFAULT_ASSET_CLASSES
    ]


def liquid_class_keys() -> tuple[str, ...]:
    """Asset-class keys that count as liquid, for the tool layer's hints."""
    return tuple(c.key for c in DEFAULT_ASSET_CLASSES if c.liquid)
