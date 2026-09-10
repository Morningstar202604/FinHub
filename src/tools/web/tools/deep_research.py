"""
LangChain tool wrapper for deep research (ROADMAP M2-A).

Binds the provider-side research adapters (exa/tavily/parallel, normalized in
``research.py``) to the agent tool surface. Tries providers in registry order
and returns a synthesized report with citations — the self-serve "deep
research" mode of the web layer.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ..research import research_providers, run_research
from ..types import ResearchRequest, WebToolError

logger = logging.getLogger(__name__)


def _provider_chain() -> list[str]:
    """Provider names offering research, in adapter order."""
    return list(research_providers())


def _summarize_citations(result) -> str:
    """Render the citation list as a compact digest for the artifact."""
    lines = []
    for i, cite in enumerate(result.citations, start=1):
        lines.append(f"{i}. {cite.title or cite.url} — {cite.url}")
    return "\n".join(lines) if lines else "（无引用）"


async def run_deep_research(
    query: str,
    *,
    level: str | None = None,
    output_schema: dict[str, Any] | None = None,
    max_wait_seconds: float = 600.0,
    provider: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Core deep research logic — provider-chain loop (unit-testable)."""
    providers = [provider] if provider else _provider_chain()
    if not providers or not providers[0]:
        return (
            ("深度研究暂不可用：未配置支持 research 的搜索服务商。请配置 "
            "exa/tavily/parallel API key，或使用普通搜索。"),
            {"provider": "none", "citations": []},
        )

    last_error: str | None = None
    for cand in providers:
        try:
            req = ResearchRequest(
                query=query,
                output_schema=output_schema,
                max_wait_seconds=max_wait_seconds,
            )
            result = await run_research(req, cand, level=level)
            content = (
                f"# 深度研究结果（provider={cand}）\n\n"
                f"{result.report}\n\n## 引用来源\n{_summarize_citations(result)}"
            )
            artifact = {
                "provider": cand,
                "report": result.report,
                "citations": [
                    {
                        "url": c.url,
                        "title": c.title,
                        "confidence": c.confidence,
                    }
                    for c in result.citations
                ],
                "request_id": result.request_id,
                "model": result.model,
            }
            return content, artifact
        except WebToolError as exc:
            last_error = str(exc.error)
            if not exc.error.retryable:
                break
            logger.warning(f"research provider {cand} failed (retryable): {exc}")

    return (
        f"深度研究失败（已尝试 {', '.join(providers)}）：{last_error or '未知错误'}",
        {"provider": providers, "citations": [], "error": last_error},
    )


@tool(response_format="content_and_artifact")
async def deep_research(
    query: str,
    config: RunnableConfig,
    level: str | None = None,
    output_schema: dict[str, Any] | None = None,
    max_wait_seconds: float = 600.0,
) -> tuple[str, dict[str, Any]]:
    """Run a deep, multi-step web research task and return a synthesized report with citations.

    Use this when the question needs synthesis across many sources — an
    industry overview, a competitive landscape, a thesis validation survey —
    rather than a single lookup. The provider runs its own iterative research
    loop server-side and returns a cited report.

    Args:
        query: The research question or objective (e.g. "AI data center demand
            drivers and the TAM picture for 2026").
        level: Optional depth tier from the manifest ('quick'/'standard'/'deep'
            names vary by provider). None uses the provider default.
        output_schema: Optional JSON Schema for structured output where the
            provider supports it (dict, JSON-schema-encoded).
        max_wait_seconds: Max seconds to wait for the research run (default 600).
    """
    return await run_deep_research(
        query,
        level=level,
        output_schema=output_schema,
        max_wait_seconds=max_wait_seconds,
        provider=None,
    )


__all__ = ["deep_research", "research_providers", "run_deep_research", "run_research"]