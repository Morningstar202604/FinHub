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


def _run_finance_committee_suite() -> tuple[int, int, list[Result]]:
    """Lock the shipped meeting's dispatch contract, offline.

    Every dispatch the finance_committee script makes must clear the live
    server-side validation (known role, schema shape), and a well-formed
    result for that schema must round-trip through the same parser the
    driver applies. A regression that renames a role or widens a schema
    field breaks this before it ever reaches a live run.
    """
    import json
    from pathlib import Path

    from ptc_agent.agent.middleware.background_subagent.workflow.prebuilt import (
        PrebuiltWorkflowRegistry,
    )
    from ptc_agent.agent.subagents.builtins import BUILTIN_SUBAGENTS
    from src.config.models import WorkflowOrchestrationConfig
    from ptc_agent.agent.middleware.background_subagent.workflow.validation import (
        parse_schema_result,
        validate_dispatch,
    )

    registry = PrebuiltWorkflowRegistry(Path(__file__).resolve().parents[1])
    source = registry.get("finance_committee")
    if source is None:
        return 0, 1, [(False, "shipped finance_committee workflow not found")]

    caps = WorkflowOrchestrationConfig()
    known = sorted(BUILTIN_SUBAGENTS)

    # Schemas mirror the shipped script's dispatch literals — statement and
    # cross ride the script's named constants, gate/minutes/verification are
    # inlined at their dispatch. Kept here on purpose: this suite is the
    # contract lock, so it owns the shapes it asserts.
    STATEMENT_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["department", "position", "key_numbers", "risks", "recommendations", "assumptions"],
        "properties": {
            "department": {"type": "string"},
            "position": {"type": "string"},
            "key_numbers": {"type": "array"},
            "risks": {"type": "array"},
            "recommendations": {"type": "array"},
            "assumptions": {"type": "array"},
        },
    }
    CROSS_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["challenger", "challenges", "agreements"],
        "properties": {
            "challenger": {"type": "string"},
            "challenges": {"type": "array"},
            "agreements": {"type": "array"},
        },
    }
    GATE_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["verdict", "concerns", "conditions", "required_actions", "blocking_actions"],
        "properties": {
            "verdict": {"type": "string", "enum": ["approve", "approve_with_conditions", "reject"]},
            "concerns": {"type": "array"},
            "conditions": {"type": "array"},
            "required_actions": {"type": "array"},
            "blocking_actions": {"type": "array"},
        },
    }
    MINUTES_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "topic", "attendees", "missing_departments", "resolution",
            "dissent", "risk_gate", "actions", "financial_impact",
        ],
        "properties": {
            "topic": {"type": "string"},
            "attendees": {"type": "array"},
            "missing_departments": {"type": "array"},
            "resolution": {"type": "string"},
            "dissent": {"type": "array"},
            "risk_gate": {"type": "string"},
            "actions": {"type": "array"},
            "financial_impact": {"type": "string"},
        },
    }
    VERIFICATION_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["unverified_claims", "contradictions", "missing_conditions", "passed"],
        "properties": {
            "unverified_claims": {"type": "array"},
            "contradictions": {"type": "array"},
            "missing_conditions": {"type": "array"},
            "passed": {"type": "boolean"},
        },
    }

    DISPATCHES = [
        # (turn label, agentType, phase, schema, sample)
        ("statement", "accountant", "statements", STATEMENT_SCHEMA, {
            "department": "会计", "position": "结账已完成", "key_numbers": [],
            "risks": [], "recommendations": [], "assumptions": [],
        }),
        ("statement", "treasury", "statements", STATEMENT_SCHEMA, {
            "department": "资金", "position": "头寸充足", "key_numbers": [],
            "risks": [], "recommendations": [], "assumptions": [],
        }),
        ("statement", "tax-specialist", "statements", STATEMENT_SCHEMA, {
            "department": "税务", "position": "税负合规", "key_numbers": [],
            "risks": [], "recommendations": [], "assumptions": [],
        }),
        ("statement", "fp-analyst", "statements", STATEMENT_SCHEMA, {
            "department": "FP&A", "position": "指标达标", "key_numbers": [],
            "risks": [], "recommendations": [], "assumptions": [],
        }),
        ("statement", "internal-auditor", "statements", STATEMENT_SCHEMA, {
            "department": "内控审计", "position": "内控有效", "key_numbers": [],
            "risks": [], "recommendations": [], "assumptions": [],
        }),
        ("challenge", "fp-analyst", "cross-examination", CROSS_SCHEMA, {
            "challenger": "fp-analyst", "challenges": [], "agreements": [],
        }),
        ("risk gate", "internal-auditor", "risk-gate", GATE_SCHEMA, {
            "verdict": "approve", "concerns": [], "conditions": [],
            "required_actions": [], "blocking_actions": [],
        }),
        ("minutes", "fp-analyst", "minutes", MINUTES_SCHEMA, {
            "topic": "预算", "attendees": [], "missing_departments": [],
            "resolution": "通过", "dissent": [], "risk_gate": "approve",
            "actions": [], "financial_impact": "未量化",
        }),
        ("verification", "general-purpose", "verification", VERIFICATION_SCHEMA, {
            "unverified_claims": [], "contradictions": [],
            "missing_conditions": [], "passed": True,
        }),
    ]

    results: list[Result] = []
    for label, role, phase, schema, sample in DISPATCHES:
        case_name = f"{role} · {label}"
        # The script labels children '<turn> · <role>' for statement/challenge
        # and the bare turn word otherwise.
        turn_word = label
        dispatch_label = f"{turn_word} · {role}" if turn_word in ("statement", "challenge") else turn_word

        opts: dict = {"agentType": role, "label": dispatch_label, "phase": phase}
        if schema is not None:
            opts["schema"] = schema
        try:
            rec = validate_dispatch(
                prompt=f"{label} 派发测试",
                opts=opts,
                known_subagent_types=known,
                default_subagent_type="general-purpose",
                caps=caps,
            )
        except Exception as exc:  # noqa: BLE001 - surface any contract break
            results.append((False, f"{case_name!r}: dispatch rejected ({exc})"))
            continue

        ok = rec["subagent_type"] == role
        detail = f"{case_name!r}: agentType={rec['subagent_type']}"

        if schema is not None:
            valid, parsed, reason = parse_schema_result(
                json.dumps(sample, ensure_ascii=False), schema
            )
            if not valid:
                ok = False
                detail += f"; sample rejected ({reason})"
            else:
                detail += f"; sample parsed (keys={len(parsed) if isinstance(parsed, dict) else 'scalar'})"

        # The script's source must still name this role — a rename is a break.
        if f"'{role}'" not in source and f'"{role}"' not in source:
            ok = False
            detail += f"; role '{role}' no longer in shipped script"

        results.append((ok, detail))

    passed = sum(1 for ok, _ in results if ok)
    return passed, len(results), results


RUNNERS: dict[str, Callable[[], tuple[int, int, list[Result]]]] = {
    "intent": _run_intent_suite,
    "auditor": _run_auditor_suite,
    "research_fallback": _run_research_fallback_suite,
    "finance_committee": _run_finance_committee_suite,
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