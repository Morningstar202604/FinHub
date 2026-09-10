"""
LangChain tool wrappers for research QA (ROADMAP M2-D).

Exposes the deterministic self-verification auditor to the agent so every
report-stage deliverable can run a number / citation / conflict pass before
it ships — the code-level half of the evidence-check gate.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from .auditor import AuditReport, audit_report


@tool(response_format="content_and_artifact")
async def audit_research_numbers(
    text: str,
    config: RunnableConfig,
    known_data: dict[str, float] | None = None,
    provenance_sources: list[str] | None = None,
    tolerance_pct: float = 2.0,
) -> tuple[str, AuditReport]:
    """Verify the numbers, citations, and internal consistency of a research write-up before delivery.

    Flags three classes of credibility failures:
    - number/benchmark mismatch (delta > tolerance),
    - key factual claims with no provenance source nearby,
    - the same metric appearing with two materially different values.

    Args:
        text: The research report / memo / analysis body to audit.
        known_data: Optional map of metric name -> expected value
            (e.g. {"营收": 18000.0} in USD-millions or raw units) to
            cross-check the report against. Supplying the numbers you
            pulled from data sources makes the check strongest.
        provenance_sources: Optional list of source ids already recorded for
            this work (SEC filing ids, provider keys, URLs). Claims that
            reference none of these are flagged as uncited.
        tolerance_pct: Maximum accepted relative delta (%) per number.
    """
    report = audit_report(
        text,
        known_data=known_data,
        provenance_sources=list(provenance_sources or ()),
        num_tolerance_pct=tolerance_pct,
    )
    summary_lines = []
    for f in report.findings:
        summary_lines.append(f"[{f.level}] {f.kind}: {f.message}")
    if not summary_lines:
        summary_lines.append("审校通过：未发现数值/引用/矛盾问题。")
    content = "\n".join(summary_lines)
    return content, report


__all__ = ["audit_research_numbers"]