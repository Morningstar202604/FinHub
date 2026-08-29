from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestLazyInit:
    """PTCSandbox lazy init: start_lazy_init -> ensure_sandbox_ready -> use."""

    async def test_lazy_init_flow(self, sandbox, _patch_create_provider):
        """Create -> stop -> lazy reconnect -> wait -> use."""
        sandbox_id = sandbox.sandbox_id
        await sandbox.stop_sandbox()

        # Reset runtime so reconnect is needed
        sandbox.runtime = None
        sandbox.sandbox_id = None

        # Start lazy init
        sandbox.start_lazy_init(sandbox_id)
        assert sandbox.is_ready() is False or sandbox.is_ready() is True  # may complete fast

        # Wait for ready
        await sandbox.ensure_sandbox_ready()
        assert sandbox.is_ready() is True

        # Should be operational
        wd = sandbox._work_dir
        result = await sandbox.execute_bash_command("echo lazy_ready", working_dir=wd)
        assert result["success"] is True
        assert "lazy_ready" in result["stdout"]

    async def test_is_ready_before_init(self, sandbox_minimal, _patch_create_provider):
        """Before any init, is_ready() should return False."""
        assert sandbox_minimal.is_ready() is False
