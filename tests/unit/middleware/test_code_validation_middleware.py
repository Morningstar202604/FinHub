"""Tests for CodeValidationMiddleware.

Verifies that ExecuteCode tool calls referencing protected platform paths
(_internal/, .mcp_tokens, .mcp_secrets) are blocked with a system_warning.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage

from ptc_agent.agent.middleware.tool.code_validation import (
    CodeValidationMiddleware,
    _INTERNAL_PATH_PATTERNS,
)


def _make_request(tool_name: str, code: str = "", tool_call_id: str = "call_1"):
    request = MagicMock()
    request.tool_call = {
        "name": tool_name,
        "id": tool_call_id,
        "args": {"code": code},
    }
    return request


class TestCheckCode:
    """Verify _check_code detects protected path references."""

    def setup_method(self):
        self.mw = CodeValidationMiddleware()

    def test_blocks_internal_path(self):
        result = self.mw._check_code('open("_internal/config.json")')
        assert result is not None
        assert "system_warning" in result

    def test_blocks_mcp_tokens(self):
        result = self.mw._check_code('with open(".mcp_tokens") as f:')
        assert result is not None
        assert ".mcp_tokens" in result

    def test_blocks_mcp_secrets(self):
        result = self.mw._check_code('data = open(".mcp_secrets").read()')
        assert result is not None
        assert ".mcp_secrets" in result

    def test_allows_normal_code(self):
        result = self.mw._check_code(
            'import pandas as pd\ndf = pd.read_csv("data.csv")'
        )
        assert result is None

    def test_allows_empty_code(self):
        assert self.mw._check_code("") is None

    def test_all_internal_patterns_caught(self):
        """Every pattern in _INTERNAL_PATH_PATTERNS triggers a warning."""
        for pattern in _INTERNAL_PATH_PATTERNS:
            result = self.mw._check_code(f'x = "{pattern}"')
            assert result is not None, f"Pattern {pattern!r} was not caught"

    def test_allows_eval_exec_compile(self):
        """Builtins like eval/exec/compile are intentionally allowed."""
        for code in [
            "re.compile(r'\\d+')",
            "result = df.eval('A + B')",
            "executor.submit(fn)",
            "eval('1+1')",
            "exec('print(1)')",
        ]:
            assert self.mw._check_code(code) is None


class TestWrapToolCall:
    """Verify sync wrap_tool_call blocks protected paths in ExecuteCode."""

    def setup_method(self):
        self.mw = CodeValidationMiddleware()

    def test_blocks_execute_code_with_internal_path(self):
        request = _make_request("ExecuteCode", code='open("_internal/secrets")')
        handler = MagicMock()

        result = self.mw.wrap_tool_call(request, handler)

        assert isinstance(result, ToolMessage)
        assert "system_warning" in result.content
        handler.assert_not_called()

    def test_passes_safe_execute_code(self):
        request = _make_request("ExecuteCode", code='print("hello")')
        expected = ToolMessage(content="hello", tool_call_id="call_1")
        handler = MagicMock(return_value=expected)

        result = self.mw.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result.content == "hello"

    def test_ignores_non_execute_code_tools(self):
        """Other tools are not scanned — even if code contains protected paths."""
        request = _make_request("read_file", code="_internal/secret")
        handler = MagicMock(return_value="ok")

        result = self.mw.wrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result == "ok"


class TestAwrapToolCall:
    """Verify async awrap_tool_call blocks protected paths."""

    def setup_method(self):
        self.mw = CodeValidationMiddleware()

    @pytest.mark.asyncio
    async def test_blocks_execute_code_with_internal_path(self):
        request = _make_request("ExecuteCode", code='open("_internal/tokens")')
        handler = AsyncMock()

        result = await self.mw.awrap_tool_call(request, handler)

        assert isinstance(result, ToolMessage)
        assert "system_warning" in result.content
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_safe_execute_code(self):
        request = _make_request("ExecuteCode", code="x = 1 + 2")
        expected = ToolMessage(content="3", tool_call_id="call_1")
        handler = AsyncMock(return_value=expected)

        result = await self.mw.awrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
        assert result.content == "3"

    @pytest.mark.asyncio
    async def test_ignores_non_execute_code_tools(self):
        request = _make_request("bash", code="cat _internal/file")
        handler = AsyncMock(return_value="ok")

        result = await self.mw.awrap_tool_call(request, handler)

        handler.assert_called_once_with(request)
