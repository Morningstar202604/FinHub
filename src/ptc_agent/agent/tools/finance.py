"""Finance ledger tools — the accounting primitives the finance roles call.

These wrap ``services/finance/ledger.py`` (validation + arithmetic) and
``database/ledger.py`` (persistence) into agent-callable tools.

Design stance: the model proposes, the ledger disposes. Every tool validates
before writing, and returns a *structured, correctable* error on failure rather
than a bare exception string. That matters more than it sounds: a model that
receives "分录不平衡：借 11300 − 贷 10000 = 1300 分" can fix itself in one
turn, whereas "LedgerError" gets it to retry the same broken entry.

Tools are bound to a ``user_id`` at construction (the repo's existing pattern —
see ``create_filesystem_tools``), so the model never supplies or sees an owner
id and cannot write to another user's ledger.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.server.database import ledger as ledger_db
from src.server.services.finance.ledger import (
    Account,
    LedgerError,
    from_cents,
    to_cents,
    trial_balance,
)

logger = logging.getLogger(__name__)


class EntryLineInput(BaseModel):
    """One line of a proposed journal entry.

    ``amount`` is a decimal string, not a float: JSON numbers cannot carry
    exact decimals and ``0.1 + 0.2 != 0.3`` is not acceptable in a ledger.
    """

    account_code: str = Field(
        description="会计科目编号，如 '1122'（应收账款）、'1002'（银行存款）、'6001'（主营业务收入）"
    )
    direction: Literal["debit", "credit"] = Field(
        description="借贷方向：'debit' 借 / 'credit' 贷"
    )
    amount: str = Field(
        description="金额（正数，十进制字符串，如 '11300.00'）。方向由 direction 表达，不要用负数。"
    )


def _parse_date(value: str | None) -> date:
    """Accept ISO date or datetime; default to today (UTC)."""
    if not value:
        return datetime.now(timezone.utc).date()
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise LedgerError(
            f"日期格式无效：{value!r}——请用 ISO 格式 'YYYY-MM-DD'"
        ) from exc


def create_finance_tools(user_id: str, currency: str = "CNY") -> list:
    """Build the ledger tool set bound to one user.

    ``currency`` sets the minor-unit exponent used for cent conversion. It is
    per-call rather than global because JPY has no minor unit — assuming two
    decimal places would scale every JPY amount by 100.
    """

    def _reject(message: str) -> str:
        """Uniform failure shape. Prefixed so the model can tell a rejection
        from a success at a glance, and so it is obvious *what to change*."""
        return f"❌ 分录被拒绝：{message}"

    @tool("post_journal_entry", parse_docstring=True)
    async def post_journal_entry(
        entry_date: Annotated[str, "记账日期，ISO 格式 'YYYY-MM-DD'（留空为今天）"] = "",
        memo: Annotated[str, "摘要，说明这笔业务的实质"] = "",
        lines: Annotated[
            list[EntryLineInput],
            "分录行列表。复式记账要求至少一借一贷，且借方合计必须等于贷方合计。",
        ] = None,
        idempotency_key: Annotated[
            str, "幂等键（可选）。同一键重复提交会被拒绝，用于防止重试导致重复入账。"
        ] = "",
    ) -> str:
        """录入一张记账凭证（复式记账）。

        这个工具会强制执行复式记账规则，不满足时拒绝入账并说明原因：
        - 至少一借一贷，不能只有借方或只有贷方
        - 借方合计必须等于贷方合计（精确到分）
        - 所有科目编号必须存在于科目表中

        什么时候用：
        - 用户描述了一笔业务（开票、收款、付款、计提、报销）需要入账
        - 需要把原始单据转成会计分录

        注意事项：
        - 金额用正数，方向由 direction 表达
        - 含税业务要拆出税额（如 13% 增值税：收入 + 应交增值税 = 价税合计）
        - 不确定科目时，先用 list_accounts 查询可用科目

        Args:
            entry_date: 记账日期 YYYY-MM-DD
            memo: 摘要
            lines: 分录行，每行含 account_code / direction / amount
            idempotency_key: 幂等键，防止重复提交

        Returns:
            成功时返回凭证号与借贷合计；失败时返回被拒绝的具体原因
        """
        if not lines:
            return _reject("未提供任何分录行")

        try:
            when = _parse_date(entry_date)
            entry = ledger_db.JournalEntry(entry_date=when, memo=memo or "(无摘要)")
            for raw in lines:
                entry.add(
                    raw.account_code.strip(),
                    raw.direction,
                    to_cents(raw.amount, currency),
                )

            # Validate here, in the tool, before handing off for persistence.
            # insert_entry validates too, but this tool's contract -- "invalid
            # entries are rejected with a correctable message" -- must not
            # depend on the storage layer keeping that promise. If a future
            # write path skipped the check, this tool would start reporting
            # "✅ 凭证已入账" for an unbalanced entry while its own docstring
            # still claimed otherwise.
            chart = await ledger_db.load_chart(user_id)
            entry.validate_against(chart)

            entry_id = await ledger_db.insert_entry(
                user_id,
                entry,
                source="agent",
                idempotency_key=idempotency_key or None,
            )
        except LedgerError as exc:
            return _reject(str(exc))
        except ledger_db.DuplicateEntryError as exc:
            return f"⚠️ 未入账：{exc}"
        except Exception as exc:  # noqa: BLE001 - surfaced, not swallowed
            logger.exception("post_journal_entry failed")
            return f"❌ 入账失败（系统错误）：{exc}"

        total = from_cents(entry.total_debit_cents(), currency)
        detail = "\n".join(
            f"  - {line.account_code}  "
            f"{'借' if line.direction == 'debit' else '贷'} "
            f"{from_cents(line.amount_cents, currency)}"
            for line in entry.lines
        )
        return (
            f"✅ 凭证已入账\n"
            f"凭证号：{entry_id}\n"
            f"日期：{entry.entry_date}\n"
            f"摘要：{entry.memo}\n"
            f"{detail}\n"
            f"借贷合计：{total} {currency}（已通过平衡校验）"
        )

    @tool("list_accounts", parse_docstring=True)
    async def list_accounts(
        category: Annotated[
            str, "按类别过滤：资产 / 负债 / 权益 / 收入 / 费用（留空返回全部）"
        ] = "",
    ) -> str:
        """查询可用的会计科目表。

        入账前如果对科目编号不确定，先用这个工具查询。返回的是真实存在的
        科目——入账时引用了不在表中的编号会被拒绝。

        Args:
            category: 可选类别过滤

        Returns:
            科目列表（编号 / 名称 / 类别 / 余额方向）
        """
        try:
            rows = await ledger_db.list_accounts(user_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("list_accounts failed")
            return f"❌ 查询科目失败：{exc}"

        if category:
            rows = [r for r in rows if r["category"] == category]
        if not rows:
            return f"（没有匹配的科目：{category or '全部'}）"

        by_category: dict[str, list] = {}
        for row in rows:
            by_category.setdefault(row["category"], []).append(row)

        parts = [f"科目表（共 {len(rows)} 个）"]
        for cat in ("资产", "负债", "权益", "收入", "费用"):
            if cat not in by_category:
                continue
            parts.append(f"\n【{cat}】")
            for row in by_category[cat]:
                mark = " *自定义*" if row.get("is_custom") else ""
                parts.append(
                    f"  {row['code']:>8}  {row['name']:<12} "
                    f"({'借' if row['normal_balance'] == 'debit' else '贷'}方余额){mark}"
                )
        return "\n".join(parts)

    @tool("add_account", parse_docstring=True)
    async def add_account(
        code: Annotated[str, "科目编号，如 '6602'。与现有编号重复会覆盖其属性。"],
        name: Annotated[str, "科目名称"],
        category: Annotated[str, "类别：资产 / 负债 / 权益 / 收入 / 费用"],
        normal_balance: Annotated[str, "正常余额方向：'debit' 借 / 'credit' 贷"],
    ) -> str:
        """新增或修改一个会计科目（用于企业自定义核算需要）。

        标准科目已内置，只有在现有科目表无法满足核算要求时才需要用这个工具。
        注意：修改已有科目的余额方向会影响试算平衡的解读，请谨慎。

        Args:
            code: 科目编号
            name: 科目名称
            category: 类别
            normal_balance: 余额方向

        Returns:
            操作结果
        """
        if category not in ("资产", "负债", "权益", "收入", "费用"):
            return f"❌ 类别无效：{category!r}——必须是 资产/负债/权益/收入/费用"
        if normal_balance not in ("debit", "credit"):
            return f"❌ 余额方向无效：{normal_balance!r}——必须是 'debit' 或 'credit'"

        try:
            await ledger_db.upsert_account(
                user_id,
                Account(
                    code=code.strip(),
                    name=name,
                    category=category,
                    normal_balance=normal_balance,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("add_account failed")
            return f"❌ 保存科目失败：{exc}"

        return f"✅ 科目已保存：{code} {name}（{category}，{'借' if normal_balance == 'debit' else '贷'}方余额）"

    @tool("get_trial_balance", parse_docstring=True)
    async def get_trial_balance(
        start_date: Annotated[str, "起始日期 YYYY-MM-DD（留空则不限）"] = "",
        end_date: Annotated[str, "截止日期 YYYY-MM-DD（留空则不限）"] = "",
    ) -> str:
        """生成科目余额表（试算平衡表）。

        汇总指定期间内所有已入账凭证的借贷发生额，按科目归集。
        借贷合计必须相等——如果不等，说明存在数据问题，会明确提示。

        Args:
            start_date: 起始日期
            end_date: 截止日期

        Returns:
            科目余额表，含各科目借贷发生额与合计
        """
        try:
            entries = await ledger_db.load_entries_as_objects(
                user_id,
                start_date=_parse_date(start_date) if start_date else None,
                end_date=_parse_date(end_date) if end_date else None,
            )
            chart = await ledger_db.load_chart(user_id)
            tb = trial_balance(entries, chart)
        except LedgerError as exc:
            return _reject(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("get_trial_balance failed")
            return f"❌ 生成试算平衡表失败：{exc}"

        if not tb.rows:
            return "（该期间内没有已入账的凭证）"

        period = f"{start_date or '不限'} ~ {end_date or '不限'}"
        parts = [
            f"科目余额表（{period}，货币 {currency}）",
            f"共 {len(entries)} 张凭证、{len(tb.rows)} 个科目",
            "",
            f"{'科目编号':<10}{'科目名称':<14}{'借方发生额':>14}{'贷方发生额':>14}",
            "-" * 54,
        ]
        for row in tb.rows:
            parts.append(
                f"{row.account_code:<10}{row.account_name:<14}"
                f"{str(from_cents(row.debit_cents, currency)):>14}"
                f"{str(from_cents(row.credit_cents, currency)):>14}"
            )
        parts.append("-" * 54)
        parts.append(
            f"{'合计':<24}"
            f"{str(from_cents(tb.total_debit_cents, currency)):>14}"
            f"{str(from_cents(tb.total_credit_cents, currency)):>14}"
        )
        parts.append("")
        parts.append(
            "✅ 借贷平衡" if tb.is_balanced
            else "❌ 借贷不平——数据异常，请检查是否有未通过校验的凭证被直接写入"
        )
        return "\n".join(parts)

    @tool("list_journal_entries", parse_docstring=True)
    async def list_journal_entries(
        start_date: Annotated[str, "起始日期 YYYY-MM-DD（留空则不限）"] = "",
        end_date: Annotated[str, "截止日期 YYYY-MM-DD（留空则不限）"] = "",
        account_code: Annotated[str, "只看涉及某科目的凭证，如 '1122'（留空为全部）"] = "",
        limit: Annotated[int, "最多返回多少行（默认 100）"] = 100,
    ) -> str:
        """查询已入账的记账凭证明细。

        什么时候用：
        - 用户问"某科目的明细账"
        - 需要核对某笔业务是否已入账
        - 审计时追溯某期间的全部凭证

        Args:
            start_date: 起始日期
            end_date: 截止日期
            account_code: 按科目过滤
            limit: 返回行数上限

        Returns:
            凭证明细（按日期倒序）
        """
        try:
            rows = await ledger_db.list_entries(
                user_id,
                start_date=_parse_date(start_date) if start_date else None,
                end_date=_parse_date(end_date) if end_date else None,
                account_code=account_code or None,
                limit=limit,
            )
        except LedgerError as exc:
            return _reject(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("list_journal_entries failed")
            return f"❌ 查询凭证失败：{exc}"

        if not rows:
            return "（没有匹配的凭证）"

        # Group lines under their entry so the output reads like a voucher
        # register rather than a flat join result.
        grouped: dict[str, list] = {}
        meta: dict[str, dict] = {}
        for row in rows:
            key = str(row["entry_id"])
            grouped.setdefault(key, []).append(row)
            meta.setdefault(
                key,
                {
                    "date": row["entry_date"],
                    "memo": row["memo"],
                    "source": row["source"],
                },
            )

        parts = [f"凭证明细（{len(meta)} 张）", ""]
        for key, entries in grouped.items():
            info = meta[key]
            parts.append(f"【{info['date']}】{info['memo']}  （来源: {info['source']}）")
            for row in entries:
                parts.append(
                    f"    {'借' if row['direction'] == 'debit' else '贷'} "
                    f"{row['account_code']:<10} "
                    f"{from_cents(row['amount_minor'], currency)}"
                )
            parts.append("")
        return "\n".join(parts)

    @tool("check_entry_balance", parse_docstring=True)
    async def check_entry_balance(
        lines: Annotated[
            list[EntryLineInput], "待校验的分录行（不入账，只校验）"
        ] = None,
    ) -> str:
        """校验一组分录是否满足复式记账规则（不入账）。

        在正式入账前如果不确定分录是否正确，可以先用这个工具校验。
        它会检查借贷是否平衡、科目是否存在，并给出具体差额。

        Args:
            lines: 待校验的分录行

        Returns:
            校验结果与差额
        """
        if not lines:
            return _reject("未提供任何分录行")

        try:
            entry = ledger_db.JournalEntry(
                entry_date=datetime.now(timezone.utc).date(), memo="(校验)"
            )
            for raw in lines:
                entry.add(
                    raw.account_code.strip(),
                    raw.direction,
                    to_cents(raw.amount, currency),
                )
            chart = await ledger_db.load_chart(user_id)
            entry.validate_against(chart)
        except LedgerError as exc:
            return _reject(str(exc))

        debit = from_cents(entry.total_debit_cents(), currency)
        return (
            f"✅ 分录合法\n"
            f"借方合计：{debit} {currency}\n"
            f"贷方合计：{from_cents(entry.total_credit_cents(), currency)} {currency}\n"
            f"共 {len(entry.lines)} 行，借贷平衡且科目均存在"
        )

    return [
        post_journal_entry,
        list_accounts,
        add_account,
        get_trial_balance,
        list_journal_entries,
        check_entry_balance,
    ]
