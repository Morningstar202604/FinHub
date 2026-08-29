"""Bash command execution helper.

This is used by the CLI when the user types input beginning with '!'.
In API mode, the agent ultimately executes commands inside the sandbox,
but this helper is still useful for tests and for any direct sandbox usage.
"""

from __future__ import annotations

from typing import Any

from ptc_cli.core import console


async def execute_bash_command(command: str, *, sandbox: Any | None, timeout: int = 60) -> None:
    """Execute a bash command in the sandbox.

    Args:
        command: The raw user command (may start with '!').
        sandbox: Sandbox-like object with execute_bash_command().
        timeout: Timeout in seconds.
    """

    raw = (command or "").strip()
    if not raw or raw == "!":
        console.print("[yellow]No command specified[/yellow]")
        return

    if sandbox is None:
        console.print("[yellow]Sandbox not initialized[/yellow]")
        return

    cmd = raw[1:].strip() if raw.startswith("!") else raw
    if not cmd:
        console.print("[yellow]No command specified[/yellow]")
        return

    try:
        result = await sandbox.execute_bash_command(cmd, timeout=timeout)
    except TimeoutError as e:
        console.print(f"[red]Command timed out:[/red] {e}")
        return
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Error executing command:[/red] {e}")
        return

    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    exit_code = result.get("exit_code")

    if stdout:
        console.print(stdout)
    if stderr:
        console.print(stderr, style="red")

    if exit_code not in (None, 0):
        console.print(f"[dim]Exit code: {exit_code}[/dim]")
