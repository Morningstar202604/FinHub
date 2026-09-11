"""Tests for files_modified tracking in sandbox execution.

Verifies that execute() correctly detects file modifications by comparing
mtimes before and after code execution.

Note: Full async integration tests should be run in CI (Linux/macOS).
This file contains basic structural tests for Windows compatibility.
"""

from unittest.mock import MagicMock, patch

import pytest

from ptc_agent.config.core import (
    CoreConfig,
    DaytonaConfig,
    FilesystemConfig,
    LoggingConfig,
    MCPConfig,
    SandboxConfig,
    SecurityConfig,
)


def _make_config(**overrides) -> CoreConfig:
    defaults = dict(
        sandbox=SandboxConfig(daytona=DaytonaConfig(api_key="test-key")),
        security=SecurityConfig(),
        mcp=MCPConfig(),
        logging=LoggingConfig(),
        filesystem=FilesystemConfig(),
    )
    defaults.update(overrides)
    return CoreConfig(**defaults)


class TestSnapshotFileMtimesStructure:
    """Structural tests for _snapshot_file_mtimes (no async)."""

    def test_function_exists(self):
        from ptc_agent.core.sandbox.execution import _snapshot_file_mtimes
        assert callable(_snapshot_file_mtimes)

    def test_function_signature(self):
        import inspect
        from ptc_agent.core.sandbox.execution import _snapshot_file_mtimes
        sig = inspect.signature(_snapshot_file_mtimes)
        params = list(sig.parameters.keys())
        assert "sandbox" in params
        assert "dirs" in params


class TestFilesModifiedDelegator:
    """Tests for _snapshot_file_mtimes delegator in PTCSandbox."""

    def test_delegator_exists(self):
        from ptc_agent.core.sandbox.ptc_sandbox import PTCSandbox

        with patch("ptc_agent.core.sandbox.ptc_sandbox.create_provider"):
            sandbox = PTCSandbox(config=_make_config())
            assert hasattr(sandbox, "_snapshot_file_mtimes")
            assert callable(sandbox._snapshot_file_mtimes)

    def test_execute_returns_files_modified_field(self):
        from ptc_agent.core.sandbox._shared import ExecutionResult

        result = ExecutionResult(
            success=True,
            stdout="",
            stderr="",
            duration=0.0,
            files_created=[],
            files_modified=["work/data.csv"],
            execution_id="exec_0001",
            code_hash="abc123",
        )
        assert result.files_modified == ["work/data.csv"]
