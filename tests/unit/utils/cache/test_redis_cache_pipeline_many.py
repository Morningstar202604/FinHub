"""RedisCacheClient.pipelined_event_buffer_many (M3-A batch XADD).

A batch of SSE frames rides one pipeline as explicit ``{event_id}-0`` XADDs.
These tests pin: order is preserved, the epoch DEL fires only for the first
frame's id==1, the retention heal fires at most once per batch (not per
frame), and a disabled client is fatal (EventBufferUnavailableError).
"""

from __future__ import annotations

import pytest

from src.utils.cache.redis_cache import _HEAL_INTERVAL, RedisCacheClient


class _FakePipeline:
    """Records every queued command; execute() just clears the queue."""

    def __init__(self, owner: "_FakeRedis"):
        self.calls: list[tuple[str, tuple, dict]] = []
        self._owner = owner

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def delete(self, key):
        self.calls.append(("delete", (key,), {}))
        return self

    def xadd(self, key, fields, **kwargs):
        self.calls.append(("xadd", (key, fields), kwargs))
        return self

    def expire(self, key, ttl):
        self.calls.append(("expire", (key, ttl), {}))
        return self

    def persist(self, key):
        self.calls.append(("persist", (key,), {}))
        return self

    async def execute(self):
        self._owner.pipelines.append(self.calls)
        return []


class _FakeRedis:
    def __init__(self):
        self.pipelines: list[list] = []

    def pipeline(self, transaction=False):
        return _FakePipeline(self)


@pytest.fixture
def cache():
    client = RedisCacheClient(url="redis://unit-test-never-connects:6379/0")
    client.enabled = True
    client.client = _FakeRedis()
    return client


def _xadd_ids(calls: list) -> list:
    return [kw["id"] for fn, _, kw in calls if fn == "xadd"]


def _xadd_fields(calls: list) -> int:
    return sum(1 for fn, _, _ in calls if fn == "xadd")


@pytest.mark.asyncio
async def test_all_frames_ride_one_pipeline_in_order(cache):
    frames = [(1, b"a", None), (2, b"b", None), (3, b"c", None)]
    await cache.pipelined_event_buffer_many("s", frames, max_size=100)

    assert len(cache.client.pipelines) == 1
    calls = cache.client.pipelines[0]
    assert _xadd_ids(calls) == ["1-0", "2-0", "3-0"]
    assert _xadd_fields(calls) == 3
    # MAXLEN backstop rides along on every xadd.
    assert all(kw.get("maxlen") == 100 for fn, _, kw in calls if fn == "xadd")


@pytest.mark.asyncio
async def test_epoch_del_fires_once_for_batch_starting_at_1(cache):
    frames = [(1, b"a", None), (2, b"b", None)]
    await cache.pipelined_event_buffer_many("s", frames, max_size=100)

    calls = cache.client.pipelines[0]
    deletes = [fn for fn, _, _ in calls if fn == "delete"]
    # Exactly one DEL, for the first frame's id==1.
    assert deletes == ["delete"]


@pytest.mark.asyncio
async def test_batch_not_starting_at_1_has_no_epoch_del(cache):
    frames = [(5, b"a", None), (6, b"b", None)]
    await cache.pipelined_event_buffer_many("s", frames, max_size=100)

    calls = cache.client.pipelines[0]
    assert all(fn != "delete" for fn, _, _ in calls)


@pytest.mark.asyncio
async def test_heal_fires_at_most_once_even_with_two_heal_frames(cache):
    # _HEAL_INTERVAL=512: a batch spanning two multiples heals once, not twice.
    frames = [
        (_HEAL_INTERVAL, b"a", None),
        (_HEAL_INTERVAL + 1, b"b", None),
        (_HEAL_INTERVAL * 2, b"c", None),
    ]
    await cache.pipelined_event_buffer_many("s", frames, max_size=100)

    calls = cache.client.pipelines[0]
    persists = [fn for fn, _, _ in calls if fn == "persist"]
    assert len(persists) == 1


@pytest.mark.asyncio
async def test_ttl_rides_along(cache):
    frames = [(1, b"a", None)]
    await cache.pipelined_event_buffer_many("s", frames, max_size=100, ttl=60)

    calls = cache.client.pipelines[0]
    assert ("expire", ("s", 60), {}) in calls


@pytest.mark.asyncio
async def test_disable_client_is_fatal(cache):
    from src.utils.cache.redis_cache import EventBufferUnavailableError

    cache.enabled = False
    with pytest.raises(EventBufferUnavailableError):
        await cache.pipelined_event_buffer_many("s", [(1, b"a", None)], max_size=100)


@pytest.mark.asyncio
async def test_empty_batch_is_a_noop(cache):
    await cache.pipelined_event_buffer_many("s", [], max_size=100)
    assert cache.client.pipelines == []


class _ScanFakeRedis:
    """SCAN-iterable client whose pipelines record every queued delete."""

    def __init__(self, keys: list[bytes]):
        self.keys = keys
        self.pipelines: list[list[tuple]] = []

    async def scan_iter(self, match=None, count=100):
        for k in self.keys:
            yield k

    def pipeline(self, transaction=False):
        return _DeletePipeline(self)


class _DeletePipeline:
    def __init__(self, owner: _ScanFakeRedis):
        self._owner = owner
        self._calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def delete(self, key):
        self._calls.append(("delete", key))
        return self

    async def execute(self):
        self._owner.pipelines.append(self._calls)
        return []


@pytest.mark.asyncio
async def test_delete_pattern_uses_one_pipeline_per_chunk():
    """M3-C: SCAN-iterated deletes ride pipeline chunks, not one round trip
    per key — a 250-key cleanup is 3 pipelines, not 250 deletes."""
    keys = [f"cache:x:{i}".encode() for i in range(250)]
    client = RedisCacheClient(url="redis://unit-test-never-connects:6379/0")
    client.enabled = True
    client.client = _ScanFakeRedis(keys)

    deleted = await client.delete_pattern("cache:x:*")

    assert deleted == 250
    pipelines = client.client.pipelines
    # chunks of 100 → [100, 100, 50]
    assert [len(p) for p in pipelines] == [100, 100, 50]
    # Every key was deleted exactly once across the chunks.
    flat = [k for fn, k in (c for p in pipelines for c in p)]
    assert set(flat) == set(keys) and len(flat) == 250