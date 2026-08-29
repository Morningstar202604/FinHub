"""Contract tests for SandboxProvider.create / get / close semantics."""

from __future__ import annotations

import pytest

from ptc_agent.core.sandbox.runtime import RuntimeState

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestProviderLifecycle:
    """SandboxProvider.create / get / close contract."""

    async def test_create_returns_running_runtime(self, sandbox_provider, timed):
        async with timed("lifecycle", "create"):
            runtime = await sandbox_provider.create(env_vars={"KEY": "val"})
        try:
            assert runtime.id is not None
            assert len(runtime.id) > 0
            state = await runtime.get_state()
            assert state == RuntimeState.RUNNING
        finally:
            await runtime.delete()

    async def test_create_unique_ids(self, sandbox_provider, timed):
        async with timed("lifecycle", "create_first"):
            r1 = await sandbox_provider.create()
        async with timed("lifecycle", "create_second"):
            r2 = await sandbox_provider.create()
        try:
            assert r1.id != r2.id
        finally:
            await r1.delete()
            await r2.delete()

    async def test_get_returns_same_runtime(self, sandbox_provider, timed):
        created = await sandbox_provider.create()
        try:
            async with timed("lifecycle", "get"):
                retrieved = await sandbox_provider.get(created.id)
            assert retrieved.id == created.id
        finally:
            await created.delete()

    async def test_env_vars_passed_to_runtime(self, sandbox_provider, timed):
        runtime = await sandbox_provider.create(env_vars={"MY_KEY": "my_val"})
        try:
            async with timed("lifecycle", "exec_env_check"):
                result = await runtime.exec("echo $MY_KEY")
            assert "my_val" in result.stdout
        finally:
            await runtime.delete()
