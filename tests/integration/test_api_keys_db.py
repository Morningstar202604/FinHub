"""Integration tests for BYOK API keys CRUD against real PostgreSQL.

These tests require pgcrypto extension (for pgp_sym_encrypt/decrypt).
The conftest schema DDL creates it via CREATE EXTENSION IF NOT EXISTS pgcrypto.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# A deterministic encryption key used only during tests.
_TEST_ENCRYPTION_KEY = "test-byok-encryption-key-32char!"


@pytest.fixture(autouse=True)
def _mock_encryption_key():
    """Provide a test encryption key for pgcrypto operations."""
    with patch.dict(os.environ, {"BYOK_ENCRYPTION_KEY": _TEST_ENCRYPTION_KEY}):
        yield


class TestUpsertAndGetKeys:
    """Test API key upsert and retrieval."""

    async def test_upsert_api_key(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_user_api_keys, upsert_api_key

        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="anthropic",
            api_key="sk-ant-test-key-123",
        )

        result = await get_user_api_keys(seed_user["user_id"])
        assert "anthropic" in result["keys"]
        assert result["keys"]["anthropic"] == "sk-ant-test-key-123"

    async def test_upsert_overwrites_existing(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_user_api_keys, upsert_api_key

        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="openai",
            api_key="sk-old-key",
        )
        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="openai",
            api_key="sk-new-key",
        )

        result = await get_user_api_keys(seed_user["user_id"])
        assert result["keys"]["openai"] == "sk-new-key"

    async def test_upsert_with_base_url(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_user_api_keys, upsert_api_key

        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="openai",
            api_key="sk-custom",
            base_url="https://custom-openai.example.com/v1",
        )

        result = await get_user_api_keys(seed_user["user_id"])
        assert result["base_urls"]["openai"] == "https://custom-openai.example.com/v1"

    async def test_multiple_providers(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_user_api_keys, upsert_api_key

        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="anthropic",
            api_key="sk-ant-xxx",
        )
        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="openai",
            api_key="sk-oai-xxx",
        )

        result = await get_user_api_keys(seed_user["user_id"])
        assert len(result["keys"]) == 2
        assert "anthropic" in result["keys"]
        assert "openai" in result["keys"]


class TestDeleteKeys:
    """Test API key deletion."""

    async def test_delete_api_key(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import (
            delete_api_key,
            get_user_api_keys,
            upsert_api_key,
        )

        await upsert_api_key(
            user_id=seed_user["user_id"],
            provider="anthropic",
            api_key="sk-to-delete",
        )

        await delete_api_key(seed_user["user_id"], "anthropic")

        result = await get_user_api_keys(seed_user["user_id"])
        assert "anthropic" not in result["keys"]


class TestByokToggle:
    """Test the global BYOK enabled/disabled toggle."""

    async def test_set_byok_enabled(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_user_api_keys, set_byok_enabled

        # Default is False
        result = await get_user_api_keys(seed_user["user_id"])
        assert result["byok_enabled"] is False

        # Enable
        enabled = await set_byok_enabled(seed_user["user_id"], True)
        assert enabled is True

        result = await get_user_api_keys(seed_user["user_id"])
        assert result["byok_enabled"] is True

        # Disable
        disabled = await set_byok_enabled(seed_user["user_id"], False)
        assert disabled is False

    async def test_is_byok_active(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import (
            is_byok_active,
            set_byok_enabled,
            upsert_api_key,
        )

        # Not active: no keys, toggle off
        assert await is_byok_active(seed_user["user_id"]) is False

        # Add key but keep toggle off
        await upsert_api_key(
            seed_user["user_id"], "anthropic", "sk-test"
        )
        assert await is_byok_active(seed_user["user_id"]) is False

        # Enable toggle -- now active
        await set_byok_enabled(seed_user["user_id"], True)
        assert await is_byok_active(seed_user["user_id"]) is True


class TestGetKeyForProvider:
    """Test single-provider key lookup."""

    async def test_get_key_for_provider(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_key_for_provider, upsert_api_key

        await upsert_api_key(
            seed_user["user_id"], "anthropic", "sk-specific-key"
        )

        key = await get_key_for_provider(seed_user["user_id"], "anthropic")
        assert key == "sk-specific-key"

    async def test_get_key_for_missing_provider(
        self, seed_user, patched_get_db_connection
    ):
        from src.server.database.api_keys import get_key_for_provider

        key = await get_key_for_provider(seed_user["user_id"], "nonexistent")
        assert key is None
