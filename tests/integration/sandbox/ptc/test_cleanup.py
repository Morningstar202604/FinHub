from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestCleanupAndClose:
    """PTCSandbox.cleanup() and close() -- resource release."""

    async def test_cleanup_deletes_runtime(self, sandbox_minimal, _patch_create_provider):
        sb = sandbox_minimal
        await sb.setup_sandbox_workspace()
        assert sb.runtime is not None

        await sb.cleanup()
        assert sb.runtime is None
        assert sb.sandbox_id is None

    async def test_close_releases_provider(self, sandbox_minimal, _patch_create_provider):
        if _patch_create_provider is None:
            pytest.skip("Test requires MemoryProvider (checks _closed attribute)")
        sb = sandbox_minimal
        await sb.setup_sandbox_workspace()

        await sb.close()
        # Provider should be closed -- further create() calls fail
        provider = _patch_create_provider
        assert provider._closed is True

    async def test_cleanup_is_idempotent(self, sandbox_minimal, _patch_create_provider):
        sb = sandbox_minimal
        await sb.setup_sandbox_workspace()
        await sb.cleanup()
        # Second cleanup should not raise
        await sb.cleanup()

    async def test_stop_then_cleanup(self, sandbox_minimal, _patch_create_provider):
        """stop_sandbox then cleanup -- the normal session teardown path."""
        sb = sandbox_minimal
        await sb.setup_sandbox_workspace()

        await sb.stop_sandbox()
        await sb.cleanup()  # delete after stop
        assert sb.runtime is None
