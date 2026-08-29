"""
Tests for the Insights API router (src/server/app/insights.py).

Covers:
- POST /api/v1/insights/generate (success, credit limit, timeout, already generating, error)
- GET /api/v1/insights/today (mixed, system-only, yesterday fallback)
- GET /api/v1/insights/{id} (system, owner, non-owner, missing)
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.conftest import create_test_app

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)
INSIGHT_ID = str(uuid.uuid4())
USER_ID = "test-user-123"
OTHER_USER_ID = "other-user-456"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insight(
    market_insight_id=None,
    user_id=None,
    type="daily_brief",
    **overrides,
):
    """Build a dict resembling a market_insights DB row (detail columns)."""
    data = {
        "market_insight_id": market_insight_id or INSIGHT_ID,
        "user_id": user_id,
        "type": type,
        "status": "completed",
        "headline": "Markets rally on strong earnings",
        "summary": "Major indices gained as Q4 earnings beat expectations.",
        "content": [
            {
                "title": "S&P 500 hits record",
                "body": "The index closed at an all-time high.",
                "url": "https://example.com/sp500",
            }
        ],
        "topics": [
            {"text": "Earnings", "trend": "up"},
            {"text": "Fed", "trend": "neutral"},
        ],
        "sources": [{"url": "https://example.com", "title": "Example"}],
        "model": "claude-sonnet-4-20250514",
        "error_message": None,
        "generation_time_ms": 4200,
        "metadata": None,
        "created_at": NOW,
        "completed_at": NOW,
    }
    data.update(overrides)
    return data


def _card(market_insight_id=None, user_id=None, **overrides):
    """Build a dict resembling a card-level row (list/today endpoint)."""
    data = {
        "market_insight_id": market_insight_id or INSIGHT_ID,
        "type": "daily_brief",
        "headline": "Markets rally on strong earnings",
        "summary": "Major indices gained as Q4 earnings beat expectations.",
        "topics": [
            {"text": "Earnings", "trend": "up"},
            {"text": "Fed", "trend": "neutral"},
        ],
        "model": "claude-sonnet-4-20250514",
        "created_at": NOW,
        "completed_at": NOW,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

INSIGHT_DB = "src.server.app.insights.market_insight_db"
ENFORCE_CREDIT = "src.server.app.insights.enforce_credit_limit"
SERVICE_PATH = "src.server.app.insights.InsightService"


@pytest_asyncio.fixture
async def client():
    from src.server.app.insights import router

    app = create_test_app(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ===========================================================================
# POST /api/v1/insights/generate
# ===========================================================================


@pytest.mark.asyncio
async def test_generate_insight_success(client):
    """Authenticated user, generation returns 202 with generating row."""
    row = {
        "market_insight_id": "ins-gen",
        "type": "personalized",
        "status": "generating",
        "created_at": "2026-01-01T12:00:00Z",
    }

    mock_service = MagicMock()
    mock_service.generate_for_user = AsyncMock(return_value=row)

    with (
        patch(ENFORCE_CREDIT, new_callable=AsyncMock) as mock_credit,
        patch(f"{SERVICE_PATH}.get_instance", return_value=mock_service),
    ):
        resp = await client.post("/api/v1/insights/generate")

    assert resp.status_code == 202
    body = resp.json()
    assert body["market_insight_id"] == "ins-gen"
    assert body["status"] == "generating"
    mock_credit.assert_awaited_once_with(USER_ID)


@pytest.mark.asyncio
async def test_generate_insight_credit_limit_exceeded(client):
    """Credit limit exceeded returns 429."""
    from fastapi import HTTPException

    with patch(
        ENFORCE_CREDIT,
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=429,
            detail={"message": "Daily credit limit reached", "type": "credit_limit"},
        ),
    ):
        resp = await client.post("/api/v1/insights/generate")

    assert resp.status_code == 429
    assert "credit" in resp.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_generate_insight_already_generating(client):
    """InsightAlreadyGeneratingError returns 202 with existing row."""
    from src.server.services.insight_service import InsightAlreadyGeneratingError

    existing = {
        "market_insight_id": "ins-existing",
        "type": "personalized",
        "status": "generating",
        "created_at": "2026-01-01T12:00:00Z",
    }
    mock_service = MagicMock()
    mock_service.generate_for_user = AsyncMock(
        side_effect=InsightAlreadyGeneratingError(existing)
    )

    with (
        patch(ENFORCE_CREDIT, new_callable=AsyncMock),
        patch(f"{SERVICE_PATH}.get_instance", return_value=mock_service),
    ):
        resp = await client.post("/api/v1/insights/generate")

    assert resp.status_code == 202
    body = resp.json()
    assert body["market_insight_id"] == "ins-existing"
    assert body["status"] == "generating"


@pytest.mark.asyncio
async def test_generate_insight_returns_none(client):
    """Service returning None (generation failure) yields 500."""
    mock_service = MagicMock()
    mock_service.generate_for_user = AsyncMock(return_value=None)

    with (
        patch(ENFORCE_CREDIT, new_callable=AsyncMock),
        patch(f"{SERVICE_PATH}.get_instance", return_value=mock_service),
    ):
        resp = await client.post("/api/v1/insights/generate")

    assert resp.status_code == 500
    assert "failed" in resp.json()["detail"].lower()


# ===========================================================================
# GET /api/v1/insights/today
# ===========================================================================


@pytest.mark.asyncio
async def test_todays_insights_mixed(client):
    """Returns mixed system + user insights ordered by created_at."""
    system_card = _card(market_insight_id=str(uuid.uuid4()), type="pre_market")
    user_card = _card(market_insight_id=str(uuid.uuid4()), type="personalized")

    with patch(
        f"{INSIGHT_DB}.get_todays_market_insights",
        new_callable=AsyncMock,
        return_value=[system_card, user_card],
    ) as mock_db:
        resp = await client.get("/api/v1/insights/today")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert len(body["insights"]) == 2
    mock_db.assert_awaited_once_with(user_id=USER_ID)


@pytest.mark.asyncio
async def test_todays_insights_system_only(client):
    """Returns system insights when no user insights exist."""
    system_card = _card(type="pre_market")

    with patch(
        f"{INSIGHT_DB}.get_todays_market_insights",
        new_callable=AsyncMock,
        return_value=[system_card],
    ):
        resp = await client.get("/api/v1/insights/today")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["insights"][0]["type"] == "pre_market"


@pytest.mark.asyncio
async def test_todays_insights_empty(client):
    """Returns empty list when no insights exist at all."""
    with patch(
        f"{INSIGHT_DB}.get_todays_market_insights",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get("/api/v1/insights/today")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["insights"] == []


@pytest.mark.asyncio
async def test_todays_insights_yesterday_fallback(client):
    """DB layer returns yesterday's insight when none exist today; route returns it."""
    yesterday_card = _card(type="post_market", headline="Yesterday recap")

    with patch(
        f"{INSIGHT_DB}.get_todays_market_insights",
        new_callable=AsyncMock,
        return_value=[yesterday_card],
    ):
        resp = await client.get("/api/v1/insights/today")

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["insights"][0]["headline"] == "Yesterday recap"


# ===========================================================================
# GET /api/v1/insights/{id}
# ===========================================================================


@pytest.mark.asyncio
async def test_get_insight_system_accessible_by_any_user(client):
    """System insight (user_id=None) is accessible by any authenticated user."""
    system_insight = _insight(user_id=None)

    with patch(
        f"{INSIGHT_DB}.get_market_insight",
        new_callable=AsyncMock,
        return_value=system_insight,
    ):
        resp = await client.get(f"/api/v1/insights/{INSIGHT_ID}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["market_insight_id"] == INSIGHT_ID
    assert body["headline"] == system_insight["headline"]


@pytest.mark.asyncio
async def test_get_insight_owner_accessible(client):
    """Per-user insight is accessible by its owner."""
    user_insight = _insight(user_id=USER_ID, type="personalized")

    with patch(
        f"{INSIGHT_DB}.get_market_insight",
        new_callable=AsyncMock,
        return_value=user_insight,
    ):
        resp = await client.get(f"/api/v1/insights/{INSIGHT_ID}")

    assert resp.status_code == 200
    assert resp.json()["market_insight_id"] == INSIGHT_ID


@pytest.mark.asyncio
async def test_get_insight_non_owner_returns_404(client):
    """Per-user insight owned by another user returns 404 (not 403)."""
    other_insight = _insight(user_id=OTHER_USER_ID, type="personalized")

    with patch(
        f"{INSIGHT_DB}.get_market_insight",
        new_callable=AsyncMock,
        return_value=other_insight,
    ):
        resp = await client.get(f"/api/v1/insights/{INSIGHT_ID}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_insight_not_found(client):
    """Non-existent insight ID returns 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        f"{INSIGHT_DB}.get_market_insight",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get(f"/api/v1/insights/{fake_id}")

    assert resp.status_code == 404
