"""Integration tests for user CRUD and preferences against real PostgreSQL."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestCreateUser:
    """Test user creation flows."""

    async def test_create_user(self, patched_get_db_connection):
        from src.server.database.user import create_user

        user = await create_user(
            user_id="user-create-test",
            email="alice@example.com",
            name="Alice",
        )

        assert user["user_id"] == "user-create-test"
        assert user["email"] == "alice@example.com"
        assert user["name"] == "Alice"
        assert user["onboarding_completed"] is False
        assert user["created_at"] is not None

    async def test_create_user_duplicate_raises(self, patched_get_db_connection):
        from src.server.database.user import create_user

        await create_user(user_id="dup-user", email="dup@example.com")

        with pytest.raises(ValueError, match="already exists"):
            await create_user(user_id="dup-user", email="dup2@example.com")

    async def test_create_user_from_auth_idempotent(
        self, patched_get_db_connection
    ):
        from src.server.database.user import create_user_from_auth, get_user

        # First call creates
        user1 = await create_user_from_auth(
            user_id="auth-user-1",
            email="auth@example.com",
            name="Auth User",
            auth_provider="google",
        )
        assert user1["auth_provider"] == "google"

        # Second call is idempotent upsert
        user2 = await create_user_from_auth(
            user_id="auth-user-1",
            email="auth-updated@example.com",
            name="Auth User v2",
            auth_provider="github",  # should NOT overwrite existing provider
        )

        # Email should be updated, auth_provider should remain google (COALESCE logic)
        assert user2["email"] == "auth-updated@example.com"
        assert user2["auth_provider"] == "google"


class TestGetUser:
    """Test user retrieval."""

    async def test_get_user_exists(self, seed_user, patched_get_db_connection):
        from src.server.database.user import get_user

        user = await get_user(seed_user["user_id"])
        assert user is not None
        assert user["email"] == "test@example.com"

    async def test_get_user_not_found(self, patched_get_db_connection):
        from src.server.database.user import get_user

        user = await get_user("nonexistent-user-id")
        assert user is None


class TestUpdateUser:
    """Test user update operations."""

    async def test_update_user_fields(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import update_user

        updated = await update_user(
            user_id=seed_user["user_id"],
            name="Updated Name",
            timezone="America/New_York",
            locale="en-US",
        )

        assert updated is not None
        assert updated["name"] == "Updated Name"
        assert updated["timezone"] == "America/New_York"
        assert updated["locale"] == "en-US"
        # Email should be unchanged
        assert updated["email"] == "test@example.com"

    async def test_update_onboarding_completed(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import update_user

        updated = await update_user(
            user_id=seed_user["user_id"],
            onboarding_completed=True,
        )

        assert updated is not None
        assert updated["onboarding_completed"] is True

    async def test_upsert_user_creates_if_missing(
        self, patched_get_db_connection
    ):
        from src.server.database.user import get_user, upsert_user

        result = await upsert_user(
            user_id="upsert-new-user",
            email="upsert@example.com",
            name="Upsert User",
        )

        assert result["user_id"] == "upsert-new-user"
        assert result["email"] == "upsert@example.com"

        # Should be retrievable
        fetched = await get_user("upsert-new-user")
        assert fetched is not None

    async def test_upsert_user_updates_if_exists(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import upsert_user

        result = await upsert_user(
            user_id=seed_user["user_id"],
            name="Upserted Name",
        )

        assert result["name"] == "Upserted Name"
        # Email should be preserved (COALESCE)
        assert result["email"] == "test@example.com"


class TestUserPreferences:
    """Test user preferences CRUD."""

    async def test_get_preferences_created_with_user(
        self, seed_user, patched_get_db_connection
    ):
        """create_user auto-creates a preferences row."""
        from src.server.database.user import get_user_preferences

        prefs = await get_user_preferences(seed_user["user_id"])
        assert prefs is not None
        assert prefs["user_id"] == seed_user["user_id"]

    async def test_upsert_preferences_merge(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import (
            get_user_preferences,
            upsert_user_preferences,
        )

        # Set initial preferences
        result = await upsert_user_preferences(
            user_id=seed_user["user_id"],
            agent_preference={"default_model": "claude-sonnet"},
        )
        assert result["agent_preference"]["default_model"] == "claude-sonnet"

        # Merge additional field
        result2 = await upsert_user_preferences(
            user_id=seed_user["user_id"],
            agent_preference={"temperature": 0.7},
        )

        # Both fields should be present after merge
        assert result2["agent_preference"]["default_model"] == "claude-sonnet"
        assert result2["agent_preference"]["temperature"] == 0.7

    async def test_upsert_preferences_replace(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import upsert_user_preferences

        # Set initial
        await upsert_user_preferences(
            user_id=seed_user["user_id"],
            risk_preference={"risk_level": "high", "notes": "aggressive"},
        )

        # Replace mode: only the new value should remain
        result = await upsert_user_preferences(
            user_id=seed_user["user_id"],
            risk_preference={"risk_level": "low"},
            replace=True,
        )

        assert result["risk_preference"] == {"risk_level": "low"}

    async def test_delete_preferences(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import (
            delete_user_preferences,
            get_user_preferences,
        )

        deleted = await delete_user_preferences(seed_user["user_id"])
        assert deleted is True

        prefs = await get_user_preferences(seed_user["user_id"])
        assert prefs is None

    async def test_get_user_with_preferences(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.user import (
            get_user_with_preferences,
            upsert_user_preferences,
        )

        await upsert_user_preferences(
            user_id=seed_user["user_id"],
            investment_preference={"sectors": ["tech", "healthcare"]},
        )

        result = await get_user_with_preferences(seed_user["user_id"])
        assert result is not None
        assert result["user"]["email"] == "test@example.com"
        assert result["preferences"] is not None
        assert result["preferences"]["investment_preference"]["sectors"] == [
            "tech",
            "healthcare",
        ]
