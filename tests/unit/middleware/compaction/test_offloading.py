"""Tests for the compaction offloading helpers.

Focuses on the `overwrite=True` contract with `SandboxBackend.awrite` —
a regression dropping that kwarg would break compaction mid-conversation
once a message id or tool_call_id is retried (since protocol-default
`awrite` is create-only).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from ptc_agent.agent.middleware.compaction.offloading import (
    aoffload_to_backend,
    aoffload_truncated_args,
)


def _make_backend(*, error: str | None = None) -> AsyncMock:
    backend = AsyncMock()
    result = MagicMock()
    result.error = error
    result.path = None if error else "/some/path"
    backend.awrite = AsyncMock(return_value=result)
    return backend


class TestAoffloadToBackend:
    @pytest.mark.asyncio
    async def test_passes_overwrite_true_to_awrite(self):
        """Regression guard: awrite must be called with overwrite=True."""
        backend = _make_backend()
        msg = HumanMessage(content="hello", id="m1")
        with patch(
            "ptc_agent.agent.middleware.compaction.offloading.get_thread_id",
            return_value="thread123",
        ):
            result = await aoffload_to_backend(backend, [msg])
        assert result == ".agents/threads/thread123"
        assert backend.awrite.call_count == 1
        call = backend.awrite.call_args
        assert call.kwargs.get("overwrite") is True
        # Path key should contain message id
        assert "evicted_m1.md" in call.args[0]

    @pytest.mark.asyncio
    async def test_returns_none_when_backend_is_none(self):
        result = await aoffload_to_backend(None, [HumanMessage(content="x", id="m1")])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_messages(self):
        backend = _make_backend()
        result = await aoffload_to_backend(backend, [])
        assert result is None
        backend.awrite.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_prior_summary_messages(self):
        """Prior summary messages (lc_source=summarization) must be filtered."""
        backend = _make_backend()
        summary = HumanMessage(
            content="summary", id="s1", additional_kwargs={"lc_source": "summarization"}
        )
        result = await aoffload_to_backend(backend, [summary])
        assert result is None
        backend.awrite.assert_not_called()

    @pytest.mark.asyncio
    async def test_awrite_error_is_logged_not_raised(self, caplog):
        backend = _make_backend(error="backend failure")
        with patch(
            "ptc_agent.agent.middleware.compaction.offloading.get_thread_id",
            return_value="t",
        ):
            result = await aoffload_to_backend(backend, [HumanMessage(content="x", id="m1")])
        # No writes succeeded → returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_awrite_none_result_is_handled(self):
        """Defensive: backend.awrite returning None must not crash."""
        backend = AsyncMock()
        backend.awrite = AsyncMock(return_value=None)
        result = await aoffload_to_backend(backend, [HumanMessage(content="x", id="m1")])
        assert result is None

    @pytest.mark.asyncio
    async def test_ai_message_tool_calls_included_in_header(self):
        backend = _make_backend()
        ai = AIMessage(
            content="thinking",
            id="m1",
            tool_calls=[{"id": "c1", "name": "Search", "args": {}}],
        )
        with patch(
            "ptc_agent.agent.middleware.compaction.offloading.get_thread_id",
            return_value="t",
        ):
            await aoffload_to_backend(backend, [ai])
        call = backend.awrite.call_args
        # Content (second positional arg) should carry the tool info marker
        content = call.args[1]
        assert "Search" in content


class TestAoffloadTruncatedArgs:
    @pytest.mark.asyncio
    async def test_passes_overwrite_true(self):
        backend = _make_backend()
        originals = {"call1": {"name": "Search", "args": {"query": "x"}}}
        with patch(
            "ptc_agent.agent.middleware.compaction.offloading.get_thread_id",
            return_value="t",
        ):
            await aoffload_truncated_args(backend, originals)
        assert backend.awrite.call_count == 1
        assert backend.awrite.call_args.kwargs.get("overwrite") is True

    @pytest.mark.asyncio
    async def test_noop_when_backend_none(self):
        await aoffload_truncated_args(None, {"c1": {"name": "X", "args": {}}})

    @pytest.mark.asyncio
    async def test_noop_when_no_originals(self):
        backend = _make_backend()
        await aoffload_truncated_args(backend, {})
        backend.awrite.assert_not_called()

    @pytest.mark.asyncio
    async def test_path_includes_tool_call_id(self):
        backend = _make_backend()
        with patch(
            "ptc_agent.agent.middleware.compaction.offloading.get_thread_id",
            return_value="t",
        ):
            await aoffload_truncated_args(
                backend, {"xyz789": {"name": "Search", "args": {}}}
            )
        path = backend.awrite.call_args.args[0]
        assert "truncated_args_xyz789.md" in path

    @pytest.mark.asyncio
    async def test_error_is_logged_not_raised(self):
        """Errors from backend.awrite must be swallowed."""
        backend = _make_backend(error="disk full")
        with patch(
            "ptc_agent.agent.middleware.compaction.offloading.get_thread_id",
            return_value="t",
        ):
            # Must not raise
            await aoffload_truncated_args(
                backend, {"c1": {"name": "X", "args": {"k": "v"}}}
            )
