"""Personal-finance tools — the primitives an individual's finances need.

These wrap ``services/finance/personal.py`` (arithmetic) and
``database/personal_finance.py`` (persistence) into agent-callable tools.

Why this is a separate tool set from the ledger
===============================================

An individual does not keep a 科目余额表 and does not book 应交增值税. Asking
them to express a salary as a journal entry is a worse interface than asking
for the salary. But the *reason* this layer exists is identical to the
ledger's: a model asked "what's my net worth" with no real primitives will
produce a confident number assembled from whatever it remembers of the
conversation. So the shape differs; the discipline does not.

The split that matters
----------------------

The tools are split deliberately between **input** (``record_*``, which
validate and persist) and **analysis** (``get_*``, which compute from
persisted data). A model may not pass a hand-computed net worth to an analysis
tool — it must record the components and let :mod:`personal` do the
arithmetic. That is the same "the model proposes, the module disposes" stance
the ledger takes, and it is what stops a plausible-sounding total from being
invented wholesale.

Liquidity is stated, not guessed
--------------------------------

``record_balance_sheet`` accepts an explicit ``liquid`` flag per asset, and
defaults it from the class catalogue when omitted. It does not infer liquidity
from a label: whether 房产 counts as available funds is a judgement about
intent, and a name-based rule gets it wrong the moment someone holds REITs.

Tools are bound to a ``user_id`` at construction (the repo's existing pattern),
so the model never supplies or sees an owner id and cannot read or write
another user's financial position.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Annotated

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.server.database import personal_finance as pf_db
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

logger = logging.getLogger(__name__)

# The catalogue is the single source of truth for valid class keys; the tool
# validates against it rather than maintaining a second list that could drift.
_ASSET_CLASSES = {c["key"]: c for c in pf_db.asset_class_catalog()}

_CASH_FLOW_CATEGORIES = (
    "收入",
    "固定支出",
    "生活支出",
    "可选支出",
    "储蓄投资",
    "债务偿还",
)


class BalanceSheetAssetInput(BaseModel):
    """One asset line in a personal balance sheet."""

    key: str = Field(
        description=(
            "资产类别（必须来自 get_asset_classes 返回的 key）："
            "cash 现金及活期 / deposit 定期存款 / investment 投资 / "
            "receivable 应收借出款 / property 房产 / vehicle 车辆 / other 其他"
        )
    )
    label: str = Field(description="具体名称，如 '招商银行活期'、'自住房'")
    amount: str = Field(description="金额（正数，十进制字符串，如 '350000.00'）")
    liquid: bool | None = Field(
        default=None,
        description=(
            "是否算作可动用资金（一个月内能变现）。留空则按类别默认值："
            "现金/存款/投资为 True，房产/车辆/应收为 False。"
            "只在类别默认不符时显式指定。"
        ),
    )


class BalanceSheetLiabilityInput(BaseModel):
    """One liability line in a personal balance sheet."""

    key: str = Field(description="负债类别，如 'mortgage'、'consumer_loan'、'credit_card'")
    label: str = Field(description="具体名称，如 '房贷（工商银行）'")
    amount: str = Field(description="本金余额（正数）")
    monthly_payment: str = Field(
        default="", description="每月还款额（可选，留空表示未知）"
    )


class CashFlowItemInput(BaseModel):
    """One line of a personal cash-flow statement."""

    # ``str``, not ``Literal[...]``, deliberately. A Literal makes Pydantic
    # reject the call *before* the tool body runs, so the model receives a raw
    # ValidationError spanning the whole argument object instead of the one
    # correctable message this layer is built to return. The tool validates
    # against _CASH_FLOW_CATEGORIES and answers with the list of valid values.
    category: str = Field(
        description=(
            "类别，决定该项在储蓄率计算中的处理方式。必须是："
            "收入 / 固定支出 / 生活支出 / 可选支出 / 储蓄投资 / 债务偿还"
        )
    )
    label: str = Field(description="具体名称，如 '工资'、'房租'、'基金定投'")
    amount: str = Field(description="金额（正数，十进制字符串）")


def _parse_date(value: str | None, *, default_today: bool = True) -> date | None:
    if not value:
        if default_today:
            return datetime.now(UTC).date()
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise FinanceError(
            f"日期格式无效：{value!r}——请用 ISO 格式 'YYYY-MM-DD'"
        ) from exc


def create_personal_finance_tools(user_id: str, currency: str = "CNY") -> list:
    """Build the personal-finance tool set bound to one user."""

    def _reject(message: str) -> str:
        return f"❌ 记录被拒绝：{message}"

    def _money(cents: int) -> str:
        return f"{format_money(cents, currency)} {currency}"

    @tool("record_balance_sheet", parse_docstring=True)
    async def record_balance_sheet(
        as_of: Annotated[str, "资产负债表的时点，ISO 格式 'YYYY-MM-DD'（留空为今天）"] = "",
        assets: Annotated[
            list[BalanceSheetAssetInput], "资产明细（可为空，但资产与负债不能同时为空）"
        ] = None,
        liabilities: Annotated[
            list[BalanceSheetLiabilityInput], "负债明细（可为空）"
        ] = None,
        note: Annotated[str, "备注，说明数据来源或口径"] = "",
    ) -> str:
        """记录个人资产负债表（净资产快照）。

        什么时候用：
        - 用户说"我有XX万存款、一套房、还欠XX万房贷"这类资产/负债描述
        - 需要计算净资产或资产负债率

        注意事项：
        - 资产与负债都记正数，负债本身即代表对外欠款，不要用负数
        - 不要把同一个账户同时记进两个类别（会重复计算净资产）
        - 金额不确定时先向用户确认，不要估算后记账

        Args:
            as_of: 快照时点
            assets: 资产明细
            liabilities: 负债明细
            note: 备注

        Returns:
            成功时返回净资产、可用资金等汇总；失败时返回具体原因
        """
        assets = assets or []
        liabilities = liabilities or []
        if not assets and not liabilities:
            return _reject("资产与负债均为空——没有任何内容可记录")

        try:
            when = _parse_date(as_of)
            sheet = BalanceSheet(as_of=when)  # type: ignore[arg-type]
            for raw in assets:
                cls = _ASSET_CLASSES.get(raw.key.strip())
                if cls is None:
                    valid = "、".join(_ASSET_CLASSES)
                    return _reject(
                        f"未知资产类别 {raw.key!r}——可用类别：{valid}"
                    )
                liquid = cls["liquid"] if raw.liquid is None else raw.liquid
                sheet.assets.append(
                    Asset(
                        key=cls["key"],
                        label=raw.label,
                        amount_cents=to_cents(raw.amount, currency),
                        liquid=liquid,
                    )
                )
            for raw in liabilities:
                monthly = (
                    to_cents(raw.monthly_payment, currency)
                    if raw.monthly_payment
                    else None
                )
                sheet.liabilities.append(
                    Liability(
                        key=raw.key.strip(),
                        label=raw.label,
                        amount_cents=to_cents(raw.amount, currency),
                        monthly_payment_cents=monthly,
                    )
                )

            snapshot_id = await pf_db.save_snapshot(
                user_id,
                "balance_sheet",
                period_start=when,
                period_end=when,
                items=pf_db.items_from_balance_sheet(sheet),
                currency=currency,
                note=note,
            )
        except FinanceError as exc:
            return _reject(str(exc))
        except Exception as exc:
            logger.exception("record_balance_sheet failed")
            return f"❌ 记录失败（系统错误）：{exc}"

        ratio = sheet.debt_to_asset_ratio
        dti = f"{ratio:.2%}" if ratio is not None else "无资产可比"
        return (
            f"✅ 资产负债表已记录（{when}）\n"
            f"快照号：{snapshot_id}\n"
            f"总资产：{_money(sheet.total_assets_cents)}\n"
            f"其中可动用（一个月内可变现）：{_money(sheet.liquid_assets_cents)}\n"
            f"总负债：{_money(sheet.total_liabilities_cents)}\n"
            f"净资产：{_money(sheet.net_worth_cents)}\n"
            f"资产负债率：{dti}\n"
            f"注：不可动用资产（房产等）不计入「可动用」"
        )

    @tool("record_cash_flow", parse_docstring=True)
    async def record_cash_flow(
        start_date: Annotated[str, "区间起始日 YYYY-MM-DD"],
        end_date: Annotated[str, "区间结束日 YYYY-MM-DD（含当日）"],
        items: Annotated[
            list[CashFlowItemInput], "收支明细（至少一项）"
        ] = None,
        note: Annotated[str, "备注"] = "",
    ) -> str:
        """记录一段时期的个人收支（现金流量）。

        什么时候用：
        - 用户说"我月薪X、房租Y、吃饭Z"这类收支描述
        - 需要计算储蓄率、结余或应急资金可支撑月数

        注意区间：工具会按实际天数折算月度必要支出，所以记一个季度或一年的
        数据同样准确，不必自己换算成月。

        Args:
            start_date: 区间起始日
            end_date: 区间结束日
            items: 收支明细
            note: 备注

        Returns:
            成功时返回收入、支出、储蓄率等汇总；失败时返回具体原因
        """
        items = items or []
        if not items:
            return _reject("未提供任何收支明细")

        try:
            start = _parse_date(start_date)
            end = _parse_date(end_date)
            if start is None or end is None:
                return _reject("必须提供 start_date 与 end_date")
            if end < start:
                return _reject(
                    f"区间无效：结束日 {end} 早于起始日 {start}"
                )

            statement = CashFlowStatement(start=start, end=end)
            for raw in items:
                if raw.category not in _CASH_FLOW_CATEGORIES:
                    valid = "、".join(_CASH_FLOW_CATEGORIES)
                    return _reject(
                        f"未知类别 {raw.category!r}——可用类别：{valid}"
                    )
                statement.items.append(
                    CashFlowItem(
                        category=raw.category,
                        label=raw.label,
                        amount_cents=to_cents(raw.amount, currency),
                    )
                )

            snapshot_id = await pf_db.save_snapshot(
                user_id,
                "cash_flow",
                period_start=start,
                period_end=end,
                items=pf_db.items_from_cash_flow(statement),
                currency=currency,
                note=note,
            )
        except FinanceError as exc:
            return _reject(str(exc))
        except Exception as exc:
            logger.exception("record_cash_flow failed")
            return f"❌ 记录失败（系统错误）：{exc}"

        rate = statement.savings_rate
        rate_text = f"{rate:.2%}" if rate is not None else "无法计算（无收入）"
        parts = [
            f"✅ 收支已记录（{start} ~ {end}，共 {(end - start).days + 1} 天）",
            f"快照号：{snapshot_id}",
            f"收入：{_money(statement.income_cents)}",
            f"固定支出：{_money(statement.fixed_cents)}",
            f"生活支出：{_money(statement.living_cents)}",
            f"可选支出：{_money(statement.discretionary_cents)}",
            f"储蓄投资：{_money(statement.savings_cents)}",
            f"债务偿还：{_money(statement.debt_service_cents)}",
            f"净结余：{_money(statement.net_cents)}"
            + ("（⚠️ 入不敷出，正在消耗存量）" if statement.is_deficit else ""),
            f"储蓄率：{rate_text}",
            "",
            "储蓄率口径：分母不含「储蓄投资」——转入投资账户属于储蓄行为本身，",
            "不视为消费，否则同等结果下主动投资者反被算得更低。",
        ]
        return "\n".join(parts)

    @tool("get_net_worth", parse_docstring=True)
    async def get_net_worth(
        as_of: Annotated[str, "查询时点 YYYY-MM-DD（留空为最新一期）"] = "",
    ) -> str:
        """查询个人净资产与资产负债结构。

        读取已记录的资产负债表快照。如果没有记录过，会明确提示先用
        record_balance_sheet 记录，而不是凭空估算。

        Args:
            as_of: 查询时点

        Returns:
            净资产、可用资金、负债结构，或"尚无记录"的提示
        """
        try:
            row = await pf_db.get_latest_snapshot(user_id, "balance_sheet")
        except Exception as exc:
            logger.exception("get_net_worth failed")
            return f"❌ 查询净资产失败：{exc}"

        if row is None:
            return (
                "（尚无资产负债表记录）\n"
                "请先用 record_balance_sheet 记录资产与负债明细，再查询净资产。"
            )

        sheet = pf_db.balance_sheet_from_row(row)
        ratio = sheet.debt_to_asset_ratio
        has_monthly = [
            li for li in sheet.liabilities if li.monthly_payment_cents
        ]
        parts = [
            f"净资产（{sheet.as_of}）",
            f"总资产：{_money(sheet.total_assets_cents)}",
            f"其中可动用：{_money(sheet.liquid_assets_cents)}",
            f"总负债：{_money(sheet.total_liabilities_cents)}",
            f"净资产：{_money(sheet.net_worth_cents)}",
            f"资产负债率：{f'{ratio:.2%}' if ratio is not None else '无资产可比'}",
        ]
        if has_monthly:
            monthly_debt = sum(
                li.monthly_payment_cents or 0 for li in sheet.liabilities
            )
            parts.append(f"每月还款合计：{_money(monthly_debt)}")

        if sheet.assets:
            parts.append("\n资产明细：")
            for a in sorted(sheet.assets, key=lambda x: -x.amount_cents):
                parts.append(
                    f"  {a.label:<16}{_money(a.amount_cents):>18}"
                    f"  {'可动用' if a.liquid else '不可动用'}"
                )
        if sheet.liabilities:
            parts.append("\n负债明细：")
            for li in sorted(sheet.liabilities, key=lambda x: -x.amount_cents):
                parts.append(f"  {li.label:<16}{_money(li.amount_cents):>18}")
        return "\n".join(parts)

    @tool("get_cash_flow_analysis", parse_docstring=True)
    async def get_cash_flow_analysis() -> str:
        """分析个人现金流：储蓄率、结余、应急资金可支撑月数。

        读取最新一期收支记录与最新一期资产负债表，合并计算：
        - 储蓄率与净结余
        - 月度必要支出（按实际天数折算）
        - 应急资金可支撑月数（用可动用资产 ÷ 月度必要支出）

        应急资金只算「可动用」资产，不含房产——把房子算进去会得出一个
        令人安心但毫无用处的月数。

        Returns:
            现金流分析，或"尚无记录"的提示
        """
        try:
            flow_row = await pf_db.get_latest_snapshot(user_id, "cash_flow")
        except Exception as exc:
            logger.exception("get_cash_flow_analysis failed")
            return f"❌ 查询现金流失败：{exc}"

        if flow_row is None:
            return (
                "（尚无收支记录）\n"
                "请先用 record_cash_flow 记录一段时期的收支，再进行分析。"
            )

        statement = pf_db.cash_flow_from_row(flow_row)
        rate = statement.savings_rate
        parts = [
            f"现金流分析（{statement.start} ~ {statement.end}，"
            f"共 {(statement.end - statement.start).days + 1} 天）",
            f"收入：{_money(statement.income_cents)}",
            f"总流出：{_money(statement.total_outflow_cents)}",
            f"净结余：{_money(statement.net_cents)}"
            + ("（⚠️ 入不敷出）" if statement.is_deficit else ""),
            f"储蓄率：{f'{rate:.2%}' if rate is not None else '无法计算（无收入）'}",
        ]

        if statement.income_cents > 0:
            by_cat = [
                ("固定支出", statement.fixed_cents),
                ("生活支出", statement.living_cents),
                ("可选支出", statement.discretionary_cents),
                ("储蓄投资", statement.savings_cents),
                ("债务偿还", statement.debt_service_cents),
            ]
            parts.append("\n支出结构（占收入比）：")
            for label, amount in by_cat:
                if amount == 0:
                    continue
                share = amount / statement.income_cents
                parts.append(f"  {label:<10}{_money(amount):>18}  {share:>7.2%}")

        essential = monthly_essential_from(statement)
        parts.append(f"\n月度必要支出（固定+生活，按天数折算）：{_money(essential)}")

        try:
            bs_row = await pf_db.get_latest_snapshot(user_id, "balance_sheet")
        except Exception:
            bs_row = None
        if bs_row is None:
            parts.append(
                "（尚无资产负债表记录，无法计算应急资金月数——"
                "请先用 record_balance_sheet 记录）"
            )
        else:
            sheet = pf_db.balance_sheet_from_row(bs_row)
            months = emergency_fund_months(sheet.liquid_assets_cents, essential)
            if months is None:
                parts.append("应急资金月数：无法计算（必要支出为 0）")
            else:
                verdict = (
                    "偏紧（建议至少 3 个月）" if months < 3
                    else "尚可（建议 3–6 个月）" if months < 6
                    else "充足"
                )
                parts.append(
                    f"应急资金：{_money(sheet.liquid_assets_cents)}"
                    f" ÷ {_money(essential)} = {months} 个月 — {verdict}"
                )
        return "\n".join(parts)

    @tool("get_asset_classes", parse_docstring=True)
    async def get_asset_classes() -> str:
        """查询可用的资产类别及其流动性默认值。

        在调用 record_balance_sheet 之前用它确认 key 的取值。
        入账时使用未在此列出的 key 会被拒绝。

        Returns:
            资产类别列表（key / 名称 / 是否默认可动用）
        """
        lines = ["可用资产类别（record_balance_sheet 的 key 字段）："]
        for cls in _ASSET_CLASSES.values():
            lines.append(
                f"  {cls['key']:<12}{cls['label']:<22}"
                f"{'默认可动用' if cls['liquid'] else '默认不可动用'}"
            )
        lines.append("")
        lines.append(
            "流动性是显式标注而非按名称推断的：房产卖出能否算「这个月可用资金」"
            "取决于你的意图，同一类别的资产在不同情况下答案不同。"
        )
        return "\n".join(lines)

    @tool("list_financial_snapshots", parse_docstring=True)
    async def list_financial_snapshots(
        kind: Annotated[str, "快照类型：'balance_sheet' / 'cash_flow'（留空为全部）"] = "",
        limit: Annotated[int, "最多返回多少条（默认 20）"] = 20,
    ) -> str:
        """列出历史财务快照，用于观察净资产或收支的时间变化。

        Args:
            kind: 快照类型过滤
            limit: 返回条数上限

        Returns:
            快照列表（时点 / 类型 / 摘要 / 金额）
        """
        if kind and kind not in ("balance_sheet", "cash_flow"):
            return f"❌ 类型无效：{kind!r}——必须是 'balance_sheet' 或 'cash_flow'"

        try:
            rows = await pf_db.list_snapshots(
                user_id, kind=kind or None, limit=limit
            )
        except Exception as exc:
            logger.exception("list_financial_snapshots failed")
            return f"❌ 查询快照失败：{exc}"

        if not rows:
            return "（没有匹配的财务快照）"

        parts = [f"财务快照（{len(rows)} 条，按期间倒序）", ""]
        for row in rows:
            label = "资产负债表" if row["kind"] == "balance_sheet" else "现金流量"
            if row["kind"] == "balance_sheet":
                sheet = pf_db.balance_sheet_from_row(row)
                summary = (
                    f"净资产 {_money(sheet.net_worth_cents)}"
                    f"（资产 {_money(sheet.total_assets_cents)}"
                    f" / 负债 {_money(sheet.total_liabilities_cents)}）"
                )
            else:
                statement = pf_db.cash_flow_from_row(row)
                rate = statement.savings_rate
                summary = (
                    f"收入 {_money(statement.income_cents)}"
                    f" / 结余 {_money(statement.net_cents)}"
                    f" / 储蓄率 {f'{rate:.2%}' if rate is not None else 'N/A'}"
                )
            period = (
                str(row["period_end"])
                if row["period_start"] == row["period_end"]
                else f"{row['period_start']} ~ {row['period_end']}"
            )
            parts.append(f"【{period}】{label}")
            parts.append(f"    {summary}")
            if row["note"]:
                parts.append(f"    备注：{row['note']}")
            parts.append("")
        return "\n".join(parts)

    return [
        record_balance_sheet,
        record_cash_flow,
        get_net_worth,
        get_cash_flow_analysis,
        get_asset_classes,
        list_financial_snapshots,
    ]
