"""M3-A performance smoke: SSE batch-write latency guard (CI performance job).

Asserts the bulk-flush path stays fast WITHOUT a real Redis: the unit-level
contract for ``stream_append_many_with_retry`` is correctness (covered by
tests); this script guards the *shaping* of the batch — that N frames still
ride one pipeline, so a regression to "one round trip per frame" fails CI
instead of silently shipping a slower stream.

Run: ``uv run python -m scripts.perf.event_write_smoke``
Exit: 0 = pass (batch shape + elapsed under threshold), 1 = fail.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from src.utils.cache.stream_append import stream_append_many_with_retry

_N_FRAMES = 128  # multiple of the executor's 32-frame batch size
_BATCH_EXPECTED = _N_FRAMES // 32  # executor flushes every 32 frames
_MAX_ELAPSED_S = 1.0  # generous wall-clock budget; the shaping is what we gate


class _PipelineProbe:
    """Records how many XADD commands the batch transport emitted."""

    def __init__(self) -> None:
        self.xadd_calls = 0

    async def __aenter__(self) -> "_PipelineProbe":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    def xadd(self, *_args, **_kwargs):
        self.xadd_calls += 1
        return self


class _ProbeRedis:
    def __init__(self, probe: _PipelineProbe, frames: list):
        self._probe = probe
        self._frames = frames

    def pipeline(self, transaction=False):
        return _ProbePipeline(self._probe, self._frames)


class _ProbePipeline:
    def __init__(self, probe: _PipelineProbe, frames: list):
        self._probe = probe
        self._frames = frames

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def xadd(self, key, fields, **kwargs):
        self._probe.xadd_calls += 1
        return self

    async def execute(self):
        return [1] * len(self._frames)


def _frames(n: int) -> list[tuple[int, str, None]]:
    return [(i, f"id: {i}\nevent: x\ndata: probe\n\n", None) for i in range(1, n + 1)]


async def main() -> int:
    frames = _frames(_N_FRAMES)
    probe = _PipelineProbe()
    cache = MagicMock()
    cache.enabled = True
    cache.pipelined_event_buffer_many = AsyncMock(
        side_effect=lambda key, f, **kw: None
    )
    cache.stream_tail = AsyncMock(return_value=None)

    started = time.monotonic()
    # Success path: the batch rides ONE pipelined_event_buffer_many call.
    await stream_append_many_with_retry(
        cache,
        "probe:stream",
        frames,
        max_size=1000,
        label="probe",
    )
    elapsed = time.monotonic() - started

    calls = cache.pipelined_event_buffer_many.await_count
    ok = calls == 1 and elapsed <= _MAX_ELAPSED_S
    print(
        f"[batch-write] {_N_FRAMES} frames -> {calls} pipelined call(s) "
        f"({elapsed * 1000:.1f} ms)"
    )
    print(
        f"[{'PASS' if ok else 'FAIL'}] M3-A batch shaping "
        f"(expect 1 pipeline call, <= {_MAX_ELAPSED_S:.1f}s)"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))