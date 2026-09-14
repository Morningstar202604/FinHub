"""Tests for personal finance primitives (net worth, cash flow, savings rate).

The cases worth having here are the ones where a plausible-looking number is
*wrong*: treating a house as spendable, counting a mortgage as anything other
than a subtraction, or extrapolating a quarter of spending into a month.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.server.services.finance.ledger import to_cents
from src.server.services.finance.personal import (
    Asset,
    BalanceSheet,
    CashFlowItem,
    CashFlowStatement,
    FinanceError,
    Liability,
    emergency_fund_months,
    format_money,
    monthly_essential_from,
)


def _cny(amount: str) -> int:
    return to_cents(amount, "CNY")


# ── balance sheet ─────────────────────────────────────────────────────────


class TestBalanceSheet:
    def test_net_worth_subtracts_liabilities(self):
        bs = BalanceSheet(
            as_of=date(2026, 9, 14),
            assets=[Asset("cash", "现金", _cny("500000"), liquid=True)],
            liabilities=[Liability("mortgage", "房贷", _cny("300000"))],
        )
        assert bs.net_worth_cents == _cny("200000")
        assert bs.total_assets_cents == _cny("500000")
        assert bs.total_liabilities_cents == _cny("300000")

    def test_liquid_excludes_illiquid_assets(self):
        """The house is the point: net worth is high, spendable cash is not.

        A report that only shows net worth invites the user to think they can
        afford things they cannot.
        """
        bs = BalanceSheet(
            as_of=date(2026, 9, 14),
            assets=[
                Asset("cash", "现金", _cny("50000"), liquid=True),
                Asset("property", "房产", _cny("3000000"), liquid=False),
            ],
        )
        assert bs.total_assets_cents == _cny("3050000")
        assert bs.liquid_assets_cents == _cny("50000")

    def test_negative_net_worth_is_reported_not_clamped(self):
        """资不抵债 must be visible, not floored at zero."""
        bs = BalanceSheet(
            as_of=date(2026, 9, 14),
            assets=[Asset("cash", "现金", _cny("10000"), liquid=True)],
            liabilities=[Liability("loan", "贷款", _cny("80000"))],
        )
        assert bs.net_worth_cents == _cny("-70000")

    def test_negative_asset_amount_is_rejected(self):
        with pytest.raises(FinanceError, match="资产应以正数记录"):
            Asset("cash", "现金", _cny("-100"), liquid=True)

    def test_debt_ratio_none_when_no_assets(self):
        """Guards the divide-by-zero that would otherwise raise mid-report."""
        bs = BalanceSheet(
            as_of=date(2026, 9, 14),
            liabilities=[Liability("loan", "贷款", _cny("5000"))],
        )
        assert bs.debt_to_asset_ratio is None

    def test_debt_ratio_computed_when_assets_present(self):
        bs = BalanceSheet(
            as_of=date(2026, 9, 14),
            assets=[Asset("cash", "现金", _cny("1000000"), liquid=True)],
            liabilities=[Liability("loan", "贷款", _cny("500000"))],
        )
        assert bs.debt_to_asset_ratio == Decimal("0.5000")


# ── cash flow ─────────────────────────────────────────────────────────────


def _statement(*items) -> CashFlowStatement:
    stmt = CashFlowStatement(start=date(2026, 9, 1), end=date(2026, 9, 30))
    for category, label, amount in items:
        stmt.items.append(CashFlowItem(category, label, _cny(amount)))
    return stmt


class TestCashFlow:
    def test_net_is_income_minus_all_outflow(self):
        stmt = _statement(
            ("收入", "工资", "30000"),
            ("固定支出", "房租", "8000"),
            ("生活支出", "餐饮", "3000"),
            ("可选支出", "娱乐", "2000"),
            ("储蓄投资", "基金定投", "5000"),
        )
        assert stmt.income_cents == _cny("30000")
        assert stmt.total_outflow_cents == _cny("18000")
        assert stmt.net_cents == _cny("12000")

    def test_deficit_is_detected(self):
        stmt = _statement(
            ("收入", "工资", "10000"),
            ("固定支出", "房租", "9000"),
            ("可选支出", "购物", "5000"),
        )
        assert stmt.is_deficit
        assert stmt.net_cents == _cny("-4000")

    def test_savings_rate_excludes_investment_transfers_from_outflow(self):
        """30000 income, 13000 consumed, 5000 invested -> 56.67%.

        储蓄投资 is the act of saving, not spending, so it must not be
        subtracted as outflow. The earlier implementation added
        ``savings_cents`` back onto ``net_cents`` while ``net_cents`` had
        already subtracted it, double-counting the transfer and reporting
        56.67% for a case whose true rate is 56.67% computed a different way
        and 16.67% computed a third — the bug was invisible without this case.
        """
        stmt = _statement(
            ("收入", "工资", "30000"),
            ("固定支出", "房租", "8000"),
            ("生活支出", "餐饮", "3000"),
            ("可选支出", "娱乐", "2000"),
            ("储蓄投资", "基金定投", "5000"),
        )
        assert stmt.savings_rate == Decimal("0.5667")

    def test_investing_and_hoarding_report_the_same_rate(self):
        """The invariant the double-count violated.

        Saving 3000 deliberately and simply not spending 3000 are the same
        outcome; a user comparing the two must not see different rates.
        """
        invested = _statement(
            ("收入", "工资", "10000"),
            ("储蓄投资", "定投", "3000"),
        )
        hoarded = _statement(("收入", "工资", "10000"))
        assert invested.savings_rate == hoarded.savings_rate == Decimal("1.0000")

    def test_savings_rate_none_without_income(self):
        stmt = _statement(("固定支出", "房租", "5000"))
        assert stmt.savings_rate is None

    def test_savings_rate_goes_negative_when_overspending(self):
        """A deficit month is a negative rate, not a silent floor at zero."""
        stmt = _statement(
            ("收入", "工资", "10000"),
            ("固定支出", "房租", "9000"),
            ("可选支出", "购物", "3000"),
        )
        assert stmt.savings_rate == Decimal("-0.2000")

    def test_debt_service_is_tracked_separately_from_spending(self):
        stmt = _statement(
            ("收入", "工资", "20000"),
            ("固定支出", "房租", "5000"),
            ("债务偿还", "房贷", "4000"),
        )
        assert stmt.debt_service_cents == _cny("4000")
        assert stmt.fixed_cents == _cny("5000")


# ── derived metrics ───────────────────────────────────────────────────────


class TestEmergencyFund:
    def test_months_from_liquid_assets(self):
        assert emergency_fund_months(_cny("60000"), _cny("10000")) == Decimal("6.0")

    def test_none_when_no_essential_spend(self):
        assert emergency_fund_months(_cny("60000"), 0) is None

    def test_partial_month_is_preserved(self):
        assert emergency_fund_months(_cny("15000"), _cny("10000")) == Decimal("1.5")


class TestMonthlyEssentials:
    def test_quarter_is_extrapolated_not_read_as_a_month(self):
        """A 90-day period with 30000 essentials is ~10000/month, not 30000.

        Normalising by the actual day count is what prevents a ~3x overstatement.
        """
        stmt = CashFlowStatement(start=date(2026, 7, 1), end=date(2026, 9, 28))
        stmt.items.append(CashFlowItem("固定支出", "房租", _cny("30000")))
        # 90 days inclusive -> 30000 / 90 * 30 = 10000
        assert monthly_essential_from(stmt) == _cny("10000")

    def test_inverted_range_is_rejected(self):
        stmt = CashFlowStatement(start=date(2026, 9, 30), end=date(2026, 9, 1))
        with pytest.raises(FinanceError, match="区间无效"):
            monthly_essential_from(stmt)

    def test_discretionary_spend_is_not_essential(self):
        stmt = CashFlowStatement(start=date(2026, 9, 1), end=date(2026, 9, 30))
        stmt.items.append(CashFlowItem("固定支出", "房租", _cny("8000")))
        stmt.items.append(CashFlowItem("可选支出", "旅游", _cny("20000")))
        # 8k essentials over 30 days -> 8k/month; the 20k trip is excluded.
        assert monthly_essential_from(stmt) == _cny("8000")


class TestFormatting:
    def test_thousands_separated(self):
        assert format_money(_cny("1234567.89")) == "1,234,567.89"

    def test_negative_renders_with_sign(self):
        assert format_money(_cny("-500.5")) == "-500.50"

    def test_zero(self):
        assert format_money(0) == "0.00"
