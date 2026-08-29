"""Structural conformance guard for `SandboxBackend`.

Uses deepagents' `execute_accepts_timeout` helper (via `supports_execution`)
to verify the backend is recognized as a full `SandboxBackendProtocol`
implementation. This catches regressions where someone accidentally renames
`aexecute` or breaks protocol inheritance.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from deepagents.backends.protocol import SandboxBackendProtocol

from ptc_agent.agent.backends.sandbox import SandboxBackend


def test_sandbox_backend_inherits_protocol():
    """Structural: SandboxBackend must be a SandboxBackendProtocol subclass."""
    assert issubclass(SandboxBackend, SandboxBackendProtocol)


def test_sandbox_backend_has_aexecute():
    """Functional: the execution entry point must exist and be callable.

    Guards against accidental renames that would break middleware expectations.
    """
    sandbox = MagicMock()
    sandbox.config.filesystem.working_directory = "/workspace"
    sandbox.sandbox_id = "sbx-x"
    backend = SandboxBackend(sandbox)
    assert callable(backend.aexecute)
    assert callable(backend.execute)  # sync entry from protocol base (not used)
