"""
Tests for AutomationScheduler service.

Tests the scheduling lifecycle: singleton, start/shutdown, polling logic,
cron calculation, and task dispatch.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.services.automation_scheduler import AutomationScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_automation(
    automation_id=None,
    trigger_type="cron",
    cron_expression="0 9 * * *",
    timezone_name="UTC",
    **overrides,
):
    data = {
        "automation_id": automation_id or str(uuid.uuid4()),
        "user_id": "user-1",
        "name": "Test Automation",
        "trigger_type": trigger_type,
        "cron_expression": cron_expression,
        "timezone": timezone_name,
        "agent_mode": "flash",
        "instruction": "Do something",
        "workspace_id": None,
        "_execution_id": str(uuid.uuid4()),
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    """Test AutomationScheduler singleton pattern."""

    def teardown_method(self):
        AutomationScheduler._instance = None

    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    def test_get_instance_creates_singleton(self, mock_executor_cls):
        mock_executor_cls.get_instance.return_value = MagicMock()
        instance = AutomationScheduler.get_instance()
        assert instance is not None
        assert isinstance(instance, AutomationScheduler)

    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    def test_get_instance_returns_same_instance(self, mock_executor_cls):
        mock_executor_cls.get_instance.return_value = MagicMock()
        first = AutomationScheduler.get_instance()
        second = AutomationScheduler.get_instance()
        assert first is second


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

class TestInit:
    """Test AutomationScheduler initialization."""

    def teardown_method(self):
        AutomationScheduler._instance = None

    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    def test_init_sets_server_id(self, mock_executor_cls):
        mock_executor_cls.get_instance.return_value = MagicMock()
        scheduler = AutomationScheduler()
        assert scheduler.server_id is not None
        assert len(scheduler.server_id) > 0

    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    def test_init_empty_running_tasks(self, mock_executor_cls):
        mock_executor_cls.get_instance.return_value = MagicMock()
        scheduler = AutomationScheduler()
        assert len(scheduler._running_tasks) == 0
        assert scheduler._poll_task is None


# ---------------------------------------------------------------------------
# start / shutdown
# ---------------------------------------------------------------------------

class TestLifecycle:
    """Test start and shutdown."""

    def teardown_method(self):
        AutomationScheduler._instance = None

    @pytest.mark.asyncio
    @patch("src.server.services.automation_scheduler.auto_db")
    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    async def test_start_creates_poll_task(self, mock_executor_cls, mock_auto_db):
        mock_executor_cls.get_instance.return_value = MagicMock()
        mock_auto_db.mark_stale_executions_failed = AsyncMock()

        scheduler = AutomationScheduler()
        await scheduler.start()

        try:
            assert scheduler._poll_task is not None
            assert not scheduler._shutdown_event.is_set()
            mock_auto_db.mark_stale_executions_failed.assert_awaited_once_with(
                scheduler.server_id
            )
        finally:
            await scheduler.shutdown()

    @pytest.mark.asyncio
    @patch("src.server.services.automation_scheduler.auto_db")
    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    async def test_shutdown_stops_poll_task(self, mock_executor_cls, mock_auto_db):
        mock_executor_cls.get_instance.return_value = MagicMock()
        mock_auto_db.mark_stale_executions_failed = AsyncMock()

        scheduler = AutomationScheduler()
        await scheduler.start()

        poll_task = scheduler._poll_task
        await scheduler.shutdown()

        assert scheduler._shutdown_event.is_set()
        assert poll_task.done() or poll_task.cancelled()

    @pytest.mark.asyncio
    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    async def test_shutdown_without_start(self, mock_executor_cls):
        mock_executor_cls.get_instance.return_value = MagicMock()

        scheduler = AutomationScheduler()
        # Should not raise
        await scheduler.shutdown()
        assert scheduler._shutdown_event.is_set()


# ---------------------------------------------------------------------------
# _poll_once
# ---------------------------------------------------------------------------

class TestPollOnce:
    """Test single polling iteration."""

    def teardown_method(self):
        AutomationScheduler._instance = None

    @pytest.mark.asyncio
    @patch("src.server.services.automation_scheduler.auto_db")
    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    async def test_poll_once_no_due_automations(self, mock_executor_cls, mock_auto_db):
        mock_executor = MagicMock()
        mock_executor_cls.get_instance.return_value = mock_executor
        mock_auto_db.claim_due_automations = AsyncMock(return_value=[])

        scheduler = AutomationScheduler()
        await scheduler._poll_once()

        mock_auto_db.claim_due_automations.assert_awaited_once()
        assert len(scheduler._running_tasks) == 0

    @pytest.mark.asyncio
    @patch("src.server.services.automation_scheduler.auto_db")
    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    async def test_poll_once_dispatches_cron_automation(self, mock_executor_cls, mock_auto_db):
        mock_executor = AsyncMock()
        mock_executor_cls.get_instance.return_value = mock_executor

        automation = _make_automation(trigger_type="cron", cron_expression="0 9 * * *")
        mock_auto_db.claim_due_automations = AsyncMock(return_value=[automation])
        mock_auto_db.update_automation_next_run = AsyncMock()

        scheduler = AutomationScheduler()
        await scheduler._poll_once()

        # Should calculate next run for cron type
        mock_auto_db.update_automation_next_run.assert_awaited_once()

        # Should have created a task
        # Wait briefly for the task to be registered
        await asyncio.sleep(0.01)
        # The task might already be done if executor is async mock,
        # but it was added to running_tasks at some point
        mock_executor.execute.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.server.services.automation_scheduler.auto_db")
    @patch("src.server.services.automation_scheduler.AutomationExecutor")
    async def test_poll_once_skips_next_run_for_once_type(self, mock_executor_cls, mock_auto_db):
        mock_executor = AsyncMock()
        mock_executor_cls.get_instance.return_value = mock_executor

        automation = _make_automation(
            trigger_type="once", cron_expression=None
        )
        mock_auto_db.claim_due_automations = AsyncMock(return_value=[automation])
        mock_auto_db.update_automation_next_run = AsyncMock()

        scheduler = AutomationScheduler()
        await scheduler._poll_once()

        # Should NOT calculate next_run for one-time type
        mock_auto_db.update_automation_next_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# _calculate_next_run
# ---------------------------------------------------------------------------

class TestCalculateNextRun:
    """Test cron next-run calculation."""

    def test_calculates_utc_datetime(self):
        result = AutomationScheduler._calculate_next_run("0 9 * * *", "UTC")
        assert result.tzinfo is not None
        assert result > datetime.now(timezone.utc)

    def test_handles_invalid_timezone(self):
        # Should fall back to UTC without raising
        result = AutomationScheduler._calculate_next_run(
            "0 9 * * *", "Invalid/Timezone"
        )
        assert result.tzinfo is not None
        assert result > datetime.now(timezone.utc)

    def test_calculate_first_run_delegates(self):
        result = AutomationScheduler.calculate_first_run("*/5 * * * *", "UTC")
        assert result.tzinfo is not None
        assert result > datetime.now(timezone.utc)

    def test_non_utc_timezone_converts_to_utc(self):
        result = AutomationScheduler._calculate_next_run(
            "0 9 * * *", "America/New_York"
        )
        assert result.tzinfo is not None
        # The result should be a valid UTC datetime
        assert result > datetime.now(timezone.utc)
