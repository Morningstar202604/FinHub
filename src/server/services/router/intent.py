"""Intent classification — auto agent-mode routing (ROADMAP M2-B).

Pure-rule, zero-LLM-cost classifier that decides whether a chat request should
run on the heavy PTC agent (sandbox + MCP + code execution) or the lightweight
flash agent (fast answers, shared workspace).

Deliberately no LLM call in the hot path: the rule layer is deterministic,
unit-testable, and returns a confidence score so a future LLM fallback can
slot in behind it without changing the interface (see ROADMAP M2-B).

Usage::

    decision = classify_intent(text, has_workspace=..., plan_mode=...)
    mode = decision.mode          # "flash" | "ptc"
    decision.reason              # human-readable routing reason
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# ---------------------------------------------------------------------------
# Signal lexicons — keyword buckets, ordered by strength.
# Keep these short and domain-shaped; they are cheap heuristics, not NLP.
# ---------------------------------------------------------------------------

# ⚠ PTC signals: the task needs a sandbox / multi-step tool pipeline /
# code execution / modeling. Strongest first so negation rarely wins.
_PTC_STRONG: Final[tuple[str, ...]] = (
    "建模",
    "估值",
    "dcf",
    "三表",
    "财务模型",
    "写代码",
    "跑数据",
    "清洗数据",
    "回测",
    "量化",
    "策略回测",
    "构建",
    "搭建",
    "deep research",
    "深度研究",
    "研究循环",
    "子代理",
    "subagent",
    "多线程",
    "批量分析",
    "分析师",
    "建模",
)

_PTC_NORMAL: Final[tuple[str, ...]] = (
    "分析",
    "对比",
    "比较",
    "预测",
    "展望",
    "财报",
    "报表",
    "报告",
    "图表",
    "画图",
    "可视化",
    "筛选",
    "选股",
    "扫描",
    "screening",
    "screener",
    "收益率",
    "毛利率",
    "现金流",
    "负债",
    "评级",
    "目标价",
    "催化剂",
    "财报电话",
    "earnings",
    "ev/ebitda",
    "pe",
    "peg",
    "roe",
    "期权",
    "options",
    "链上",
    "宏观",
    "gdp",
    "cpi",
    "利率",
    "美联储",
    "行业",
    "板块",
    "竞品",
    "competitive",
)

# ⚡ Flash signals: simple factual lookups, small talk, quick quotes.
_FLASH_STRONG: Final[tuple[str, ...]] = (
    "你好",
    "hi",
    "hello",
    "谢谢",
    "thank",
    "再见",
    "怎么回事",
    "什么意思",
    "解释一下",
    "是什么",
    "是多少",
    "帮我翻译",
    "英译中",
    "中译英",
)

_FLASH_NORMAL: Final[tuple[str, ...]] = (
    "报价",
    "股价",
    "现价",
    "今日",
    "最新",
    "涨跌",
    "行情",
    "quote",
    "price",
    "市值",
    "新闻",
    "news",
    "快讯",
    "简况",
    "概览",
    "时间",
    "几点",
)


def _contains_any(text: str, bucket: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(token.lower() in lowered for token in bucket)


@dataclass(frozen=True)
class IntentDecision:
    """Result of intent classification."""

    mode: str  # "flash" | "ptc"
    reason: str
    confidence: float = field(default=0.0)  # 0..1 heuristic strength


def classify_intent(
    text: str,
    *,
    has_workspace: bool,
    plan_mode: bool = False,
    requested_workspace: bool = False,
) -> IntentDecision:
    """Route a chat request to ``flash`` or ``ptc``.

    Arguments:
        text: the (joined) latest user message text.
        has_workspace: whether a workspace id is available/resolvable.
        plan_mode: whether the request explicitly asked for plan approval.
        requested_workspace: whether the client sent workspace_id directly.

    Rules (in order):
        1. Strong PTC signal  → ptc (highest confidence).
        2. Strong flash signal → flash.
        3. plan_mode            → ptc (planning needs the full agent).
        4. No workspace         → flash: ptc requires a workspace and auto
           routing must never surface a 400 behind the user's back; flash has
           a shared workspace. Strong signals above deliberately win over this
           so a clearly deep task still gets told a workspace is needed.
        5. Normal-strength tally: ptc wins if it has strictly more matches
           and at least 1; otherwise flash (quick default path).
    """
    if not text:
        # Empty/resume turns: keep whatever env exists; no workspace → flash.
        if not has_workspace:
            return IntentDecision(
                mode="flash",
                reason="no text & no workspace -> shared flash",
                confidence=0.9,
            )
        return IntentDecision(
            mode="ptc",
            reason="no text but workspace present -> ptc",
            confidence=0.6,
        )

    if _contains_any(text, _PTC_STRONG):
        return IntentDecision(
            mode="ptc",
            reason="strong ptc signal keyword",
            confidence=0.9,
        )
    if _contains_any(text, _FLASH_STRONG):
        return IntentDecision(
            mode="flash",
            reason="strong flash signal keyword",
            confidence=0.9,
        )
    if plan_mode:
        return IntentDecision(
            mode="ptc",
            reason="plan mode requested",
            confidence=0.8,
        )

    # Auto routing must never turn into a 400: ptc requires a workspace, and
    # flash carries a shared one. Weak/intent-less requests fall back to flash.
    if not has_workspace:
        return IntentDecision(
            mode="flash",
            reason="ptc requires a workspace; none available",
            confidence=0.85,
        )

    ptc_hits = _count_any(text, _PTC_NORMAL)
    flash_hits = _count_any(text, _FLASH_NORMAL)

    if ptc_hits > 0 and ptc_hits > flash_hits:
        return IntentDecision(
            mode="ptc",
            reason=f"normal ptc signals outrank flash ({ptc_hits}> {flash_hits})",
            confidence=0.7,
        )

    return IntentDecision(
        mode="flash",
        reason="default quick path (workspace optional)",
        confidence=0.55,
    )


def _count_any(text: str, bucket: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for token in bucket if token.lower() in lowered)