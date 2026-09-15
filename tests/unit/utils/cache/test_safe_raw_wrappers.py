"""The safe raw-byte cache wrappers must never raise — and never fail silent.

These methods exist because the flag caches bypassed get()/set() (raw bytes,
not JSON) and swallowed every Redis failure on the way down to the DB.
Falling back is correct; doing it without an observation signal is not, so
every failure path must log through _log_error and bump stats["errors"].
"""

import logging
from unittest.mock import AsyncMock

import pytest

from src.utils.cache.redis_cache import RedisCacheClient

pytestmark = pytest.mark.asyncio

_KEY = "byok_active:user-1"


_UNSET = object()


def _client(enabled=True, client=_UNSET) -> RedisCacheClient:
    c = RedisCacheClient()
    c.enabled = enabled
    c.client = AsyncMock() if client is _UNSET else client
    c.stats = {"errors": 0}
    return c


def _failing_client(exc: Exception = RuntimeError("connection refused")):
    client = AsyncMock()
    client.get = AsyncMock(side_effect=exc)
    client.set = AsyncMock(side_effect=exc)
    client.delete = AsyncMock(side_effect=exc)
    return client


async def test_get_raw_returns_value_on_success():
    client = AsyncMock()
    client.get = AsyncMock(return_value=b"1")
    c = _client(client=client)
    assert await c.safe_get_raw(_KEY) == b"1"
    assert c.stats["errors"] == 0


async def test_get_raw_degrades_to_none_and_counts(caplog):
    c = _client(client=_failing_client())
    with caplog.at_level(logging.ERROR, logger="src.utils.cache.redis_cache"):
        assert await c.safe_get_raw(_KEY) is None
    assert c.stats["errors"] == 1
    assert _KEY in caplog.text


async def test_set_raw_degrades_to_false_and_counts(caplog):
    c = _client(client=_failing_client())
    with caplog.at_level(logging.ERROR, logger="src.utils.cache.redis_cache"):
        assert await c.safe_set_raw(_KEY, b"1", ex=60) is False
    assert c.stats["errors"] == 1
    assert _KEY in caplog.text


async def test_delete_degrades_to_false_and_counts(caplog):
    c = _client(client=_failing_client())
    with caplog.at_level(logging.ERROR, logger="src.utils.cache.redis_cache"):
        assert await c.safe_delete(_KEY) is False
    assert c.stats["errors"] == 1


async def test_set_raw_and_delete_return_true_on_success():
    c = _client()  # happy-path AsyncMock
    assert await c.safe_set_raw(_KEY, b"0", ex=86400) is True
    assert await c.safe_delete(_KEY, "other:key") is True


async def test_disabled_client_short_circuits_without_touching_redis():
    client = AsyncMock()
    c = _client(enabled=False, client=client)
    assert await c.safe_get_raw(_KEY) is None
    assert await c.safe_set_raw(_KEY, b"1") is False
    assert await c.safe_delete(_KEY) is False
    client.get.assert_not_awaited()
    client.set.assert_not_awaited()
    client.delete.assert_not_awaited()
    assert c.stats["errors"] == 0


async def test_none_client_short_circuits():
    c = _client(enabled=True, client=None)
    assert await c.safe_get_raw(_KEY) is None
    assert await c.safe_set_raw(_KEY, b"1") is False


async def test_delete_with_no_keys_is_a_noop():
    client = AsyncMock()
    c = _client(client=client)
    assert await c.safe_delete() is False
    client.delete.assert_not_awaited()
