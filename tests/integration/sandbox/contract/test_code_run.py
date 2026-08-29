"""Contract tests for SandboxRuntime.code_run() -- Python code execution."""

from __future__ import annotations

import pytest

from ptc_agent.core.sandbox.runtime import CodeRunResult

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.asyncio(loop_scope="class")
class TestRuntimeCodeRun:
    """SandboxRuntime.code_run() -- Python code execution."""

    async def test_simple_python(self, shared_runtime, timed):
        async with timed("code_run", "simple"):
            result = await shared_runtime.code_run("print(2 + 2)")
        assert isinstance(result, CodeRunResult)
        assert result.exit_code == 0
        assert "4" in result.stdout

    async def test_python_with_env(self, shared_runtime, timed):
        async with timed("code_run", "with_env"):
            result = await shared_runtime.code_run(
                "import os; print(os.environ.get('CUSTOM_VAR', 'missing'))",
                env={"CUSTOM_VAR": "injected"},
            )
        assert "injected" in result.stdout

    async def test_python_error(self, shared_runtime, timed):
        async with timed("code_run", "error"):
            result = await shared_runtime.code_run("raise ValueError('test error')")
        assert result.exit_code != 0
        assert "ValueError" in result.stderr or "ValueError" in result.stdout

    async def test_python_imports(self, shared_runtime, timed):
        async with timed("code_run", "imports"):
            result = await shared_runtime.code_run(
                "import json; print(json.dumps({'key': 'value'}))"
            )
        assert result.exit_code == 0
        assert '"key"' in result.stdout

    async def test_python_file_creation(self, shared_runtime, timed):
        """Code can create files in the working directory."""
        wd = await shared_runtime.fetch_working_dir()
        async with timed("code_run", "file_creation"):
            await shared_runtime.code_run(
                f"with open('{wd}/coderun_output.txt', 'w') as f: f.write('hello from python')"
            )
        content = await shared_runtime.download_file(f"{wd}/coderun_output.txt")
        assert content == b"hello from python"

    async def test_python_multiline(self, shared_runtime, timed):
        code = """\
data = [1, 2, 3, 4, 5]
total = sum(data)
avg = total / len(data)
print(f"sum={total}, avg={avg}")
"""
        async with timed("code_run", "multiline"):
            result = await shared_runtime.code_run(code)
        assert result.exit_code == 0
        assert "sum=15" in result.stdout
        assert "avg=3.0" in result.stdout
