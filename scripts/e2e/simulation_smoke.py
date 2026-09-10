"""Simulated full-chain smoke (no external keys, no DB).

Walks the behavior a real chat turn exercises, end to end, with mocked
providers: intent routing → (deep) research → self-audit → structured
artifact → memory recall. Exits non-zero on any hard failure.
"""

import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


async def main() -> int:
    from src.server.services.router.intent import classify_intent
    from src.tools.research_qa.artifacts import build_artifact, artifact_to_dict
    from src.tools.research_qa.auditor import audit_report
    from src.tools.web.search import get_web_search_tool
    from src.tools.memory.retrieval import build_chunks, recall

    checks = []

    # 1. Intent routing (rule layer, no LLM key needed).
    decision = classify_intent(
        "帮我深度分析一下 NVDA 的数据中心收入趋势并做个估值模型",
        has_workspace=True,
    )
    ok1 = decision.mode == "ptc"
    checks.append(("意图识别 → PTC（深度分析/建模）", ok1, decision.to_dict() if hasattr(decision, "to_dict") else str(decision)))

    decision2 = classify_intent("今天大盘怎么样", has_workspace=False)
    ok2 = decision2.mode == "flash"
    checks.append(("意图识别 → Flash（简单行情）", ok2, str(decision2)))

    # 2. Deep research tool: provider chain degrades to 'none' without keys.
    from src.tools.web.tools.deep_research import run_deep_research
    content, artifact = await run_deep_research("AI 算力需求", level="quick")
    ok3 = artifact.get("provider") in ("none",) or ("citations" in artifact)
    checks.append(("深度研究工具（无 key 优雅降级）", ok3, f"provider={artifact.get('provider')}"))

    # 3. Web search tool builders resolve (none requires env keys at build time).
    tool = get_web_search_tool(max_search_results=5)
    checks.append(("联网搜索工具可构建", tool is not None, tool.name))

    # 4. Self-verification auditor catches a fabricated number.
    report = audit_report(
        "英伟达 2026 财年数据中心收入 1200 亿美元，毛利率 70%。",
        known_data={"数据中心收入": 18000.0},  # USD-millions
        provenance_sources=["sec-filing"],
    )
    has_error = any(f.level == "error" for f in report.findings)
    ok4 = has_error
    checks.append(("自我验证审校器（检出数字失真）", ok4, f"errors={sum(1 for f in report.findings if f.level=='error')}"))

    # 5. Structured output round-trips through the pydantic artifact schema.
    art = build_artifact(
        "report",
        title="AI 算力主题",
        body_markdown="## 结论\n算力需求高增。",
        key_numbers=[{"label": "数据中心收入", "value": "1200亿美元"}],
        evidence=[{"source": "sec-1", "kind": "filing", "title": "10-K", "url": "https://example.com"}],
    )
    restored = artifact_to_dict(art)
    ok5 = restored["artifact_type"] == "report" and restored["version"] >= 1
    checks.append(("结构化输出 artifact 契约", ok5, f"schema_v={restored.get('version')}"))

    # 6. Memory recall: BM25 ranks the relevant memory doc first.
    hits = recall(
        "喜欢成长股 高毛利率",
        build_chunks([("memory.md", "用户偏好成长股，重视毛利率。"), ("research.md", "NVDA 收入 880 亿。")]),
        top_k=1,
    )
    ok6 = bool(hits) and hits[0].source == "memory.md"
    checks.append(("记忆检索 recall（BM25 相关性）", ok6, hits[0].source if hits else "(no hit)"))

    # 7. Guardrails PII redaction masks an email + ID while keeping domain.
    from src.tools.guardrails.pii import redact_pii
    redacted = redact_pii("联系 aa12345678@qq.com 或 110101199001011234")
    ok7 = "aa12345678" not in redacted and "@qq.com" in redacted
    checks.append(("Guardrails PII 打码", ok7, redacted))

    # Report.
    all_ok = True
    for name, ok, detail in checks:
        all_ok = all_ok and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    print()
    print(f"模拟全链路: {sum(1 for _, ok, _ in checks if ok)}/{len(checks)} 通过")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))