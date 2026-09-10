"""Evals harness (ROADMAP M2-G) — offline agent-behavior evaluation.

Runs scenario suites against the deterministic components (intent router,
research auditor, deep-research fallback chain) and emits a markdown report.
Stdlib only; no external LLM required for the locked suites.

Usage (from repo root):
    uv run python -m evals run intent       # one suite
    uv run python -m evals run all          # every suite
    uv run python -m evals run all --json   # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .scenarios import SUITES

Result = tuple[bool, str]


def _run_intent_suite() -> tuple[int, int, list[Result]]:
    from src.server.services.router.intent import classify_intent

    results: list[Result] = []
    for case in SUITES["intent"]:
        text: str = case["text"]
        has_ws: bool = case.get("has_workspace", False)
        plan_mode: bool = case.get("plan_mode", False)
        expected: str = case["expected"]
        got = classify_intent(text, has_workspace=has_ws, plan_mode=plan_mode)
        ok = got.mode == expected
        results.append((ok, f"{case.get('name', text[:20])!r}: want {expected}, got {got.mode} ({got.reason})"))
    passed = sum(1 for ok, _ in results if ok)
    return passed, len(results), results


def _run_auditor_suite() -> tuple[int, int, list[Result]]:
    from src.tools.research_qa.auditor import audit_report

    results: list[Result] = []
    for case in SUITES["auditor"]:
        text: str = case["text"]
        expected_kind: str = case["expect"]  # "error" | "pass"
        known = case.get("known_data")
        provenance = case.get("provenance_sources")
        report = audit_report(text, known_data=known, provenance_sources=provenance or ())
        if expected_kind == "error":
            ok = not report.passed
            detail = f"{len(report.errors())} error(s): {'; '.join(f.message for f in report.errors()[:2])}"
        else:
            ok = report.passed
            detail = "no errors"
        results.append((ok, f"{case.get('name', text[:20])!r}: expect {expected_kind} -> {detail}"))
    passed = sum(1 for ok, _ in results if ok)
    return passed, len(results), results


def _run_research_fallback_suite() -> tuple[int, int, list[Result]]:
    import asyncio
    from unittest.mock import patch

    from src.tools.web.tools.deep_research import run_deep_research
    from src.tools.web.types import (
        ResearchCitation,
        ResearchResult,
        WebError,
        WebErrorType,
        WebToolError,
    )

    results: list[Result] = []

    async def _case_empty_chain() -> Result:
        with patch("src.tools.web.tools.deep_research.research_providers", return_value=()):
            content, artifact = await run_deep_research("q")
        ok = artifact["provider"] == "none" and "暂不可用" in content
        return ok, f"empty provider chain -> provider={artifact['provider']}"

    async def _case_retryable_fallback() -> Result:
        def _fake_run(req, provider, level=None):
            if provider == "exa":
                raise WebToolError(WebError(type=WebErrorType.RATE_LIMITED, message="quota", retryable=True))
            return ResearchResult(provider="parallel", report="ok report",
                                  citations=[ResearchCitation(url="https://x", title="X")])

        with (
            patch("src.tools.web.tools.deep_research.research_providers", return_value=("exa", "parallel")),
            patch("src.tools.web.tools.deep_research.run_research", side_effect=_fake_run),
        ):
            _content, artifact = await run_deep_research("q")
        ok = artifact["provider"] == "parallel" and artifact["citations"]
        return ok, f"retryable fallback -> provider={artifact['provider']} citations={len(artifact['citations'])}"

    async def _case_fatal_stops() -> Result:
        def _fake_run(req, provider, level=None):
            raise WebToolError(WebError(type=WebErrorType.NOT_FOUND, message="nope", retryable=False))

        with (
            patch("src.tools.web.tools.deep_research.research_providers", return_value=("exa", "parallel")),
            patch("src.tools.web.tools.deep_research.run_research", side_effect=_fake_run),
        ):
            _content, artifact = await run_deep_research("q")
        ok = artifact["error"] is not None
        return ok, f"fatal error stops chain -> provider={artifact['provider']} error={'yes' if artifact['error'] else 'no'}"

    tests: list[tuple[str, Callable[[], Any]]] = [
        ("empty_chain", _case_empty_chain),
        ("retryable_fallback", _case_retryable_fallback),
        ("fatal_stops", _case_fatal_stops),
    ]
    for name, fn in tests:
        result = asyncio.run(fn())
        results.append(result)
    passed = sum(1 for ok, _ in results if ok)
    return passed, len(results), results


RUNNERS: dict[str, Callable[[], tuple[int, int, list[Result]]]] = {
    "intent": _run_intent_suite,
    "auditor": _run_auditor_suite,
    "research_fallback": _run_research_fallback_suite,
}


def run_suite(name: str) -> tuple[str, int, int, list[Result]]:
    runner = RUNNERS[name]
    passed, total, results = runner()
    return name, passed, total, results


def run_all(json_out: bool = False) -> int:
    summary: dict[str, Any] = {"suites": {}, "passed": 0, "total": 0, "ok": True}
    lines: list[str] = []
    started = time.time()
    for name in RUNNERS:
        _suite_name, passed, total, results = run_suite(name)
        summary["suites"][name] = {"passed": passed, "total": total}
        summary["passed"] += passed
        summary["total"] += total
        summary["ok"] = summary["ok"] and passed == total
        if not json_out:
            lines.append(f"## {name} — {passed}/{total} passed")
            for ok, detail in results:
                lines.append(f"- [{'PASS' if ok else 'FAIL'}] {detail}")
            lines.append("")
    summary["duration_ms"] = int((time.time() - started) * 1000)

    if json_out:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        report = "\n".join(lines)
        report += f"\n**总评: {summary['passed']}/{summary['total']} 通过 ({summary['duration_ms']} ms) — {'✅ ALL GREEN' if summary['ok'] else '❌ HAS FAILURES'}**\n"
        out_path = Path(__file__).resolve().parents[1] / "evals" / "runs" / "latest.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")

    # Machine-readable summary (M4-4 dashboard source) — written on every run
    # regardless of --json so the read-only /api/v1/evals/report endpoint can
    # serve it to the frontend without re-running the harness. Body includes
    # per-suite detail lines when captured above.
    json_path = Path(__file__).resolve().parents[1] / "evals" / "runs" / "latest.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    detail: list[dict] = []
    if not json_out:
        for line in lines:
            if line.startswith("- ["):
                detail.append({"line": line})
    summary["detail"] = detail
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if json_out:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["ok"] else 1
    print(report)

    return 0 if summary["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals", description=__doc__)
    parser.add_argument("suite", nargs="?", default="all", help="suite name or 'all'")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    argv = list(argv) if argv is not None else sys.argv[1:]
    if argv and argv[0] == "run":
        argv = argv[1:]  # accept both `evals run all` and `evals all`
    args = parser.parse_args(argv)

    if args.suite == "all":
        return run_all(json_out=args.json)
    if args.suite not in RUNNERS:
        print(f"unknown suite {args.suite!r}; available: {', '.join(RUNNERS)}", file=sys.stderr)
        return 2
    name, passed, total, results = run_suite(args.suite)
    for ok, detail in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {detail}")
    print(f"\n{name}: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())