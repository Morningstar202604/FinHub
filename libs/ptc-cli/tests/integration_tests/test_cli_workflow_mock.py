"""Integration tests for CLI workflows (API mode)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ptc_cli.commands.slash import handle_command
from ptc_cli.core.state import SessionState
from ptc_cli.display.tokens import TokenTracker
from ptc_cli.input.file_mentions import parse_file_mentions


@pytest.fixture
def token_tracker():
    tracker = Mock(spec=TokenTracker)
    tracker.display = Mock()
    return tracker


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.base_url = "http://localhost:8000"
    client.user_id = "cli_user"
    client.workspace_id = "ws-123"
    client.thread_id = "t-123"

    client.get_workspace = AsyncMock(return_value={"workspace_id": "ws-123", "status": "running"})
    client.start_workspace = AsyncMock(return_value={})

    client.list_workspace_files = AsyncMock(return_value=["file1.txt", "src/file2.py"])
    client.read_workspace_file = AsyncMock(return_value={"content": "File content here"})
    client.download_workspace_file = AsyncMock(return_value=b"bytes")

    return client


class TestSlashCommandWorkflow:
    @pytest.mark.asyncio
    async def test_help_command(self, mock_client, token_tracker):
        state = SessionState()
        with patch("ptc_cli.commands.slash.show_help") as show_help:
            result = await handle_command("/help", mock_client, token_tracker, state)
        assert result == "handled"
        show_help.assert_called_once()

    @pytest.mark.asyncio
    async def test_tokens_command(self, mock_client, token_tracker):
        state = SessionState()
        result = await handle_command("/tokens", mock_client, token_tracker, state)
        assert result == "handled"
        token_tracker.display.assert_called_once()

    @pytest.mark.asyncio
    async def test_exit_commands(self, mock_client, token_tracker):
        state = SessionState()
        assert await handle_command("/exit", mock_client, token_tracker, state) == "exit"
        assert await handle_command("/q", mock_client, token_tracker, state) == "exit"

    @pytest.mark.asyncio
    async def test_unknown_command(self, mock_client, token_tracker):
        state = SessionState()
        result = await handle_command("/unknown", mock_client, token_tracker, state)
        assert result == "handled"

    @pytest.mark.asyncio
    async def test_case_insensitive_commands(self, mock_client, token_tracker):
        state = SessionState()
        assert await handle_command("/HELP", mock_client, token_tracker, state) == "handled"
        assert await handle_command("/Help", mock_client, token_tracker, state) == "handled"
        assert await handle_command("/EXIT", mock_client, token_tracker, state) == "exit"


class TestFileMentionParsingWorkflow:
    def test_parse_single_file_mention(self):
        text = "Read @file.txt and analyze it"
        original_text, paths = parse_file_mentions(text)
        assert original_text == text
        assert paths == ["file.txt"]

    def test_parse_multiple_file_mentions(self):
        text = "Compare @file1.txt with @file2.txt and @file3.txt"
        original_text, paths = parse_file_mentions(text)
        assert original_text == text
        assert paths == ["file1.txt", "file2.txt", "file3.txt"]

    def test_parse_file_with_path(self):
        text = "Read @src/main.py"
        original_text, paths = parse_file_mentions(text)
        assert original_text == text
        assert paths == ["src/main.py"]

    def test_parse_file_with_spaces(self):
        text = r"Read @my\ file.txt"
        original_text, paths = parse_file_mentions(text)
        assert original_text == text
        assert paths == ["my file.txt"]

    def test_parse_no_file_mentions(self):
        text = "This is just regular text"
        original_text, paths = parse_file_mentions(text)
        assert original_text == text
        assert paths == []
