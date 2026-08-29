"""Contract tests for SandboxRuntime metadata and capabilities."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio(loop_scope="class")
class TestRuntimeMetadata:
    """SandboxRuntime.capabilities, get_metadata(), working_dir, fetch_working_dir."""

    async def test_capabilities_set(self, shared_runtime, timed):
        async with timed("metadata", "capabilities"):
            caps = shared_runtime.capabilities
        assert isinstance(caps, set)
        assert "exec" in caps
        assert "code_run" in caps
        assert "file_io" in caps

    async def test_get_metadata(self, shared_runtime, timed):
        async with timed("metadata", "get_metadata"):
            meta = await shared_runtime.get_metadata()
        assert meta["id"] == shared_runtime.id
        assert "working_dir" in meta

    async def test_working_dir_property(self, shared_runtime, timed):
        async with timed("metadata", "working_dir_property"):
            wd = shared_runtime.working_dir
        assert wd is not None
        assert len(wd) > 0

    async def test_fetch_working_dir(self, shared_runtime, timed):
        async with timed("metadata", "fetch_working_dir"):
            wd = await shared_runtime.fetch_working_dir()
        assert wd == shared_runtime.working_dir
