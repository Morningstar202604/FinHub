"""Personal finance primitives — net worth, cash flow, and savings rate.

Why this is separate from the B2B ledger
========================================

The ledger in ``ledger.py`` is deliberately enterprise-shaped: a chart of
accounts, VAT, period-end close. An individual does not keep a 科目余额表 and
does not need 应交增值税.

But the *arithmetic* is the same problem, and the failure mode is the same one
that motivated the ledger: a model asked "what's my net worth" without real
primitives will produce a confident number assembled from whatever it
remembers of the conversation. So personal finance gets its own primitives,
sharing the exact-arithmetic discipline (Decimal → integer minor units) but
with a personal balance-sheet shape.

Asset/liability classification
------------------------------

The distinction that makes a personal balance sheet useful is **liquidity and
direction**, not instrument type:

* A house is an asset but not liquid — counting it in "available funds" is how
  people conclude they can afford things they cannot.
* A mortgage is a liability regardless of it being "secured by" the asset; net
  worth must subtract it.

So :class:`AssetClass` carries an explicit ``liquid`` flag rather than leaving
callers to infer liquidity from the class name, and liabilities are their own
type rather than negative assets. Sign conventions are where personal finance
maths silently goes wrong (a -300000 "asset" and a 300000 liability produce
the same net worth by accident but behave differently under every other
operation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from src.server.services.finance.ledger import from_cents

logger = logging.getLogger(__name__)


class FinanceError(ValueError):
    """Raised when a personal-finance computation is given incoherent input."""


# Consumption-heavy categories are split out because they are the ones a
# budget actually acts on; merging them into "其它" is what makes a cash-flow
# statement unactionable.
CashFlowCategory = Literal[
    "收入",
    "固定支出",
    "生活支出",
    "可选支出",
    "储蓄投资",
    "债务偿还",
]


@dataclass(frozen=True)
class AssetClass:
    """A kind of asset, with an explicit liquidity flag.

    ``liquid`` is stored rather than derived: whether 房产 counts as available
    funds is a judgement about *intent* (could you sell it this month?) that a
    name-based rule gets wrong as soon as someone holds REITs.
    """

    key: str
    label: str
    liquid: bool


DEFAULT_ASSET_CLASSES: tuple[AssetClass, ...] = (
    AssetClass("cash", "现金及活期", liquid=True),
    AssetClass("deposit", "定期存款", liquid=True),
    AssetClass("investment", "投资（股票/基金/理财）", liquid=True),
    AssetClass("receivable", "应收/借出款", liquid=False),
    AssetClass("property", "房产", liquid=False),
    AssetClass("vehicle", "车辆", liquid=False),
    AssetClass("other", "其他资产", liquid=False),
)


@dataclass
class Asset:
    key: str
    label: str
    amount_cents: int
    liquid: bool

    def __post_init__(self) -> None:
        if self.amount_cents < 0:
            raise FinanceError(
                f"资产 {self.label!r} 金额为负——资产应以正数记录，"
                "负债请用 Liability"
            )


@dataclass
class Liability:
    key: str
    label: str
    amount_cents: int
    # Optional: monthly minimum payment, so the report can say something about
    # debt service rather than just a stock figure.
    monthly_payment_cents: int | None = None

    def __post_init__(self) -> None:
        if self.amount_cents < 0:
            raise FinanceError(
                f"负债 {self.label!r} 金额为负——负债以正数记录，余额由类型表达"
            )


@dataclass
class BalanceSheet:
    """Assets and liabilities at a point in time."""

    as_of: date
    assets: list[Asset] = field(default_factory=list)
    liabilities: list[Liability] = field(default_factory=list)

    @property
    def total_assets_cents(self) -> int:
        return sum(a.amount_cents for a in self.assets)

    @property
    def total_liabilities_cents(self) -> int:
        return sum(li.amount_cents for li in self.liabilities)

    @property
    def net_worth_cents(self) -> int:
        return self.total_assets_cents - self.total_liabilities_cents

    @property
    def liquid_assets_cents(self) -> int:
        """Assets realisable within roughly a month.

        Offered separately from total assets on purpose: the common personal
        finance error is treating a house as spendable.
        """
        return sum(a.amount_cents for a in self.assets if a.liquid)

    @property
    def debt_to_asset_ratio(self) -> Decimal | None:
        """负数表示资不抵债；None 表示无资产可比（避免除零）。"""
        if self.total_assets_cents == 0:
            return None
        return (
            Decimal(self.total_liabilities_cents)
            / Decimal(self.total_assets_cents)
        ).quantize(Decimal("0.0001"))


@dataclass
class CashFlowItem:
    category: CashFlowCategory
    label: str
    amount_cents: int


@dataclass
class CashFlowStatement:
    """Income and outgo over a period."""

    start: date
    end: date
    items: list[CashFlowItem] = field(default_factory=list)

    def _sum(self, *categories: str) -> int:
        return sum(i.amount_cents for i in self.items if i.category in categories)

    @property
    def income_cents(self) -> int:
        return self._sum("收入")

    @property
    def fixed_cents(self) -> int:
        return self._sum("固定支出")

    @property
    def living_cents(self) -> int:
        return self._sum("生活支出")

    @property
    def discretionary_cents(self) -> int:
        return self._sum("可选支出")

    @property
    def savings_cents(self) -> int:
        return self._sum("储蓄投资")

    @property
    def debt_service_cents(self) -> int:
        return self._sum("债务偿还")

    @property
    def total_outflow_cents(self) -> int:
        return (
            self.fixed_cents
            + self.living_cents
            + self.discretionary_cents
            + self.savings_cents
            + self.debt_service_cents
        )

    @property
    def net_cents(self) -> int:
        """收入 − 全部流出。负数意味着在消耗存量。"""
        return self.income_cents - self.total_outflow_cents

    @property
    def savings_rate(self) -> Decimal | None:
        """储蓄率 = （收入 − 消费 − 偿债）/ 收入。

        Note what is *not* subtracted: 储蓄投资. A transfer into investments is
        the act of saving, not spending, so it must be excluded from the
        denominator's outflow — otherwise the deliberate saver is penalised
        relative to someone who merely left the cash in their account, and the
        two identical outcomes report different rates.

        ``net_cents`` deliberately *does* include 储蓄投资 in outflow (money did
        leave the current account), so this is computed independently rather
        than by adding ``savings_cents`` back onto ``net_cents`` — that
        addition double-counted the transfer.
        """
        if self.income_cents <= 0:
            return None
        saved = self.income_cents - (
            self.fixed_cents
            + self.living_cents
            + self.discretionary_cents
            + self.debt_service_cents
        )
        return (Decimal(saved) / Decimal(self.income_cents)).quantize(
            Decimal("0.0001")
        )

    @property
    def is_deficit(self) -> bool:
        return self.net_cents < 0


def emergency_fund_months(
    liquid_assets_cents: int,
    monthly_essential_cents: int,
) -> Decimal | None:
    """Months of essential spending the liquid assets cover.

    Uses *liquid* assets and *essential* (fixed + living) spending — not total
    assets and total spend. Including a house or discretionary spending makes
    the number reassuring and useless.
    """
    if monthly_essential_cents <= 0:
        return None
    return (
        Decimal(liquid_assets_cents) / Decimal(monthly_essential_cents)
    ).quantize(Decimal("0.1"))


def monthly_essential_from(statement: CashFlowStatement) -> int:
    """Essential monthly spend, normalised from a period statement.

    The period may not be a month, so the daily rate is extrapolated rather
    than assuming the caller passed 30 days — a quarter of spending read as a
    month overstates essentials ~3x.

    Quantised to whole minor units *then* cast, rather than ``int()`` on the
    raw Decimal: truncation turns an exact 10000.00 into 9999.99, which then
    propagates into the emergency-fund ratio as 6.0 → 5.9 months.
    """
    days = (statement.end - statement.start).days + 1
    if days <= 0:
        raise FinanceError("现金流区间无效：结束日期早于开始日期")
    essential = statement.fixed_cents + statement.living_cents
    monthly = (
        Decimal(essential) / Decimal(days) * Decimal(30)
    ).quantize(Decimal(1))
    return int(monthly)


def format_money(cents: int, currency: str = "CNY") -> str:
    """Thousands-separated rendering, for reports and tables."""
    value = from_cents(cents, currency)
    return f"{value:,.2f}"
