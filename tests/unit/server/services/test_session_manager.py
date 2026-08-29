"""
Tests for SessionService and related classes.

Tests session lifecycle: creation, retrieval, metadata tracking,
idle cleanup, singleton pattern, shutdown, and SessionServiceProvider.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.session_manager import (
    SessionMetadata,
    SessionService,
    SessionServiceProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config():
    """Create a minimal mock AgentConfig."""
    config = MagicMock()
    config.to_core_config.return_value = MagicMock()
    config.skills = MagicMock(enabled=False)
    return config


def _make_mock_session(initialized=True, has_sandbox=True):
    session = MagicMock()
    session._initialized = initialized
    session.sandbox = MagicMock() if has_sandbox else None
    if has_sandbox:
        session.sandbox.sandbox_id = "sandbox-abc"
        session.sandbox.sync_sandbox_assets = AsyncMock()
    session.initialize = AsyncMock()
    session.stop = AsyncMock()
    session.cleanup = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# SessionMetadata
# ---------------------------------------------------------------------------

class TestSessionMetadata:
    """Test SessionMetadata dataclass."""

    def test_defaults(self):
        meta = SessionMetadata(workspace_id="ws-1")
        assert meta.workspace_id == "ws-1"
        assert meta.request_count == 0
        assert meta.sandbox_id is None
        assert isinstance(meta.created_at, datetime)
        assert isinstance(meta.last_active, datetime)

    def test_touch_increments_request_count(self):
        meta = SessionMetadata(workspace_id="ws-1")
        old_active = meta.last_active
        meta.touch()
        assert meta.request_count == 1
        assert meta.last_active >= old_active

    def test_touch_multiple_times(self):
        meta = SessionMetadata(workspace_id="ws-1")
        for _ in range(5):
            meta.touch()
        assert meta.request_count == 5


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    """Test SessionService singleton pattern."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    def test_get_instance_requires_config_on_first_call(self):
        with pytest.raises(ValueError, match="config is required"):
            SessionService.get_instance()

    def test_get_instance_creates_singleton(self):
        config = _make_config()
        instance = SessionService.get_instance(config=config)
        assert instance is not None
        assert isinstance(instance, SessionService)

    def test_get_instance_returns_same_instance(self):
        config = _make_config()
        first = SessionService.get_instance(config=config)
        second = SessionService.get_instance()
        assert first is second

    def test_reset_instance_clears_singleton(self):
        config = _make_config()
        SessionService.get_instance(config=config)
        SessionService.reset_instance()
        with pytest.raises(ValueError, match="config is required"):
            SessionService.get_instance()


# ---------------------------------------------------------------------------
# get_or_create_session
# ---------------------------------------------------------------------------

class TestGetOrCreateSession:
    """Test session creation and retrieval."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_creates_new_session_and_metadata(self, mock_sm):
        ws_id = str(uuid.uuid4())
        mock_session = _make_mock_session(initialized=False)
        mock_sm.get_session.return_value = mock_session

        config = _make_config()
        service = SessionService(config)

        result = await service.get_or_create_session(ws_id)

        assert result is mock_session
        mock_session.initialize.assert_awaited_once()
        assert ws_id in service._metadata
        assert service._metadata[ws_id].request_count == 1

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_returns_existing_session(self, mock_sm):
        ws_id = str(uuid.uuid4())
        mock_session = _make_mock_session(initialized=True)
        mock_sm.get_session.return_value = mock_session

        config = _make_config()
        service = SessionService(config)
        service._metadata[ws_id] = SessionMetadata(workspace_id=ws_id)

        result = await service.get_or_create_session(ws_id)

        assert result is mock_session
        # Already initialized, so initialize should not be called
        mock_session.initialize.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------

class TestGetSession:
    """Test getting existing sessions."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_get_session_returns_initialized(self, mock_sm):
        ws_id = str(uuid.uuid4())
        mock_session = _make_mock_session(initialized=True)
        mock_sm.get_session.return_value = mock_session

        config = _make_config()
        service = SessionService(config)
        service._metadata[ws_id] = SessionMetadata(workspace_id=ws_id)

        result = await service.get_session(ws_id)
        assert result is mock_session

    @pytest.mark.asyncio
    async def test_get_session_returns_none_if_no_metadata(self):
        config = _make_config()
        service = SessionService(config)

        result = await service.get_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_get_session_returns_none_if_not_initialized(self, mock_sm):
        ws_id = str(uuid.uuid4())
        mock_session = _make_mock_session(initialized=False)
        mock_sm.get_session.return_value = mock_session

        config = _make_config()
        service = SessionService(config)
        service._metadata[ws_id] = SessionMetadata(workspace_id=ws_id)

        result = await service.get_session(ws_id)
        assert result is None


# ---------------------------------------------------------------------------
# cleanup_session
# ---------------------------------------------------------------------------

class TestCleanupSession:
    """Test session cleanup."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_cleanup_removes_metadata_and_lock(self, mock_sm):
        ws_id = str(uuid.uuid4())
        mock_sm.cleanup_session = AsyncMock()

        config = _make_config()
        service = SessionService(config)
        service._metadata[ws_id] = SessionMetadata(workspace_id=ws_id)
        service._session_locks[ws_id] = asyncio.Lock()

        await service.cleanup_session(ws_id)

        assert ws_id not in service._metadata
        assert ws_id not in service._session_locks
        mock_sm.cleanup_session.assert_awaited_once_with(ws_id)


# ---------------------------------------------------------------------------
# cleanup_idle_sessions
# ---------------------------------------------------------------------------

class TestCleanupIdle:
    """Test idle session cleanup."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_cleanup_idle_removes_old_sessions(self, mock_sm):
        mock_sm.cleanup_session = AsyncMock()

        config = _make_config()
        service = SessionService(config, idle_timeout=1800)

        # Create an idle session with old timestamp
        ws_id = str(uuid.uuid4())
        meta = SessionMetadata(workspace_id=ws_id)
        meta.last_active = datetime.now(timezone.utc) - timedelta(hours=2)
        service._metadata[ws_id] = meta

        count = await service.cleanup_idle_sessions()

        assert count == 1
        assert ws_id not in service._metadata

    @pytest.mark.asyncio
    async def test_cleanup_idle_keeps_active_sessions(self):
        config = _make_config()
        service = SessionService(config, idle_timeout=1800)

        ws_id = str(uuid.uuid4())
        meta = SessionMetadata(workspace_id=ws_id)
        meta.last_active = datetime.now(timezone.utc)
        service._metadata[ws_id] = meta

        count = await service.cleanup_idle_sessions()

        assert count == 0
        assert ws_id in service._metadata


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------

class TestShutdown:
    """Test session service shutdown."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_shutdown_clears_state(self, mock_sm):
        mock_sm.stop_all = AsyncMock()

        config = _make_config()
        service = SessionService(config)
        service._metadata["ws-1"] = SessionMetadata(workspace_id="ws-1")
        service._session_locks["ws-1"] = asyncio.Lock()

        await service.shutdown()

        assert service._shutdown is True
        assert len(service._metadata) == 0
        assert len(service._session_locks) == 0
        mock_sm.stop_all.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.server.services.session_manager.SessionManager")
    async def test_shutdown_cancels_cleanup_task(self, mock_sm):
        mock_sm.stop_all = AsyncMock()

        config = _make_config()
        service = SessionService(config, cleanup_interval=1)

        await service.start_cleanup_task()
        assert service._cleanup_task is not None

        await service.shutdown()
        assert service._cleanup_task is None


# ---------------------------------------------------------------------------
# Utility methods
# ---------------------------------------------------------------------------

class TestUtilityMethods:
    """Test utility and stats methods."""

    def setup_method(self):
        SessionService.reset_instance()

    def teardown_method(self):
        SessionService.reset_instance()

    def test_get_active_sessions(self):
        config = _make_config()
        service = SessionService(config)
        service._metadata["ws-1"] = SessionMetadata(workspace_id="ws-1")
        service._metadata["ws-2"] = SessionMetadata(workspace_id="ws-2")

        result = service.get_active_sessions()
        assert set(result) == {"ws-1", "ws-2"}

    def test_get_session_count(self):
        config = _make_config()
        service = SessionService(config)
        assert service.get_session_count() == 0

        service._metadata["ws-1"] = SessionMetadata(workspace_id="ws-1")
        assert service.get_session_count() == 1

    def test_get_session_metadata(self):
        config = _make_config()
        service = SessionService(config)
        meta = SessionMetadata(workspace_id="ws-1")
        service._metadata["ws-1"] = meta

        assert service.get_session_metadata("ws-1") is meta
        assert service.get_session_metadata("ws-2") is None

    def test_get_stats(self):
        config = _make_config()
        service = SessionService(config)
        service._metadata["ws-1"] = SessionMetadata(workspace_id="ws-1")

        stats = service.get_stats()
        assert stats["active_sessions"] == 1
        assert stats["idle_timeout"] == 1800
        assert len(stats["workspaces"]) == 1
        assert stats["workspaces"][0]["workspace_id"] == "ws-1"
