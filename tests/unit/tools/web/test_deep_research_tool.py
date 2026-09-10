"""Unit tests for the deep research tool binding (ROADMAP M2-A).

The provider adapters themselves are live (network) code and are covered by
integration tests; here we lock the tool shell's provider-chain behavior with
mocked adapters.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.tools.web.tools.deep_research import _provider_chain, run_deep_research
from src.tools.web.types import (
    ResearchCitation,
    ResearchResult,
    WebError,
    WebErrorType,
    WebToolError,
)


def test_provider_chain_lists_only_available() -> None:
    with patch("src.tools.web.tools.deep_research.research_providers", return_value=("exa", "tavily")):
        assert _provider_chain() == ["exa", "tavily"]


def test_empty_provider_chain_returns_graceful_message() -> None:
    with patch("src.tools.web.tools.deep_research.research_providers", return_value=()):
        content, artifact = _run("any question")
    assert "暂不可用" in content
    assert artifact["provider"] == "none"


def test_success_returns_report_and_citations() -> None:
    fake_result = ResearchResult(
        provider="tavily",
        report="# 综述\n结论内容",
        citations=[ResearchCitation(url="https://example.com/a", title="A")],
        request_id="r-1",
        model="m",
    )

    async def _fake_run(req, provider, level=None):
        return fake_result

    with (
        patch("src.tools.web.tools.deep_research.research_providers", return_value=("tavily",)),
        patch("src.tools.web.tools.deep_research.run_research", side_effect=_fake_run),
    ):
        content, artifact = _run("行业综述")
    assert "引用来源" in content
    assert artifact["provider"] == "tavily"
    assert artifact["citations"][0]["url"] == "https://example.com/a"


def test_retryable_failure_falls_through_to_next_provider() -> None:
    def _fake_run(req, provider, level=None):
        if provider == "exa":
            raise WebToolError(
                WebError(type=WebErrorType.RATE_LIMITED, message="quota", retryable=True)
            )
        return ResearchResult(provider="parallel", report="ok report", citations=[])

    with (
        patch("src.tools.web.tools.deep_research.research_providers", return_value=("exa", "parallel")),
        patch("src.tools.web.tools.deep_research.run_research", side_effect=_fake_run),
    ):
        _content, artifact = _run("q")
    assert artifact["provider"] == "parallel"
    assert "ok report" in artifact["report"]


def test_non_retryable_failure_stops_chain() -> None:
    def _fake_run(req, provider, level=None):
        raise WebToolError(WebError(type=WebErrorType.NOT_FOUND, message="nope", retryable=False))

    with (
        patch("src.tools.web.tools.deep_research.research_providers", return_value=("exa", "parallel")),
        patch("src.tools.web.tools.deep_research.run_research", side_effect=_fake_run),
    ):
        _content, artifact = _run("q")
    assert artifact["error"] is not None
    assert artifact["provider"] == ["exa", "parallel"]


def _run(query: str):
    """Invoke the core research loop with a fresh event loop."""
    return asyncio.run(run_deep_research(query))