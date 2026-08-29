"""Mocked integration tests for CLI-specific UX behavior (API mode)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestFileMentionsIntegration:
    """Test @ file mention parsing."""

    @pytest.mark.asyncio
    async def test_file_mention_parsing(self):
        from ptc_cli.input.file_mentions import parse_file_mentions

        text = "Read @code/main.py and analyze @data/input.csv"
        original, paths = parse_file_mentions(text)

        assert original == text
        assert paths == ["code/main.py", "data/input.csv"]

    @pytest.mark.asyncio
    async def test_file_mention_escaped_spaces(self):
        from ptc_cli.input.file_mentions import parse_file_mentions

        text = r"Read @my\ file.txt"
        _, paths = parse_file_mentions(text)

        assert paths == ["my file.txt"]


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.base_url = "http://localhost:8000"
    client.user_id = "cli_user"
    client.workspace_id = "ws-123"
    client.thread_id = "t-123"

    client.get_workspace = AsyncMock(return_value={"workspace_id": "ws-123", "status": "running"})
    client.start_workspace = AsyncMock(return_value={})

    client.list_workspace_files = AsyncMock(return_value=["README.md", "src/main.py"])
    client.read_workspace_file = AsyncMock(return_value={"content": "hello"})
    client.download_workspace_file = AsyncMock(return_value=b"bytes")

    return client


class TestSlashCommandsFilesIntegration:
    @pytest.mark.asyncio
    async def test_files_command_lists_files(self, mock_client):
        from ptc_cli.commands.slash import handle_command
        from ptc_cli.core.state import SessionState

        token_tracker = Mock()
        session_state = SessionState()

        with patch("ptc_cli.commands.slash.console"):
            result = await handle_command("/files", mock_client, token_tracker, session_state)

        assert result == "handled"
        mock_client.list_workspace_files.assert_awaited_once_with(include_system=False)

    @pytest.mark.asyncio
    async def test_files_all_includes_system(self, mock_client):
        from ptc_cli.commands.slash import handle_command
        from ptc_cli.core.state import SessionState

        token_tracker = Mock()
        session_state = SessionState()

        with patch("ptc_cli.commands.slash.console"):
            result = await handle_command("/files all", mock_client, token_tracker, session_state)

        assert result == "handled"
        mock_client.list_workspace_files.assert_awaited_once_with(include_system=True)


class TestSlashCommandsViewIntegration:
    @pytest.mark.asyncio
    async def test_view_reads_text(self, mock_client):
        from ptc_cli.commands.slash import handle_command
        from ptc_cli.core.state import SessionState

        token_tracker = Mock()
        session_state = SessionState()

        mock_client.read_workspace_file = AsyncMock(return_value={"content": "def hi():\n    return 1"})

        with patch("ptc_cli.commands.slash.console"):
            result = await handle_command("/view src/main.py", mock_client, token_tracker, session_state)

        assert result == "handled"
        mock_client.read_workspace_file.assert_awaited()

    @pytest.mark.asyncio
    async def test_view_downloads_binary(self, mock_client, tmp_path, monkeypatch):
        from ptc_cli.commands.slash import handle_command
        from ptc_cli.core.state import SessionState

        token_tracker = Mock()
        session_state = SessionState()

        mock_client.download_workspace_file = AsyncMock(return_value=b"fake-image")
        monkeypatch.setattr("pathlib.Path.cwd", lambda: tmp_path)

        with patch("ptc_cli.commands.slash.console"):
            result = await handle_command("/view image.png", mock_client, token_tracker, session_state)

        assert result == "handled"
        assert (tmp_path / "image.png").exists()


class TestSlashCommandsDownloadIntegration:
    @pytest.mark.asyncio
    async def test_download_saves_file(self, mock_client, tmp_path, monkeypatch):
        from ptc_cli.commands.slash import handle_command
        from ptc_cli.core.state import SessionState

        token_tracker = Mock()
        session_state = SessionState()

        mock_client.download_workspace_file = AsyncMock(return_value=b"downloaded")

        local_dest = tmp_path / "out.bin"
        with patch("ptc_cli.commands.slash.console"):
            result = await handle_command(f"/download results/x.bin {local_dest}", mock_client, token_tracker, session_state)

        assert result == "handled"
        assert local_dest.exists()
        assert local_dest.read_bytes() == b"downloaded"


class TestSlashCommandsCopyIntegration:
    @pytest.mark.asyncio
    async def test_copy_to_clipboard(self, mock_client):
        from ptc_cli.commands.slash import handle_command
        from ptc_cli.core.state import SessionState

        token_tracker = Mock()
        session_state = SessionState()

        mock_client.read_workspace_file = AsyncMock(return_value={"content": "copy me"})

        copied = []

        with patch("ptc_cli.commands.slash.console"), patch("pyperclip.copy", side_effect=lambda x: copied.append(x)):
            result = await handle_command("/copy src/main.py", mock_client, token_tracker, session_state)

        assert result == "handled"
        assert copied == ["copy me"]
