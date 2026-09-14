"""Ledger kernel — the accounting primitives the finance roles actually lack.

Why this module exists
======================

``agent_config.yaml`` already declares five finance roles (accountant,
treasury, tax-specialist, fp-analyst, internal-auditor) whose prompts promise
double-entry bookkeeping, journal entries and trial balances. But the tool set
those roles receive (``finance_tools`` in ``agent.py``) is entirely
*equity-market* tooling: SEC filings, quotes, OHLCV, options chains, a stock
screener. Not one accounting primitive.

The failure mode that creates is specific and worth naming: a model asked to
"book this invoice" with no ledger will produce a *plausible* journal entry,
because that is what the prompt asks for. It will cite accounts like 1122
应收账款 by pattern-matching, never checking whether the account exists, and
never proving the entry balances. The output reads correct and is unverifiable.

So the design rule here is: **the model proposes, this module disposes.** Every
number that reaches a user passes through integer-cent arithmetic and a
balance assertion first. Anything that fails is rejected loudly rather than
rendered into a report.

Money representation
--------------------

Amounts are carried as :class:`decimal.Decimal` and **never** as float. A
ledger is a system of record; ``0.1 + 0.2 != 0.3`` is not an acceptable
property for one. Summation goes through :func:`to_cents`, which converts to
integer minor units (分) before adding, so a trial balance totals exactly
rather than approximately.

This also handles the currency-subunit problem: JPY has no minor unit, so
``to_cents`` must not blindly multiply by 100. :data:`CURRENCY_EXPONENT` makes
the exponent explicit per currency instead of assuming the ISO-4217 default of
two.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Literal

logger = logging.getLogger(__name__)

# ISO-4217 minor-unit exponents. Absent → 2 (the common case). JPY and KRW
# have no minor unit; getting this wrong scales every amount by 100.
CURRENCY_EXPONENT: dict[str, int] = {
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "CLP": 0,
    "ISK": 0,
    "BHD": 3,
    "KWD": 3,
    "OMR": 3,
    "TND": 3,
}

Direction = Literal["debit", "credit"]


class LedgerError(ValueError):
    """Raised when a proposed entry violates the accounting model.

    A distinct type (not a bare ``ValueError``) so the tool layer can turn it
    into a structured, correctable message for the model rather than a 500.
    """


def currency_exponent(currency: str) -> int:
    return CURRENCY_EXPONENT.get(currency.upper(), 2)


def to_cents(amount: Decimal | int | str | float, currency: str = "CNY") -> int:
    """Convert an amount to integer minor units (分) for the currency.

    Accepts ``float`` only because JSON has no decimal type and a caller may
    hand us one; it is converted via ``str()`` first so we inherit the decimal
    value the caller *wrote* rather than the nearest binary approximation.
    ``Decimal(0.1)`` is 0.1000000000000000055511151231257827, and a ledger must
    not carry that.
    """
    if isinstance(amount, float):
        # Rounding at the JSON boundary is the caller's last chance to say what
        # they meant; do it once, explicitly, rather than accumulating drift.
        amount = Decimal(str(amount))
    elif not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    factor = Decimal(10) ** currency_exponent(currency)
    quantized = (amount * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(quantized)


def from_cents(cents: int, currency: str = "CNY") -> Decimal:
    """Inverse of :func:`to_cents`, exact by construction."""
    return (Decimal(cents) / (Decimal(10) ** currency_exponent(currency))).quantize(
        Decimal(1).scaleb(-currency_exponent(currency))
    )


@dataclass(frozen=True)
class Account:
    """A chart-of-accounts entry.

    ``normal_balance`` is what makes a trial balance interpretable: without it,
    a credit balance on 库存现金 is indistinguishable from a debit balance on
    应付账款 to a naive "sum the debits" check. Debits and credits are stored
    signed against the normal balance so the trial-balance total is a real
    invariant (see :func:`trial_balance`).
    """

    code: str
    name: str
    category: Literal["资产", "负债", "权益", "收入", "费用"]
    normal_balance: Direction


@dataclass
class EntryLine:
    """One side of a journal entry, in integer minor units."""

    account_code: str
    direction: Direction
    amount_cents: int

    def __post_init__(self) -> None:
        # A zero-amount line is almost always a bug in the caller (a tax line
        # computed as 0 on an exempt invoice, say) and it inflates the entry
        # without affecting it. Reject rather than silently carry it.
        if self.amount_cents == 0:
            raise LedgerError(
                f"分录行金额为 0（科目 {self.account_code}）——"
                "零金额行通常是上游计算错误，请检查该行是否应当存在"
            )
        if self.amount_cents < 0:
            raise LedgerError(
                f"分录行金额为负（科目 {self.account_code}）——"
                "借贷方向由 direction 表达，金额必须为正数"
            )


@dataclass
class JournalEntry:
    """A balanced (or to-be-validated) double-entry journal entry."""

    entry_date: date
    memo: str
    lines: list[EntryLine] = field(default_factory=list)

    def add(self, account_code: str, direction: Direction, amount_cents: int) -> None:
        self.lines.append(EntryLine(account_code, direction, amount_cents))

    def total_debit_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines if line.direction == "debit")

    def total_credit_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines if line.direction == "credit")

    def imbalance_cents(self) -> int:
        """Signed debit − credit. Zero means balanced."""
        return self.total_debit_cents() - self.total_credit_cents()

    def validate(self) -> None:
        """Raise :class:`LedgerError` unless the entry is bookable.

        Checks run in the order a human accountant would: is there anything to
        book, are the accounts real, does it balance. Each message names the
        specific offender so the model can repair its own output.
        """
        if not self.lines:
            raise LedgerError("分录为空——至少需要一借一贷两行")

        if len(self.lines) < 2:
            raise LedgerError(
                f"分录只有 {len(self.lines)} 行——复式记账要求至少一借一贷"
            )

        # Both sides present. An entry with only debits is the single most
        # common LLM bookkeeping error, and it balances from neither side.
        has_debit = any(line.direction == "debit" for line in self.lines)
        has_credit = any(line.direction == "credit" for line in self.lines)
        if not has_debit or not has_credit:
            missing = "贷方" if has_debit else "借方"
            raise LedgerError(f"分录缺少{missing}——复式记账的每一笔都必须有借有贷")

        imbalance = self.imbalance_cents()
        if imbalance != 0:
            raise LedgerError(
                f"分录不平衡：借方 {self.total_debit_cents()} 分 − "
                f"贷方 {self.total_credit_cents()} 分 = {imbalance} 分。"
                "请调整金额使借贷相等（差额通常是税额或含税/不含税口径混淆）"
            )

    def validate_against(self, chart: "ChartOfAccounts") -> None:
        """Balance check plus referential integrity against the chart."""
        self.validate()
        for line in self.lines:
            if not chart.has(line.account_code):
                raise LedgerError(
                    f"科目 {line.account_code} 不在科目表中。"
                    f"可用科目：{', '.join(chart.codes()[:20])}"
                )


class ChartOfAccounts:
    """Minimal chart of accounts, keyed by code.

    Deliberately not a database-backed registry: this is the *validation*
    surface the ledger needs, and it is constructed per call from either the
    CAS defaults or a caller-supplied set. Persistence of custom charts is a
    separate concern (see the ``ledger_accounts`` table).
    """

    def __init__(self, accounts: Iterable[Account] = ()) -> None:
        self._by_code: dict[str, Account] = {}
        for account in accounts:
            self.add(account)

    def add(self, account: Account) -> None:
        self._by_code[account.code] = account

    def has(self, code: str) -> bool:
        return code in self._by_code

    def get(self, code: str) -> Account | None:
        return self._by_code.get(code)

    def codes(self) -> list[str]:
        return sorted(self._by_code)

    def __len__(self) -> int:
        return len(self._by_code)


# A working subset of 中国企业会计准则 (CAS) accounts — enough for the common
# flows a small business or an individual actually books. Not exhaustive; the
# point is that the *codes are real* so a model citing 1122 is citing something
# that exists in this chart.
CAS_DEFAULT_ACCOUNTS: tuple[Account, ...] = (
    # 资产
    Account("1001", "库存现金", "资产", "debit"),
    Account("1002", "银行存款", "资产", "debit"),
    Account("1012", "其他货币资金", "资产", "debit"),
    Account("1122", "应收账款", "资产", "debit"),
    Account("1123", "预付账款", "资产", "debit"),
    Account("1221", "其他应收款", "资产", "debit"),
    Account("1403", "原材料", "资产", "debit"),
    Account("1405", "库存商品", "资产", "debit"),
    Account("1601", "固定资产", "资产", "debit"),
    Account("1602", "累计折旧", "资产", "credit"),  # 备抵科目，贷方余额
    Account("1701", "无形资产", "资产", "debit"),
    # 负债
    Account("2001", "短期借款", "负债", "credit"),
    Account("2202", "应付账款", "负债", "credit"),
    Account("2203", "预收账款", "负债", "credit"),
    Account("2211", "应付职工薪酬", "负债", "credit"),
    Account("2221", "应交税费", "负债", "credit"),
    Account("2221001", "应交增值税", "负债", "credit"),
    Account("2221002", "应交企业所得税", "负债", "credit"),
    Account("2221003", "应交个人所得税", "负债", "credit"),
    Account("2241", "其他应付款", "负债", "credit"),
    # 权益
    Account("4001", "实收资本", "权益", "credit"),
    Account("4002", "资本公积", "权益", "credit"),
    Account("4103", "本年利润", "权益", "credit"),
    Account("4104", "利润分配", "权益", "credit"),
    # 收入
    Account("6001", "主营业务收入", "收入", "credit"),
    Account("6051", "其他业务收入", "收入", "credit"),
    Account("6111", "投资收益", "收入", "credit"),
    Account("6301", "营业外收入", "收入", "credit"),
    # 费用
    Account("6401", "主营业务成本", "费用", "debit"),
    Account("6601", "销售费用", "费用", "debit"),
    Account("6602", "管理费用", "费用", "debit"),
    Account("6603", "财务费用", "费用", "debit"),
    Account("6711", "营业外支出", "费用", "debit"),
    Account("6801", "所得税费用", "费用", "debit"),
)


def default_chart() -> ChartOfAccounts:
    return ChartOfAccounts(CAS_DEFAULT_ACCOUNTS)


@dataclass
class TrialBalanceRow:
    account_code: str
    account_name: str
    category: str
    debit_cents: int
    credit_cents: int


@dataclass
class TrialBalance:
    rows: list[TrialBalanceRow]
    total_debit_cents: int
    total_credit_cents: int

    @property
    def is_balanced(self) -> bool:
        return self.total_debit_cents == self.total_credit_cents


def trial_balance(
    entries: Iterable[JournalEntry],
    chart: ChartOfAccounts | None = None,
) -> TrialBalance:
    """Aggregate entries into a trial balance.

    Note the aggregation is on *raw* debit/credit columns, not on
    normal-balance-signed values. Presented this way the totals are directly
    comparable, which is what makes "借贷合计相等" a meaningful check rather
    than an artefact of how balances were signed.
    """
    chart = chart or default_chart()
    debits: dict[str, int] = {}
    credits: dict[str, int] = {}

    for entry in entries:
        for line in entry.lines:
            bucket = debits if line.direction == "debit" else credits
            bucket[line.account_code] = bucket.get(line.account_code, 0) + line.amount_cents

    rows: list[TrialBalanceRow] = []
    for code in sorted(set(debits) | set(credits)):
        account = chart.get(code)
        rows.append(
            TrialBalanceRow(
                account_code=code,
                account_name=account.name if account else "(未知科目)",
                category=account.category if account else "(未知)",
                debit_cents=debits.get(code, 0),
                credit_cents=credits.get(code, 0),
            )
        )

    return TrialBalance(
        rows=rows,
        total_debit_cents=sum(r.debit_cents for r in rows),
        total_credit_cents=sum(r.credit_cents for r in rows),
    )
