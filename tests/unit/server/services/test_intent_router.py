"""Unit tests for intent routing (ROADMAP M2-B) — pure rule layer."""

from __future__ import annotations

import pytest

from src.server.services.router.intent import classify_intent


@pytest.mark.parametrize(
    "text,has_ws,expected",
    [
        # Strong PTC signals — win regardless of workspace presence
        ("帮我做一个苹果的 DCF 估值模型", True, "ptc"),
        ("写代码清洗这些财务数据", True, "ptc"),
        ("跑一下回测分析这个策略", False, "ptc"),
        # Strong flash signals
        ("你好", False, "flash"),
        ("谢谢", False, "flash"),
        ("这句话什么意思？解释一下", False, "flash"),
        # Normal tally: PTC wins on more hits (workspace present)
        ("对比苹果和谷歌的毛利率和现金流，预测走势", True, "ptc"),
        # Normal tally: flash wins when ptc signals lower (quick factual)
        ("苹果最新股价是多少", False, "flash"),
        # No workspace -> flash for weak/absent signals (auto never 400s)
        ("分析财报", False, "flash"),
        # Workspace + no signal -> flash (quick default path)
        ("随便聊聊", True, "flash"),
    ],
)
def test_classify_intent_modes(text: str, has_ws: bool, expected: str) -> None:
    decision = classify_intent(text, has_workspace=has_ws)
    assert decision.mode == expected
    assert decision.reason  # reason is always populated


def test_plan_mode_overrides_and_returns_reason() -> None:
    decision = classify_intent("先列个计划吧", has_workspace=False, plan_mode=True)
    assert decision.mode == "ptc"
    assert "plan" in decision.reason


def test_empty_text_no_workspace_routes_flash() -> None:
    decision = classify_intent("", has_workspace=False)
    assert decision.mode == "flash"


def test_empty_text_with_workspace_routes_ptc() -> None:
    decision = classify_intent("", has_workspace=True)
    assert decision.mode == "ptc"


def test_structure_signals_earn_high_confidence() -> None:
    assert classify_intent("做deep research", has_workspace=False).confidence >= 0.85
    assert classify_intent("你好", has_workspace=False).confidence >= 0.85