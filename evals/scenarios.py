"""Scenario definitions for the eval suites (ROADMAP M2-G)."""

from __future__ import annotations

from typing import Any

SUITES: dict[str, list[dict[str, Any]]] = {
    # ------------------------------------------------------------------
    # Intent routing — expect "ptc" | "flash"
    # ------------------------------------------------------------------
    "intent": [
        {"name": "深估值任务→PTC", "text": "对苹果做一个 DCF 估值模型", "has_workspace": True, "expected": "ptc"},
        {"name": "代码任务→PTC", "text": "写代码清洗这些财务数据", "has_workspace": True, "expected": "ptc"},
        {"name": "回测任务→PTC", "text": "跑一下回测分析这个策略", "has_workspace": False, "expected": "ptc"},
        {"name": "问候→Flash", "text": "你好", "has_workspace": False, "expected": "flash"},
        {"name": "感谢→Flash", "text": "谢谢", "has_workspace": False, "expected": "flash"},
        {"name": "解释→Flash", "text": "这句话什么意思？解释一下", "has_workspace": False, "expected": "flash"},
        {"name": "多指标对比→PTC", "text": "对比苹果和谷歌的毛利率和现金流，预测走势", "has_workspace": True, "expected": "ptc"},
        {"name": "简单报价→Flash", "text": "苹果最新股价是多少", "has_workspace": False, "expected": "flash"},
        {"name": "无工作区弱信号→Flash", "text": "分析财报", "has_workspace": False, "expected": "flash"},
        {"name": "计划模式→PTC", "text": "先规划一下研究步骤", "has_workspace": False, "plan_mode": True, "expected": "ptc"},
        {"name": "闲聊→Flash", "text": "随便聊聊", "has_workspace": True, "expected": "flash"},
        {"name": "深度研究→PTC", "text": "给我做个 deep research 关于数据中心", "has_workspace": True, "expected": "ptc"},
    ],
    # ------------------------------------------------------------------
    # Auditor — expect "error" (must be caught) | "pass"
    # ------------------------------------------------------------------
    "auditor": [
        {"name": "基准偏差→报错", "text": "营收为 $12.4B", "known_data": {"营收": 18_000.0}, "expect": "error"},
        {"name": "基准一致→通过", "text": "营收为 $18.2B", "known_data": {"营收": 18_000.0}, "expect": "pass"},
        {"name": "无引用→报错", "text": "我们认为毛利率将达到 45%", "provenance_sources": ["sec-10k"], "expect": "error"},
        {"name": "有引用→通过", "text": "毛利率45% per sec-10k", "provenance_sources": ["sec-10k"], "expect": "pass"},
        {"name": "矛盾数值→报错", "text": "毛利率为 45%，但后文写 毛利率 55%", "expect": "error"},
        {"name": "一致文本→通过", "text": "毛利率为 45%，营收 12.4B", "expect": "pass"},
    ],
    # ------------------------------------------------------------------
    # Deep research provider fallback — expect "pass"
    # ------------------------------------------------------------------
    "research_fallback": [
        {
            "name": "无供应商→优雅降级",
            "scenario": "empty_chain",
        },
        {
            "name": "可重试失败→切换下一家",
            "scenario": "retryable_fallback",
        },
        {
            "name": "致命失败→停止链",
            "scenario": "fatal_stops",
        },
    ],
}