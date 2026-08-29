"""Tests for the WorkspaceContextMiddleware.

Covers YAML front matter parsing, content block appending, agent.md
injection into system messages, and truncation of large agent.md content.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import SystemMessage

from ptc_agent.agent.middleware.workspace_context import (
    MAX_AGENT_MD_SIZE,
    WorkspaceContextMiddleware,
    _append_content_block,
    _parse_yaml_front_matter,
)


# ---------------------------------------------------------------------------
# Tests for _parse_yaml_front_matter
# ---------------------------------------------------------------------------


class TestParseYamlFrontMatter:
    """Tests for _parse_yaml_front_matter."""

    def test_valid_front_matter(self):
        content = "---\nworkspace_name: My Workspace\ndescription: A test\n---\n# Body"
        result = _parse_yaml_front_matter(content)
        assert result is not None
        assert result["workspace_name"] == "My Workspace"
        assert result["description"] == "A test"

    def test_no_front_matter(self):
        content = "# Just a heading\nSome text"
        result = _parse_yaml_front_matter(content)
        assert result is None

    def test_missing_closing_delimiter(self):
        content = "---\nkey: value\nno closing"
        result = _parse_yaml_front_matter(content)
        assert result is None

    def test_empty_front_matter(self):
        content = "---\n---\n# Body"
        result = _parse_yaml_front_matter(content)
        assert result is not None
        assert result == {}

    def test_front_matter_with_empty_lines(self):
        content = "---\nkey: value\n\nanother: data\n---\n# Body"
        result = _parse_yaml_front_matter(content)
        assert result is not None
        assert result["key"] == "value"
        assert result["another"] == "data"


# ---------------------------------------------------------------------------
# Tests for _append_content_block
# ---------------------------------------------------------------------------


class TestAppendContentBlock:
    """Tests for _append_content_block."""

    def test_append_to_none(self):
        result = _append_content_block(None, "new block")
        assert isinstance(result, SystemMessage)

    def test_append_to_existing(self):
        existing = SystemMessage(content="initial")
        result = _append_content_block(existing, "appended")
        assert isinstance(result, SystemMessage)
        # Content blocks should contain the appended text
        blocks = result.content
        assert any("appended" in str(b) for b in blocks) if isinstance(blocks, list) else "appended" in str(blocks)


# ---------------------------------------------------------------------------
# Tests for WorkspaceContextMiddleware
# ---------------------------------------------------------------------------


def _make_session(agent_md: str | None = None, conversation_id: str = "ws-123") -> MagicMock:
    """Create a mock Session object."""
    session = MagicMock()
    session.get_agent_md = AsyncMock(return_value=agent_md)
    session.conversation_id = conversation_id
    return session


class TestGetWorkspaceContextBlock:
    """Tests for _get_workspace_context_block."""

    @pytest.mark.asyncio
    async def test_returns_agentmd_content(self):
        session = _make_session(agent_md="# My workspace\nSome notes")
        mw = WorkspaceContextMiddleware(session=session)
        block = await mw._get_workspace_context_block()
        assert "<agentmd" in block
        assert "My workspace" in block

    @pytest.mark.asyncio
    async def test_returns_placeholder_when_no_agentmd(self):
        session = _make_session(agent_md=None)
        mw = WorkspaceContextMiddleware(session=session)
        block = await mw._get_workspace_context_block()
        assert "No agent.md exists yet" in block

    @pytest.mark.asyncio
    async def test_truncates_large_agentmd(self):
        large_content = "x" * (MAX_AGENT_MD_SIZE + 1000)
        session = _make_session(agent_md=large_content)
        mw = WorkspaceContextMiddleware(session=session)
        block = await mw._get_workspace_context_block()
        assert "[... truncated ...]" in block

    @pytest.mark.asyncio
    async def test_front_matter_change_triggers_sync(self):
        agent_md = "---\nworkspace_name: Updated\n---\n# Content"
        session = _make_session(agent_md=agent_md)
        mw = WorkspaceContextMiddleware(session=session)

        def _close_coro(coro):
            """Prevent 'coroutine was never awaited' by closing it."""
            coro.close()
            return MagicMock()

        with patch(
            "ptc_agent.agent.middleware.workspace_context.asyncio.create_task",
            side_effect=_close_coro,
        ) as mock_task:
            await mw._get_workspace_context_block()
            mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_same_front_matter_does_not_retrigger_sync(self):
        agent_md = "---\nworkspace_name: Same\n---\n# Content"
        session = _make_session(agent_md=agent_md)
        mw = WorkspaceContextMiddleware(session=session)

        def _close_coro(coro):
            """Prevent 'coroutine was never awaited' by closing it."""
            coro.close()
            return MagicMock()

        with patch(
            "ptc_agent.agent.middleware.workspace_context.asyncio.create_task",
            side_effect=_close_coro,
        ) as mock_task:
            # First call triggers sync
            await mw._get_workspace_context_block()
            assert mock_task.call_count == 1
            # Second call with same content should not trigger
            await mw._get_workspace_context_block()
            assert mock_task.call_count == 1


class TestAwrapModelCall:
    """Tests for awrap_model_call system message injection."""

    @pytest.mark.asyncio
    async def test_injects_context_into_system_message(self):
        session = _make_session(agent_md="# Workspace notes")
        mw = WorkspaceContextMiddleware(session=session)

        # Create a mock request with override method
        mock_request = MagicMock()
        modified_request = MagicMock()
        mock_request.override = MagicMock(return_value=modified_request)
        mock_request.system_message = None

        handler = AsyncMock(return_value="model_response")
        result = await mw.awrap_model_call(mock_request, handler)

        # override should have been called with a new system message
        mock_request.override.assert_called_once()
        call_kwargs = mock_request.override.call_args
        assert "system_message" in call_kwargs.kwargs
        new_sys = call_kwargs.kwargs["system_message"]
        assert isinstance(new_sys, SystemMessage)

        # handler should have been called with modified request
        handler.assert_called_once_with(modified_request)
