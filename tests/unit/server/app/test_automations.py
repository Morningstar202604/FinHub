"""
Tests for the Automations API router (src/server/app/automations.py).

Covers CRUD, control actions (trigger/pause/resume), and execution history.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import create_test_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)
AUTO_ID = str(uuid.uuid4())
EXEC_ID = str(uuid.uuid4())


def _automation(automation_id=None, user_id="test-user-123", **overrides):
    data = {
        "automation_id": automation_id or AUTO_ID,
        "user_id": user_id,
        "name": "Daily Briefing",
        "description": "Morning market summary",
        "trigger_type": "cron",
        "cron_expression": "0 8 * * *",
        "timezone": "UTC",
        "trigger_config": None,
        "next_run_at": NOW,
        "last_run_at": None,
        "agent_mode": "flash",
        "instruction": "Give me a market summary",
        "workspace_id": None,
        "llm_model": None,
        "additional_context": None,
        "thread_strategy": "new",
        "conversation_thread_id": None,
        "status": "active",
        "max_failures": 3,
        "failure_count": 0,
        "delivery_config": None,
        "metadata": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return data


def _execution(automation_id=None, **overrides):
    data = {
        "automation_execution_id": EXEC_ID,
        "automation_id": automation_id or AUTO_ID,
        "status": "completed",
        "conversation_thread_id": None,
        "scheduled_at": NOW,
        "started_at": NOW,
        "completed_at": NOW,
        "error_message": None,
        "server_id": None,
        "created_at": NOW,
    }
    data.update(overrides)
    return data


@pytest_asyncio.fixture
async def client():
    from src.server.app.automations import router

    app = create_test_app(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


HANDLER = "src.server.app.automations.handler"
AUTO_DB = "src.server.app.automations.auto_db"


# ---------------------------------------------------------------------------
# POST /api/v1/automations — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_automation(client):
    auto = _automation()
    with patch(
        f"{HANDLER}.create_automation",
        new_callable=AsyncMock,
        return_value=auto,
    ):
        resp = await client.post(
            "/api/v1/automations",
            json={
                "name": "Daily Briefing",
                "trigger_type": "cron",
                "cron_expression": "0 8 * * *",
                "instruction": "Give me a market summary",
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Daily Briefing"
    assert body["trigger_type"] == "cron"


@pytest.mark.asyncio
async def test_create_automation_duplicate_409(client):
    with patch(
        f"{HANDLER}.create_automation",
        new_callable=AsyncMock,
        side_effect=ValueError("duplicate name"),
    ):
        resp = await client.post(
            "/api/v1/automations",
            json={
                "name": "Dup",
                "trigger_type": "cron",
                "cron_expression": "0 8 * * *",
                "instruction": "test",
            },
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_automation_validation_error(client):
    """Missing required fields should return 422."""
    resp = await client.post(
        "/api/v1/automations",
        json={"name": "No trigger"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/automations — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_automations(client):
    auto = _automation()
    with patch(
        f"{AUTO_DB}.list_automations",
        new_callable=AsyncMock,
        return_value=([auto], 1),
    ):
        resp = await client.get("/api/v1/automations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["automations"]) == 1


@pytest.mark.asyncio
async def test_list_automations_with_filters(client):
    with patch(
        f"{AUTO_DB}.list_automations",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as mock_list:
        resp = await client.get(
            "/api/v1/automations?status=active&limit=10&offset=5"
        )

    assert resp.status_code == 200
    mock_list.assert_awaited_once_with(
        "test-user-123", status="active", limit=10, offset=5
    )


# ---------------------------------------------------------------------------
# GET /api/v1/automations/{automation_id} — get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_automation(client):
    auto = _automation()
    with patch(
        f"{AUTO_DB}.get_automation",
        new_callable=AsyncMock,
        return_value=auto,
    ):
        resp = await client.get(f"/api/v1/automations/{AUTO_ID}")

    assert resp.status_code == 200
    assert resp.json()["automation_id"] == AUTO_ID


@pytest.mark.asyncio
async def test_get_automation_not_found(client):
    fake_id = str(uuid.uuid4())
    with patch(
        f"{AUTO_DB}.get_automation",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(f"/api/v1/automations/{fake_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/automations/{automation_id} — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_automation(client):
    auto = _automation(name="Updated")
    with patch(
        f"{HANDLER}.update_automation",
        new_callable=AsyncMock,
        return_value=auto,
    ):
        resp = await client.patch(
            f"/api/v1/automations/{AUTO_ID}",
            json={"name": "Updated"},
        )

    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_update_automation_not_found(client):
    fake_id = str(uuid.uuid4())
    with patch(
        f"{HANDLER}.update_automation",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.patch(
            f"/api/v1/automations/{fake_id}",
            json={"name": "X"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_automation_conflict_409(client):
    with patch(
        f"{HANDLER}.update_automation",
        new_callable=AsyncMock,
        side_effect=ValueError("conflict"),
    ):
        resp = await client.patch(
            f"/api/v1/automations/{AUTO_ID}",
            json={"name": "X"},
        )

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /api/v1/automations/{automation_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_automation(client):
    with patch(
        f"{AUTO_DB}.delete_automation",
        new_callable=AsyncMock,
        return_value=True,
    ):
        resp = await client.delete(f"/api/v1/automations/{AUTO_ID}")

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_automation_not_found(client):
    fake_id = str(uuid.uuid4())
    with patch(
        f"{AUTO_DB}.delete_automation",
        new_callable=AsyncMock,
        return_value=False,
    ):
        resp = await client.delete(f"/api/v1/automations/{fake_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/automations/{automation_id}/trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_automation(client):
    result = {"status": "triggered", "execution_id": EXEC_ID}
    with patch(
        f"{HANDLER}.trigger_automation",
        new_callable=AsyncMock,
        return_value=result,
    ):
        resp = await client.post(f"/api/v1/automations/{AUTO_ID}/trigger")

    assert resp.status_code == 200
    assert resp.json()["status"] == "triggered"


@pytest.mark.asyncio
async def test_trigger_automation_conflict(client):
    with patch(
        f"{HANDLER}.trigger_automation",
        new_callable=AsyncMock,
        side_effect=ValueError("already running"),
    ):
        resp = await client.post(f"/api/v1/automations/{AUTO_ID}/trigger")

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/v1/automations/{automation_id}/pause
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_automation(client):
    auto = _automation(status="paused")
    with patch(
        f"{HANDLER}.pause_automation",
        new_callable=AsyncMock,
        return_value=auto,
    ):
        resp = await client.post(f"/api/v1/automations/{AUTO_ID}/pause")

    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_pause_automation_not_found(client):
    fake_id = str(uuid.uuid4())
    with patch(
        f"{HANDLER}.pause_automation",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(f"/api/v1/automations/{fake_id}/pause")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/automations/{automation_id}/resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_automation(client):
    auto = _automation(status="active")
    with patch(
        f"{HANDLER}.resume_automation",
        new_callable=AsyncMock,
        return_value=auto,
    ):
        resp = await client.post(f"/api/v1/automations/{AUTO_ID}/resume")

    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_resume_automation_not_found(client):
    fake_id = str(uuid.uuid4())
    with patch(
        f"{HANDLER}.resume_automation",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(f"/api/v1/automations/{fake_id}/resume")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/automations/{automation_id}/executions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_executions(client):
    ex = _execution()
    with patch(
        f"{AUTO_DB}.list_executions",
        new_callable=AsyncMock,
        return_value=([ex], 1),
    ):
        resp = await client.get(
            f"/api/v1/automations/{AUTO_ID}/executions"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["executions"]) == 1


@pytest.mark.asyncio
async def test_list_executions_with_pagination(client):
    with patch(
        f"{AUTO_DB}.list_executions",
        new_callable=AsyncMock,
        return_value=([], 0),
    ) as mock_list:
        resp = await client.get(
            f"/api/v1/automations/{AUTO_ID}/executions?limit=5&offset=10"
        )

    assert resp.status_code == 200
    mock_list.assert_awaited_once_with(
        AUTO_ID, "test-user-123", limit=5, offset=10
    )
