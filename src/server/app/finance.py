"""Finance API — the department's read/write surface for the UI.

Why this exists
===============

The ledger and personal-finance tools are agent-callable, which makes them
reachable *only* by asking the agent in chat. That is the wrong interface for
"show me my trial balance": it costs a model round-trip to render data the
database can return directly, and it makes the numbers non-reproducible — two
identical questions can produce two slightly different renderings.

So this router reads the same tables the tools write. It does not re-implement
any arithmetic: every figure it returns comes from
``services/finance/ledger.py`` / ``services/finance/personal.py``, the same
modules the tools use. The single-source rule matters more here than anywhere —
a UI that computes net worth slightly differently from the agent produces two
"official" numbers, and users have no way to tell which is right.

Read-only by design. Writes go through the agent, because the *validation* is
the point: an HTTP POST that skipped ``JournalEntry.validate_against`` would be
a hole straight through the balance invariant. A UI that needs to create an
entry asks the agent to, and gets the same rejection messages a human
accountant would.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from src.server.database import ledger as ledger_db
from src.server.database import personal_finance as pf_db
from src.server.services.finance.ledger import from_cents, trial_balance
from src.server.services.finance.personal import (
    emergency_fund_months,
    monthly_essential_from,
)
from src.server.utils.api import CurrentUserId
from src.server.utils.error_sanitization import sanitize_error_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/finance", tags=["Finance"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"日期格式无效：{value!r}，应为 YYYY-MM-DD"
        ) from exc


def _dec(cents: int, currency: str) -> float:
    """Decimal → float, for JSON.

    A deliberate narrowing at the API boundary: ``Decimal`` is not
    JSON-serialisable, and the exactness matters for *storage and
    accumulation*, not for one value on its way to a chart. Every number the
    client receives has already been accumulated at full precision server-side,
    and ``str``-ing it here would just push the parse into every consumer.
    """
    return float(from_cents(cents, currency))


@router.get("/accounts")
async def list_accounts(
    user_id: CurrentUserId,
    category: str | None = Query(None, description="资产/负债/权益/收入/费用"),
    include_inactive: bool = Query(False),
) -> dict:
    """The effective chart of accounts (built-ins plus this user's overrides)."""
    try:
        rows = await ledger_db.list_accounts(
            user_id, include_inactive=include_inactive
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("list_accounts failed: %s", exc)
        raise HTTPException(status_code=500, detail=sanitize_error_text(str(exc)))

    if category:
        rows = [r for r in rows if r["category"] == category]

    return {
        "count": len(rows),
        "accounts": [
            {
                "code": r["code"],
                "name": r["name"],
                "category": r["category"],
                "normal_balance": r["normal_balance"],
                "is_custom": bool(r.get("is_custom")),
                "is_active": bool(r.get("is_active", True)),
            }
            for r in rows
        ],
    }


@router.get("/entries")
async def list_entries(
    user_id: CurrentUserId,
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    account_code: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Journal entries with their lines, grouped per voucher."""
    try:
        rows = await ledger_db.list_entries(
            user_id,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            account_code=account_code,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("list_entries failed: %s", exc)
        raise HTTPException(status_code=500, detail=sanitize_error_text(str(exc)))

    grouped: dict[str, dict] = {}
    for row in rows:
        key = str(row["entry_id"])
        entry = grouped.setdefault(
            key,
            {
                "entry_id": key,
                "entry_date": str(row["entry_date"]),
                "memo": row["memo"],
                "source": row["source"],
                "lines": [],
            },
        )
        entry["lines"].append(
            {
                "account_code": row["account_code"],
                "direction": row["direction"],
                "amount": _dec(row["amount_minor"], "CNY"),
            }
        )

    return {"count": len(grouped), "entries": list(grouped.values())}


@router.get("/trial-balance")
async def get_trial_balance(
    user_id: CurrentUserId,
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    currency: str = Query("CNY"),
) -> dict:
    """Trial balance over a period, with the balance check surfaced as data."""
    try:
        entries = await ledger_db.load_entries_as_objects(
            user_id,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
        )
        chart = await ledger_db.load_chart(user_id)
        tb = trial_balance(entries, chart)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("trial_balance failed: %s", exc)
        raise HTTPException(status_code=500, detail=sanitize_error_text(str(exc)))

    return {
        "entry_count": len(entries),
        "is_balanced": tb.is_balanced,
        "total_debit": _dec(tb.total_debit_cents, currency),
        "total_credit": _dec(tb.total_credit_cents, currency),
        "rows": [
            {
                "account_code": r.account_code,
                "account_name": r.account_name,
                "debit": _dec(r.debit_cents, currency),
                "credit": _dec(r.credit_cents, currency),
            }
            for r in tb.rows
        ],
    }


@router.get("/personal/balance-sheet")
async def get_personal_balance_sheet(user_id: CurrentUserId) -> dict:
    """Latest personal balance sheet, recomputed from stored components."""
    try:
        row = await pf_db.get_latest_snapshot(user_id, "balance_sheet")
    except Exception as exc:  # noqa: BLE001
        logger.error("get_personal_balance_sheet failed: %s", exc)
        raise HTTPException(status_code=500, detail=sanitize_error_text(str(exc)))

    if row is None:
        return {"has_data": False}

    sheet = pf_db.balance_sheet_from_row(row)
    currency = row.get("currency") or "CNY"
    ratio = sheet.debt_to_asset_ratio
    return {
        "has_data": True,
        "as_of": str(sheet.as_of),
        "currency": currency,
        "total_assets": _dec(sheet.total_assets_cents, currency),
        "liquid_assets": _dec(sheet.liquid_assets_cents, currency),
        "total_liabilities": _dec(sheet.total_liabilities_cents, currency),
        "net_worth": _dec(sheet.net_worth_cents, currency),
        "debt_to_asset_ratio": float(ratio) if ratio is not None else None,
        "assets": [
            {
                "key": a.key,
                "label": a.label,
                "amount": _dec(a.amount_cents, currency),
                "liquid": a.liquid,
            }
            for a in sorted(sheet.assets, key=lambda x: -x.amount_cents)
        ],
        "liabilities": [
            {
                "key": li.key,
                "label": li.label,
                "amount": _dec(li.amount_cents, currency),
                "monthly_payment": (
                    _dec(li.monthly_payment_cents, currency)
                    if li.monthly_payment_cents
                    else None
                ),
            }
            for li in sorted(sheet.liabilities, key=lambda x: -x.amount_cents)
        ],
    }


@router.get("/personal/cash-flow")
async def get_personal_cash_flow(user_id: CurrentUserId) -> dict:
    """Latest personal cash flow, plus emergency-fund coverage if a balance
    sheet exists.

    The two are returned together rather than from two endpoints because
    "months of runway" is the number people actually want and it needs both —
    making the client stitch them invites a client that stitches them
    *differently*.
    """
    try:
        flow_row = await pf_db.get_latest_snapshot(user_id, "cash_flow")
    except Exception as exc:  # noqa: BLE001
        logger.error("get_personal_cash_flow failed: %s", exc)
        raise HTTPException(status_code=500, detail=sanitize_error_text(str(exc)))

    if flow_row is None:
        return {"has_data": False}

    statement = pf_db.cash_flow_from_row(flow_row)
    currency = flow_row.get("currency") or "CNY"
    rate = statement.savings_rate

    essential = monthly_essential_from(statement)
    payload: dict = {
        "has_data": True,
        "start": str(statement.start),
        "end": str(statement.end),
        "days": (statement.end - statement.start).days + 1,
        "currency": currency,
        "income": _dec(statement.income_cents, currency),
        "fixed": _dec(statement.fixed_cents, currency),
        "living": _dec(statement.living_cents, currency),
        "discretionary": _dec(statement.discretionary_cents, currency),
        "savings": _dec(statement.savings_cents, currency),
        "debt_service": _dec(statement.debt_service_cents, currency),
        "total_outflow": _dec(statement.total_outflow_cents, currency),
        "net": _dec(statement.net_cents, currency),
        "savings_rate": float(rate) if rate is not None else None,
        "is_deficit": statement.is_deficit,
        "monthly_essential": _dec(essential, currency),
        "items": [
            {
                "category": i.category,
                "label": i.label,
                "amount": _dec(i.amount_cents, currency),
            }
            for i in statement.items
        ],
        "emergency_fund_months": None,
    }

    try:
        bs_row = await pf_db.get_latest_snapshot(user_id, "balance_sheet")
    except Exception:  # noqa: BLE001
        bs_row = None
    if bs_row is not None:
        sheet = pf_db.balance_sheet_from_row(bs_row)
        months = emergency_fund_months(sheet.liquid_assets_cents, essential)
        payload["emergency_fund_months"] = (
            float(months) if months is not None else None
        )

    return payload


@router.get("/snapshots")
async def list_snapshots(
    user_id: CurrentUserId,
    kind: str | None = Query(None, description="balance_sheet / cash_flow"),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """Snapshot history, for a net-worth-over-time chart."""
    if kind and kind not in ("balance_sheet", "cash_flow"):
        raise HTTPException(
            status_code=422, detail="kind 必须是 'balance_sheet' 或 'cash_flow'"
        )
    try:
        rows = await pf_db.list_snapshots(user_id, kind=kind, limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.error("list_snapshots failed: %s", exc)
        raise HTTPException(status_code=500, detail=sanitize_error_text(str(exc)))

    out = []
    for row in rows:
        currency = row.get("currency") or "CNY"
        item = {
            "snapshot_id": str(row["snapshot_id"]),
            "kind": row["kind"],
            "period_start": str(row["period_start"]),
            "period_end": str(row["period_end"]),
            "currency": currency,
            "note": row["note"],
        }
        if row["kind"] == "balance_sheet":
            sheet = pf_db.balance_sheet_from_row(row)
            item.update(
                {
                    "net_worth": _dec(sheet.net_worth_cents, currency),
                    "total_assets": _dec(sheet.total_assets_cents, currency),
                    "total_liabilities": _dec(
                        sheet.total_liabilities_cents, currency
                    ),
                }
            )
        else:
            statement = pf_db.cash_flow_from_row(row)
            rate = statement.savings_rate
            item.update(
                {
                    "income": _dec(statement.income_cents, currency),
                    "net": _dec(statement.net_cents, currency),
                    "savings_rate": float(rate) if rate is not None else None,
                }
            )
        out.append(item)

    return {"count": len(out), "snapshots": out}
