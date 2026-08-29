from __future__ import annotations

import pytest

from ptc_agent.core.sandbox.runtime import RuntimeState

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestReconnection:
    """PTCSandbox.reconnect() -- stop -> reconnect -> verify state."""

    async def test_reconnect_from_stopped(self, sandbox, _patch_create_provider):
        sandbox_id = sandbox.sandbox_id
        wd = sandbox._work_dir

        # Upload data before stopping
        await sandbox.aupload_file_bytes(f"{wd}/data/before_stop.txt", b"preserved")

        # Stop
        await sandbox.stop_sandbox()

        # Reconnect
        await sandbox.reconnect(sandbox_id)
        assert sandbox.runtime is not None
        assert await sandbox.runtime.get_state() == RuntimeState.RUNNING

        # Data should be preserved
        content = await sandbox.adownload_file_bytes(f"{wd}/data/before_stop.txt")
        assert content == b"preserved"

    async def test_reconnect_already_running(self, sandbox, _patch_create_provider):
        """Reconnecting to a running sandbox should be a no-op start."""
        sandbox_id = sandbox.sandbox_id
        await sandbox.reconnect(sandbox_id)
        assert await sandbox.runtime.get_state() == RuntimeState.RUNNING

    async def test_reconnect_preserves_exec(self, sandbox, _patch_create_provider):
        """After reconnect, exec should work normally."""
        sandbox_id = sandbox.sandbox_id
        wd = sandbox._work_dir
        await sandbox.stop_sandbox()
        await sandbox.reconnect(sandbox_id)

        result = await sandbox.execute_bash_command("echo reconnected", working_dir=wd)
        assert result["success"] is True
        assert "reconnected" in result["stdout"]
