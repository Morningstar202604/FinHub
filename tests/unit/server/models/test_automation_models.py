"""Tests for automation Pydantic models.

Covers request/response models in src/server/models/automation.py including
field constraints, enum literals, and defaults.
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.server.models.automation import (
    AutomationCreate,
    AutomationExecutionResponse,
    AutomationExecutionsListResponse,
    AutomationResponse,
    AutomationsListResponse,
    AutomationUpdate,
)


NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# AutomationCreate
# ---------------------------------------------------------------------------


class TestAutomationCreate:
    """AutomationCreate construction and validation."""

    def test_valid_minimal_cron(self):
        a = AutomationCreate(
            name="Daily Report",
            trigger_type="cron",
            instruction="Summarise market news",
        )
        assert a.trigger_type == "cron"
        assert a.agent_mode == "flash"
        assert a.thread_strategy == "new"
        assert a.max_failures == 3
        assert a.timezone == "UTC"

    def test_valid_once(self):
        a = AutomationCreate(
            name="One-shot",
            trigger_type="once",
            instruction="Run analysis",
            next_run_at=NOW,
        )
        assert a.trigger_type == "once"
        assert a.next_run_at == NOW

    def test_invalid_trigger_type(self):
        with pytest.raises(ValidationError):
            AutomationCreate(
                name="Bad",
                trigger_type="webhook",
                instruction="x",
            )

    def test_invalid_agent_mode(self):
        with pytest.raises(ValidationError):
            AutomationCreate(
                name="Bad",
                trigger_type="cron",
                instruction="x",
                agent_mode="turbo",
            )

    def test_max_failures_bounds(self):
        with pytest.raises(ValidationError):
            AutomationCreate(
                name="Bad",
                trigger_type="cron",
                instruction="x",
                max_failures=0,
            )
        with pytest.raises(ValidationError):
            AutomationCreate(
                name="Bad",
                trigger_type="cron",
                instruction="x",
                max_failures=101,
            )

    def test_name_too_long(self):
        with pytest.raises(ValidationError):
            AutomationCreate(
                name="x" * 256,
                trigger_type="cron",
                instruction="x",
            )

    def test_thread_strategy_values(self):
        for strategy in ("new", "continue"):
            a = AutomationCreate(
                name="A",
                trigger_type="cron",
                instruction="x",
                thread_strategy=strategy,
            )
            assert a.thread_strategy == strategy


# ---------------------------------------------------------------------------
# AutomationUpdate
# ---------------------------------------------------------------------------


class TestAutomationUpdate:
    """AutomationUpdate partial update model."""

    def test_empty_update(self):
        u = AutomationUpdate()
        assert u.name is None
        assert u.instruction is None
        assert u.max_failures is None

    def test_partial_update(self):
        u = AutomationUpdate(name="Renamed", max_failures=5)
        assert u.name == "Renamed"
        assert u.max_failures == 5

    def test_max_failures_bounds(self):
        with pytest.raises(ValidationError):
            AutomationUpdate(max_failures=0)
        with pytest.raises(ValidationError):
            AutomationUpdate(max_failures=101)


# ---------------------------------------------------------------------------
# AutomationResponse
# ---------------------------------------------------------------------------


class TestAutomationResponse:
    """AutomationResponse model construction."""

    def test_valid_construction(self):
        uid = uuid.uuid4()
        resp = AutomationResponse(
            automation_id=uid,
            user_id="user-1",
            name="My Auto",
            trigger_type="cron",
            timezone="UTC",
            agent_mode="flash",
            instruction="Do something",
            thread_strategy="new",
            status="active",
            max_failures=3,
            failure_count=0,
            created_at=NOW,
            updated_at=NOW,
        )
        assert resp.automation_id == uid
        assert resp.status == "active"
        assert resp.failure_count == 0


# ---------------------------------------------------------------------------
# AutomationExecutionResponse
# ---------------------------------------------------------------------------


class TestAutomationExecutionResponse:
    """Execution response model."""

    def test_valid_construction(self):
        exec_id = uuid.uuid4()
        auto_id = uuid.uuid4()
        resp = AutomationExecutionResponse(
            automation_execution_id=exec_id,
            automation_id=auto_id,
            status="completed",
            scheduled_at=NOW,
            created_at=NOW,
        )
        assert resp.status == "completed"
        assert resp.error_message is None
        assert resp.started_at is None
        assert resp.completed_at is None


# ---------------------------------------------------------------------------
# List responses
# ---------------------------------------------------------------------------


class TestAutomationsListResponse:
    """Automation list response."""

    def test_empty(self):
        resp = AutomationsListResponse(automations=[], total=0)
        assert resp.total == 0


class TestAutomationExecutionsListResponse:
    """Execution list response."""

    def test_empty(self):
        resp = AutomationExecutionsListResponse(executions=[], total=0)
        assert resp.total == 0
