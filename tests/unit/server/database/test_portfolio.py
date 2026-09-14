"""Portfolio writes are tenant-scoped, and merges are arithmetic.

Two things here are worth more than the rest:

1. **every statement carries ``user_id``** — a holding id alone must never be
   enough to read, change or delete someone else's position. That is the whole
   ownership model, and it is easy to lose one clause in a refactor;
2. **the merge's weighted average cost** — buying more of a position at a
   different price must not silently keep the old cost basis, because every
   unrealised P&L number downstream is computed from it.
"""

from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.server.database import portfolio

ALICE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
BOB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
HOLDING = "hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh"


def _cursor(*, fetchone_return=None, fetchall_return=None):
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=fetchone_return)
    cursor.fetchall = AsyncMock(return_value=fetchall_return or [])
    cursor.rowcount = 1
    return cursor


@asynccontextmanager
async def _fake_pool(cursor):
    conn = AsyncMock()

    @asynccontextmanager
    async def _cur(**_kwargs):
        yield cursor

    conn.cursor = _cur

    @asynccontextmanager
    async def _tx():
        yield

    conn.transaction = _tx
    yield conn


def _patched(cursor):
    return patch(
        "src.server.database.portfolio.get_db_connection",
        lambda: _fake_pool(cursor),
    )


def _statements(cursor):
    return [c.args[0] for c in cursor.execute.await_args_list]


def _params(cursor):
    return [c.args[1] for c in cursor.execute.await_args_list]


# ---------------------------------------------------------------------------
# Tenant scoping — the ownership model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reading_one_holding_is_scoped_by_user():
    cursor = _cursor(fetchone_return={"user_portfolio_id": HOLDING})
    with _patched(cursor):
        await portfolio.get_portfolio_holding(HOLDING, ALICE)

    sql, params = cursor.execute.await_args.args
    assert "user_id = %s" in sql
    assert params == (HOLDING, ALICE)


@pytest.mark.asyncio
async def test_deleting_is_scoped_by_user():
    cursor = _cursor()
    with _patched(cursor):
        assert await portfolio.delete_portfolio_holding(HOLDING, ALICE) is True

    sql, params = cursor.execute.await_args.args
    assert "user_id = %s" in sql
    assert params == (HOLDING, ALICE)


@pytest.mark.asyncio
async def test_deleting_another_users_holding_deletes_nothing():
    """rowcount 0 is how "not yours" is reported — not an exception, not a hit."""
    cursor = _cursor()
    cursor.rowcount = 0
    with _patched(cursor):
        assert await portfolio.delete_portfolio_holding(HOLDING, BOB) is False


@pytest.mark.asyncio
async def test_an_update_that_changes_nothing_does_not_write():
    """A no-field update would be an UPDATE with an empty SET; it reads instead."""
    cursor = _cursor(fetchone_return={"user_portfolio_id": HOLDING})
    with _patched(cursor):
        row = await portfolio.update_portfolio_holding(HOLDING, ALICE)

    assert row == {"user_portfolio_id": HOLDING}
    assert all("UPDATE" not in s for s in _statements(cursor))


@pytest.mark.asyncio
async def test_a_real_update_still_carries_the_owner():
    cursor = _cursor(fetchone_return={"user_portfolio_id": HOLDING})
    with _patched(cursor):
        await portfolio.update_portfolio_holding(HOLDING, ALICE, quantity=Decimal("5"))

    updates = [s for s in _statements(cursor) if "UPDATE" in s]
    assert updates, "expected an UPDATE to be issued"
    assert "user_id = %s" in updates[0]
    assert ALICE in _params(cursor)[-1]


# ---------------------------------------------------------------------------
# Merge arithmetic
# ---------------------------------------------------------------------------


def _existing(qty: str, cost: str | None):
    return {
        "user_portfolio_id": HOLDING,
        "user_id": ALICE,
        "quantity": Decimal(qty),
        "average_cost": Decimal(cost) if cost is not None else None,
        "name": "旧名字",
        "notes": "旧备注",
        "first_purchased_at": dt.datetime(2026, 1, 1),
    }


@pytest.mark.asyncio
async def test_merging_reweights_the_cost_basis():
    """10 @ 100 then 10 @ 200 is 20 @ 150 — not 20 @ 100."""
    cursor = _cursor(fetchone_return=_existing("10", "100"))
    with _patched(cursor):
        _row, details = await portfolio.upsert_portfolio_holding(
            ALICE, "AAPL", "stock", Decimal("10"), average_cost=Decimal("200")
        )

    assert details is not None
    assert details["result"]["quantity"] == "20"
    assert details["result"]["average_cost"] == "150"


@pytest.mark.asyncio
async def test_the_merge_locks_the_row_against_a_concurrent_merge():
    """Two simultaneous buys of the same symbol must not both read-then-write."""
    cursor = _cursor(fetchone_return=_existing("10", "100"))
    with _patched(cursor):
        await portfolio.upsert_portfolio_holding(
            ALICE, "AAPL", "stock", Decimal("10"), average_cost=Decimal("200")
        )

    assert any("FOR UPDATE" in s for s in _statements(cursor))


@pytest.mark.asyncio
async def test_the_earlier_purchase_date_wins():
    """first_purchased_at is a fact about the position, not the latest lot."""
    cursor = _cursor(fetchone_return=_existing("10", "100"))
    with _patched(cursor):
        await portfolio.upsert_portfolio_holding(
            ALICE,
            "AAPL",
            "stock",
            Decimal("10"),
            average_cost=Decimal("200"),
            first_purchased_at=dt.datetime(2025, 6, 1),
        )

    update_call = [c for c in cursor.execute.await_args_list if "UPDATE" in c.args[0]][-1]
    assert update_call.args[1][4] == dt.datetime(2025, 6, 1)


@pytest.mark.asyncio
async def test_closing_a_position_clears_the_cost_basis():
    """Quantity netting to zero has no meaningful average cost — carrying the
    old one forward would invent a basis for a position that no longer exists."""
    cursor = _cursor(fetchone_return=_existing("10", "100"))
    with _patched(cursor):
        _row, details = await portfolio.upsert_portfolio_holding(
            ALICE, "AAPL", "stock", Decimal("-10"), average_cost=Decimal("200")
        )

    assert details["result"]["quantity"] == "0"
    assert details["result"]["average_cost"] is None


@pytest.mark.asyncio
async def test_a_new_symbol_inserts_and_is_tagged_with_the_owner():
    cursor = _cursor()
    # First fetchone is the existence check (nothing there), second is the
    # INSERT ... RETURNING result.
    cursor.fetchone.side_effect = [None, {"user_portfolio_id": "new-holding"}]
    with _patched(cursor):
        _row, details = await portfolio.upsert_portfolio_holding(
            ALICE, "TSLA", "stock", Decimal("3"), average_cost=Decimal("250")
        )

    assert details is None, "a create is not a merge"
    insert = [c for c in cursor.execute.await_args_list if "INSERT" in c.args[0]][0]
    assert ALICE in insert.args[1]
