"""Batch event-stream append protocol (M3-A bulk flush).

``stream_append_many_with_retry`` rides one pipeline for a whole batch of SSE
frames instead of one XADD round trip per frame. Batching is a transport
optimization only: the I6 no-holes contract is preserved because every
ambiguous failure degrades to the per-frame ``stream_append_with_retry``
path, which keeps the idempotency-fence / tail-probe semantics pinned by
``test_stream_append_retry.py``.

These tests pin the batch-specific classification: the tail must witness the
LAST frame of the batch to trust the whole batch, and a refused/ambiguous
batch falls back frame-by-frame instead of being trusted as a unit.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.exceptions as redis_exceptions

from src.utils.cache.redis_cache import EventBufferUnavailableError
from src.utils.cache.stream_append import (
    StreamAppendError,
    stream_append_many_with_retry,
)

FRAME_A = "id: 1\ndata: a\n\n"
FRAME_B = "id: 2\ndata: b\n\n"
FRAME_C = "id: 3\ndata: c\n\n"
FRAMES = [
    (1, FRAME_A, None),
    (2, FRAME_B, None),
    (3, FRAME_C, None),
]
TAIL_C = FRAME_C.encode("utf-8")

# Per-frame fallback spy: records how many frames the fallback placed.
_fallback_calls = 0


def _install_fallback() -> None:
    """Patch stream_append_with_retry with a counting spy (global, per-test)."""
    global _fallback_calls
    _fallback_calls = 0

    async def _fake(*args, **kwargs):
        global _fallback_calls
        _fallback_calls += 1

    return patch(
        "src.utils.cache.stream_append.stream_append_with_retry",
        new=_fake,
    )


def _cache(**overrides) -> MagicMock:
    cache = MagicMock()
    cache.enabled = True
    cache.pipelined_event_buffer_many = AsyncMock(return_value=None)
    cache.stream_tail = AsyncMock(return_value=None)
    for k, v in overrides.items():
        setattr(cache, k, v)
    return cache


async def _append_many(cache, frames=FRAMES):
    await stream_append_many_with_retry(
        cache,
        "workflow:stream:t1:r1",
        list(frames),
        max_size=1000,
        label="t1:r1",
    )


@pytest.mark.asyncio
async def test_empty_batch_is_a_noop():
    cache = _cache()
    await _append_many(cache, frames=[])
    cache.pipelined_event_buffer_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_happy_path_writes_the_batch_once():
    cache = _cache()
    await _append_many(cache)

    assert cache.pipelined_event_buffer_many.await_count == 1
    cache.stream_tail.assert_not_awaited()
    frames = cache.pipelined_event_buffer_many.await_args.args[1]
    assert [f[0] for f in frames] == [1, 2, 3]
    # Not a retry: the first frame's epoch DEL rides along.
    assert cache.pipelined_event_buffer_many.await_args.kwargs["bare"] is False


@pytest.mark.asyncio
async def test_pool_exhaustion_replays_the_identical_batch():
    """Nothing reached the server, so there is nothing to probe — replay the
    whole batch identically (still not bare; the epoch DEL never ran)."""
    cache = _cache()
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=[
            redis_exceptions.ConnectionError("No connection available."),
            None,
        ]
    )
    await _append_many(cache)

    assert cache.pipelined_event_buffer_many.await_count == 2
    cache.stream_tail.assert_not_awaited()
    assert cache.pipelined_event_buffer_many.await_args.kwargs["bare"] is False


@pytest.mark.asyncio
async def test_ambiguous_batch_that_landed_is_accepted():
    """Reply lost but the tail proves the whole batch landed (last frame id +
    payload match) — accept, recover, don't degrade."""
    cache = _cache(stream_tail=AsyncMock(return_value=(3, TAIL_C, None)))
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=redis_exceptions.TimeoutError("Timeout reading from redis")
    )

    await _append_many(cache)

    assert cache.pipelined_event_buffer_many.await_count == 1
    cache.stream_tail.assert_awaited_once()


@pytest.mark.asyncio
async def test_ambiguous_batch_not_at_tail_degrades_per_frame():
    """Tail below our last id means the unit didn't fully land — fall back to
    single-frame appends so each frame's own fence decides, never trust."""
    cache = _cache()
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=redis_exceptions.TimeoutError("Timeout reading from redis")
    )
    # Tail at id 1 (a partial batch) — not the last frame → degrade.
    cache.stream_tail = AsyncMock(return_value=(1, FRAME_A.encode("utf-8"), None))

    with _install_fallback():
        await _append_many(cache)

    assert _fallback_calls == 3
    # The batch path accepted failure without a second batch attempt.
    assert cache.pipelined_event_buffer_many.await_count == 1


@pytest.mark.asyncio
async def test_refused_batch_degrades_per_frame():
    """A first-attempt ResponseError means the server answered "no" — never
    trust the batch, place each frame via the single-frame path."""
    cache = _cache()
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=redis_exceptions.ResponseError("the server refused")
    )

    with _install_fallback():
        await _append_many(cache)
        assert _fallback_calls == 3

    assert cache.pipelined_event_buffer_many.await_count == 1


@pytest.mark.asyncio
async def test_transport_unavailable_is_fatal_for_the_batch():
    cache = _cache()
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=EventBufferUnavailableError("disabled")
    )
    with pytest.raises(StreamAppendError, match="unusable"):
        await _append_many(cache)


@pytest.mark.asyncio
async def test_batch_with_record_field_witnesses_record_bytes():
    """When the batch writes ``record`` fields, the tail probe must match them
    too — the rendered frame alone cannot prove authorship (I6)."""
    frames = [
        (1, FRAME_A.encode("utf-8"), b'{"run":"r1"}'),
        (2, FRAME_B.encode("utf-8"), b'{"run":"r1"}'),
    ]
    cache = _cache(
        stream_tail=AsyncMock(return_value=(2, FRAME_B.encode("utf-8"), b'{"run":"r1"}'))
    )
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=redis_exceptions.TimeoutError("Timeout reading from redis")
    )

    await _append_many(cache, frames=frames)

    assert cache.pipelined_event_buffer_many.await_count == 1