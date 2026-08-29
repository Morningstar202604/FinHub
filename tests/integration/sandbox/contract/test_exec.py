"""Contract tests for SandboxRuntime.exec() -- shell command execution."""

from __future__ import annotations

import pytest

from ptc_agent.core.sandbox.runtime import ExecResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio(loop_scope="class")
class TestRuntimeExec:
    """SandboxRuntime.exec() -- shell command execution."""

    async def test_simple_command(self, shared_runtime, timed):
        async with timed("exec", "simple"):
            result = await shared_runtime.exec("echo hello")
        assert isinstance(result, ExecResult)
        assert result.exit_code == 0
        assert "hello" in result.stdout

    async def test_exit_code_nonzero(self, shared_runtime, timed):
        async with timed("exec", "exit_code_nonzero"):
            result = await shared_runtime.exec("exit 42")
        assert result.exit_code == 42

    async def test_command_with_env_var(self, shared_runtime, timed):
        async with timed("exec", "env_var"):
            result = await shared_runtime.exec("echo $TEST_VAR")
        assert "hello" in result.stdout

    async def test_multiline_output(self, shared_runtime, timed):
        async with timed("exec", "multiline"):
            result = await shared_runtime.exec("echo line1 && echo line2 && echo line3")
        lines = result.stdout.strip().split("\n")
        assert len(lines) == 3

    async def test_mkdir_and_ls(self, shared_runtime, timed):
        async with timed("exec", "mkdir_and_ls"):
            await shared_runtime.exec("mkdir -p testdir_exec/sub")
            result = await shared_runtime.exec("ls testdir_exec")
        assert "sub" in result.stdout

    async def test_pipe_commands(self, shared_runtime, timed):
        async with timed("exec", "pipe"):
            result = await shared_runtime.exec("echo 'a b c' | wc -w")
        assert "3" in result.stdout
