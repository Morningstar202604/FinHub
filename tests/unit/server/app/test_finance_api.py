"""Tests for the Finance API router (src/server/app/finance.py).

The point of these is not that the endpoints return 200 — it is that they
return the *same* numbers the service layer computes, and that they say
"no data" instead of guessing when there is none.

That last one is the whole reason the finance package exists. An endpoint that
reports a net worth of 0 when nothing has been recorded is worse than one that
fails: the user cannot tell "I have no money" from "I never told you."
"""

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import create_test_app

DB = "src.server.app.finance"


@pytest_asyncio.fixture
async def client():
    from src.server.app.finance import router

    app = create_test_app(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _asset(key, label, amount_minor, liquid):
    return {
        "side": "asset",
        "key": key,
        "label": label,
        "amount_minor": amount_minor,
        "liquid": liquid,
    }


def _liability(key, label, amount_minor, monthly=None):
    return {
        "side": "liability",
        "key": key,
        "label": label,
        "amount_minor": amount_minor,
        "monthly_payment_minor": monthly,
    }


def _bs_row(items, *, as_of="2026-09-14", currency="CNY"):
    d = date.fromisoformat(as_of)
    return {
        "snapshot_id": "s1",
        "kind": "balance_sheet",
        "period_start": d,
        "period_end": d,
        "currency": currency,
        "note": "",
        "items": items,
        "created_at": None,
    }


def _flow_row(items, *, start="2026-08-15", end="2026-09-13", currency="CNY"):
    return {
        "snapshot_id": "s2",
        "kind": "cash_flow",
        "period_start": date.fromisoformat(start),
        "period_end": date.fromisoformat(end),
        "currency": currency,
        "note": "",
        "items": items,
        "created_at": None,
    }


# ── chart of accounts ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_accounts(client, monkeypatch):
    rows = [
        {
            "code": "1001",
            "name": "库存现金",
            "category": "资产",
            "normal_balance": "debit",
            "is_custom": False,
            "is_active": True,
        },
        {
            "code": "2202",
            "name": "应付账款",
            "category": "负债",
            "normal_balance": "credit",
            "is_custom": False,
            "is_active": True,
        },
    ]

    async def fake(user_id, include_inactive=False):
        return rows

    monkeypatch.setattr(f"{DB}.ledger_db.list_accounts", fake)
    resp = await client.get("/api/v1/finance/accounts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["accounts"][0]["code"] == "1001"


@pytest.mark.asyncio
async def test_list_accounts_filters_by_category(client, monkeypatch):
    async def fake(user_id, include_inactive=False):
        return [
            {
                "code": "1001",
                "name": "库存现金",
                "category": "资产",
                "normal_balance": "debit",
                "is_custom": False,
                "is_active": True,
            },
            {
                "code": "2202",
                "name": "应付账款",
                "category": "负债",
                "normal_balance": "credit",
                "is_custom": False,
                "is_active": True,
            },
        ]

    monkeypatch.setattr(f"{DB}.ledger_db.list_accounts", fake)
    resp = await client.get("/api/v1/finance/accounts", params={"category": "负债"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["accounts"][0]["code"] == "2202"


# ── journal entries / trial balance ──────────────────────────────────────


@pytest.mark.asyncio
async def test_list_entries_groups_lines_under_their_voucher(client, monkeypatch):
    """Lines must arrive grouped: a flat join result would make a 3-line
    voucher read as three separate one-line entries."""

    async def fake(user_id, **kwargs):
        return [
            {
                "entry_id": "e1",
                "entry_date": date(2026, 9, 14),
                "memo": "销售商品",
                "source": "agent",
                "account_code": "1122",
                "direction": "debit",
                "amount_minor": 1_130_000,
                "line_no": 0,
            },
            {
                "entry_id": "e1",
                "entry_date": date(2026, 9, 14),
                "memo": "销售商品",
                "source": "agent",
                "account_code": "6001",
                "direction": "credit",
                "amount_minor": 1_000_000,
                "line_no": 1,
            },
            {
                "entry_id": "e1",
                "entry_date": date(2026, 9, 14),
                "memo": "销售商品",
                "source": "agent",
                "account_code": "2221001",
                "direction": "credit",
                "amount_minor": 130_000,
                "line_no": 2,
            },
        ]

    monkeypatch.setattr(f"{DB}.ledger_db.list_entries", fake)
    resp = await client.get("/api/v1/finance/entries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    entry = body["entries"][0]
    assert len(entry["lines"]) == 3
    assert entry["lines"][0]["amount"] == 11300.0


@pytest.mark.asyncio
async def test_trial_balance_reports_the_balance_flag(client, monkeypatch):
    from src.server.services.finance.ledger import (
        Account,
        ChartOfAccounts,
        JournalEntry,
        trial_balance as tb_fn,
    )

    chart = ChartOfAccounts()
    chart.add(Account("1122", "应收账款", "资产", "debit"))
    chart.add(Account("6001", "主营业务收入", "收入", "credit"))
    entry = JournalEntry(entry_date=date(2026, 9, 14), memo="x")
    entry.add("1122", "debit", 1_000_000)
    entry.add("6001", "credit", 1_000_000)
    expected = tb_fn([entry], chart)

    async def fake_entries(user_id, **kwargs):
        return [entry]

    async def fake_chart(user_id):
        return chart

    monkeypatch.setattr(f"{DB}.ledger_db.load_entries_as_objects", fake_entries)
    monkeypatch.setattr(f"{DB}.ledger_db.load_chart", fake_chart)

    resp = await client.get("/api/v1/finance/trial-balance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_balanced"] is True
    assert body["total_debit"] == float(expected.total_debit_cents) / 100
    assert body["total_credit"] == float(expected.total_credit_cents) / 100


@pytest.mark.asyncio
async def test_bad_date_is_422_not_500(client):
    resp = await client.get(
        "/api/v1/finance/entries", params={"start_date": "2026/09/14"}
    )
    assert resp.status_code == 422
    assert "YYYY-MM-DD" in resp.json()["detail"]


# ── personal: balance sheet ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_balance_sheet_without_data_says_so(client, monkeypatch):
    """Must not render as zero net worth."""

    async def fake(user_id, kind):
        return None

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/balance-sheet")
    assert resp.status_code == 200
    assert resp.json() == {"has_data": False}


@pytest.mark.asyncio
async def test_balance_sheet_excludes_illiquid_from_liquid(client, monkeypatch):
    row = _bs_row(
        [
            _asset("cash", "活期", 8_500_000, True),
            _asset("property", "自住房", 350_000_000, False),
        ],
        # no liabilities
    )

    async def fake(user_id, kind):
        return row

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/balance-sheet")
    body = resp.json()
    assert body["total_assets"] == 3_585_000.0
    assert body["liquid_assets"] == 85_000.0
    assert body["net_worth"] == 3_585_000.0
    # The house must be present but flagged, not silently dropped.
    house = next(a for a in body["assets"] if a["key"] == "property")
    assert house["liquid"] is False


@pytest.mark.asyncio
async def test_balance_sheet_computes_ratio_and_net_worth(client, monkeypatch):
    row = _bs_row(
        [
            _asset("cash", "活期", 8_500_000, True),
            _asset("investment", "基金", 15_000_000, True),
            _asset("property", "自住房", 350_000_000, False),
        ],
        # included below
    )
    row["items"].append(_liability("mortgage", "房贷", 180_000_000, 980_000))

    async def fake(user_id, kind):
        return row

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/balance-sheet")
    body = resp.json()
    assert body["net_worth"] == 1_935_000.0  # 3,735,000 − 1,800,000
    assert body["debt_to_asset_ratio"] == pytest.approx(0.4819, abs=1e-4)
    mortgage = body["liabilities"][0]
    assert mortgage["monthly_payment"] == 9800.0


@pytest.mark.asyncio
async def test_ratio_is_null_when_there_are_no_assets(client, monkeypatch):
    """Zero assets must not divide by zero — and must not report 0.0, which
    would read as a real (and alarming) 0% debt ratio."""
    row = _bs_row([], as_of="2026-09-14")
    row["items"] = [_liability("loan", "消费贷", 500_000)]

    async def fake(user_id, kind):
        return row

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/balance-sheet")
    assert resp.json()["debt_to_asset_ratio"] is None


# ── personal: cash flow ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cash_flow_without_data_says_so(client, monkeypatch):
    async def fake(user_id, kind):
        return None

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/cash-flow")
    assert resp.status_code == 200
    assert resp.json() == {"has_data": False}


@pytest.mark.asyncio
async def test_cash_flow_savings_rate_matches_the_service(client, monkeypatch):
    flow = _flow_row(
        [
            {"category": "收入", "label": "工资", "amount_minor": 3_500_000},
            {"category": "固定支出", "label": "房贷", "amount_minor": 1_100_000},
            {"category": "生活支出", "label": "餐饮", "amount_minor": 600_000},
            {"category": "可选支出", "label": "娱乐", "amount_minor": 300_000},
            {"category": "储蓄投资", "label": "定投", "amount_minor": 500_000},
        ]
    )

    async def fake_latest(user_id, kind):
        return flow if kind == "cash_flow" else None

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake_latest)
    resp = await client.get("/api/v1/finance/personal/cash-flow")
    body = resp.json()
    assert body["income"] == 35000.0
    assert body["net"] == 10000.0
    # 42.86%, NOT 28.57% — the investment transfer is saving, not spending.
    assert body["savings_rate"] == pytest.approx(0.4286, abs=1e-4)
    assert body["monthly_essential"] == 17000.0
    assert body["emergency_fund_months"] is None  # no balance sheet recorded


@pytest.mark.asyncio
async def test_emergency_months_use_liquid_assets(client, monkeypatch):
    flow = _flow_row(
        [
            {"category": "收入", "label": "工资", "amount_minor": 3_500_000},
            {"category": "固定支出", "label": "房贷", "amount_minor": 1_100_000},
            {"category": "生活支出", "label": "餐饮", "amount_minor": 600_000},
        ]
    )
    bs = _bs_row(
        [
            _asset("cash", "活期", 23_500_000, True),
            _asset("property", "自住房", 350_000_000, False),
        ]
    )

    async def fake(user_id, kind):
        return flow if kind == "cash_flow" else bs

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/cash-flow")
    body = resp.json()
    # 235,000 / 17,000 = 13.8. Counting the house would give ~219.6.
    assert body["emergency_fund_months"] == 13.8


@pytest.mark.asyncio
async def test_longer_period_is_annualised_by_days(client, monkeypatch):
    """A quarter read as a month overstates essentials ~3x."""
    flow = _flow_row(
        [
            {"category": "收入", "label": "工资", "amount_minor": 9_000_000},
            {"category": "固定支出", "label": "房贷", "amount_minor": 3_000_000},
            {"category": "生活支出", "label": "餐饮", "amount_minor": 3_000_000},
        ],
        start="2026-07-01",
        end="2026-09-30",  # 92 days
    )

    async def fake(user_id, kind):
        return flow if kind == "cash_flow" else None

    monkeypatch.setattr(f"{DB}.pf_db.get_latest_snapshot", fake)
    resp = await client.get("/api/v1/finance/personal/cash-flow")
    body = resp.json()
    assert body["days"] == 92
    # 60,000 over 92 days → 19,565.22/month
    assert body["monthly_essential"] == pytest.approx(19_565.22, abs=0.01)


# ── snapshots ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_snapshots_reject_an_unknown_kind(client):
    resp = await client.get(
        "/api/v1/finance/snapshots", params={"kind": "portfolio"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_snapshots_summarise_each_kind(client, monkeypatch):
    bs = _bs_row([_asset("cash", "活期", 1_000_000, True)])
    flow = _flow_row(
        [{"category": "收入", "label": "工资", "amount_minor": 3_500_000}]
    )

    async def fake(user_id, **kwargs):
        return [bs, flow]

    monkeypatch.setattr(f"{DB}.pf_db.list_snapshots", fake)
    resp = await client.get("/api/v1/finance/snapshots")
    body = resp.json()
    assert body["count"] == 2
    assert body["snapshots"][0]["net_worth"] == 10_000.0
    assert body["snapshots"][1]["savings_rate"] == pytest.approx(1.0)
