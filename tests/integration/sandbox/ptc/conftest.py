from __future__ import annotations

import pytest_asyncio

from ptc_agent.core.sandbox.ptc_sandbox import PTCSandbox


async def _setup_ptc_sandbox(config) -> PTCSandbox:
    """Create and configure a PTCSandbox (shared helper)."""
    sb = PTCSandbox(config)
    await sb.setup_sandbox_workspace()
    assert sb.runtime is not None
    assert sb.sandbox_id is not None

    actual_work_dir = await sb.runtime.fetch_working_dir()
    sb.config.filesystem.working_directory = actual_work_dir
    sb.config.filesystem.allowed_directories = [actual_work_dir, "/tmp"]
    sb.TOKEN_FILE_PATH = f"{actual_work_dir}/_internal/.mcp_tokens.json"
    sb.UNIFIED_MANIFEST_PATH = f"{actual_work_dir}/_internal/.sandbox_manifest.json"
    return sb


@pytest_asyncio.fixture
async def sandbox(core_config, _patch_create_provider):
    """A PTCSandbox with workspace set up, ready for operations.

    Function-scoped: use for destructive tests (cleanup, reconnection, lazy_init).
    For non-destructive tests, prefer ``shared_sandbox`` — much faster on Docker.
    """
    sb = await _setup_ptc_sandbox(core_config)
    yield sb
    try:
        await sb.cleanup()
    except Exception:
        pass


@pytest_asyncio.fixture(scope="class", loop_scope="class")
async def shared_sandbox(class_core_config, _class_patch_create_provider):
    """Class-scoped PTCSandbox shared across all tests in a class.

    Dramatically faster on Docker/Daytona (1 sandbox per class instead of
    per test). Use for non-destructive tests that don't stop/delete/cleanup
    the sandbox.
    """
    sb = await _setup_ptc_sandbox(class_core_config)
    yield sb
    try:
        await sb.cleanup()
    except Exception:
        pass


@pytest_asyncio.fixture
async def sandbox_minimal(core_config, _patch_create_provider):
    """A PTCSandbox constructed but NOT set up -- for testing init flow."""
    sb = PTCSandbox(core_config)
    yield sb
    try:
        if sb.runtime:
            await sb.cleanup()
    except Exception:
        pass
