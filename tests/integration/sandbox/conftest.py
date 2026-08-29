"""Fixtures for provider-agnostic sandbox integration tests.

Provider selection via env vars:
    SANDBOX_TEST_PROVIDERS=memory,docker   (comma-separated, preferred)
    SANDBOX_TEST_PROVIDER=memory           (singular fallback, default)

Available providers:
    memory   (default) -- in-process MemoryProvider, no infra needed
    daytona  -- real Daytona sandbox (requires DAYTONA_API_KEY)
    docker   -- Docker containers (requires Docker daemon + langalpha-sandbox image)

Usage:
    # Default: in-memory (fast, no infra)
    uv run pytest tests/integration/sandbox/ -v

    # Against real Daytona:
    SANDBOX_TEST_PROVIDERS=daytona DAYTONA_API_KEY=... uv run pytest tests/integration/sandbox/ -v

    # Multiple providers at once:
    SANDBOX_TEST_PROVIDERS=memory,docker uv run pytest tests/integration/sandbox/ -v

    # Legacy (still works):
    SANDBOX_TEST_PROVIDER=docker uv run pytest tests/integration/sandbox/ -v

IMPORTANT: When using real providers, every sandbox created during tests is
deleted in fixture teardown to avoid resource leaks.
"""

from __future__ import annotations

import os
import shutil
from unittest.mock import patch

import pytest
import pytest_asyncio

from ptc_agent.config.core import (
    CoreConfig,
    DaytonaConfig,
    DockerConfig,
    FilesystemConfig,
    LoggingConfig,
    MCPConfig,
    SandboxConfig,
    SecurityConfig,
)
from ptc_agent.core.sandbox.runtime import SandboxProvider, SandboxRuntime

from .memory_provider import MemoryProvider, MemoryRuntime

# Prevent pytest from descending into metrics/ during collection (it has no
# test files and its conftest is registered via root conftest pytest_plugins).
collect_ignore = [os.path.join(os.path.dirname(__file__), "metrics")]

# ---------------------------------------------------------------------------
# Multi-provider selection
# ---------------------------------------------------------------------------


def _requested_providers() -> list[str]:
    """Parse SANDBOX_TEST_PROVIDERS (comma-separated) or fall back to SANDBOX_TEST_PROVIDER."""
    plural = os.getenv("SANDBOX_TEST_PROVIDERS")
    if plural:
        return [p.strip().lower() for p in plural.split(",") if p.strip()]
    singular = os.getenv("SANDBOX_TEST_PROVIDER", "memory")
    return [singular.strip().lower()]


REQUESTED_PROVIDERS = _requested_providers()


def _can_run_provider(name: str) -> bool:
    if name == "memory":
        return True
    if name == "daytona":
        return bool(os.environ.get("DAYTONA_API_KEY"))
    if name == "docker":
        return shutil.which("docker") is not None
    return False


# ---------------------------------------------------------------------------
# Shared config builder
# ---------------------------------------------------------------------------


def _make_core_config(
    working_directory: str,
    provider: str = "daytona",
    api_key: str = "test-key",
    base_url: str = "https://app.daytona.io/api",
    docker_config: DockerConfig | None = None,
) -> CoreConfig:
    """Build a CoreConfig suitable for testing."""
    return CoreConfig(
        sandbox=SandboxConfig(
            provider=provider if provider in ("daytona", "docker") else "daytona",
            daytona=DaytonaConfig(
                api_key=api_key,
                base_url=base_url,
                snapshot_enabled=False,  # skip snapshot for tests
            ),
            docker=docker_config or DockerConfig(),
        ),
        security=SecurityConfig(
            max_execution_time=60,
            max_code_length=50000,
            max_file_size=10485760,
            enable_code_validation=False,
            allowed_imports=[],
            blocked_patterns=[],
        ),
        mcp=MCPConfig(servers=[], tool_discovery_enabled=False),
        logging=LoggingConfig(),
        filesystem=FilesystemConfig(
            working_directory=working_directory,
            allowed_directories=[working_directory, "/tmp"],
            denied_directories=[],
            enable_path_validation=True,
        ),
    )


# ---------------------------------------------------------------------------
# Parameterized provider name
# ---------------------------------------------------------------------------


@pytest.fixture(
    scope="class",
    params=[
        pytest.param(
            p,
            id=p,
            marks=(
                [getattr(pytest.mark, f"provider_{p}")]
                if p != "memory"
                else []
            ),
        )
        for p in REQUESTED_PROVIDERS
        if _can_run_provider(p)
    ],
)
def provider_name(request) -> str:
    """The name of the sandbox provider under test (parameterized).

    Class-scoped so that class-scoped fixtures (shared_sandbox,
    shared_runtime) can depend on it.  Function-scoped fixtures
    like sandbox_runtime can still use it (narrower scope is OK).
    """
    return request.param


# ---------------------------------------------------------------------------
# Provider fixtures — dual-mode (memory or real)
# ---------------------------------------------------------------------------


@pytest.fixture
def sandbox_base_dir(tmp_path):
    """Temporary directory for sandbox working dirs (memory provider only)."""
    d = tmp_path / "sandboxes"
    d.mkdir()
    return str(d)


@pytest.fixture(scope="class")
def class_sandbox_base_dir(tmp_path_factory):
    """Class-scoped temp directory for sandbox working dirs."""
    d = tmp_path_factory.mktemp("sandboxes")
    return str(d)


@pytest.fixture
def memory_provider(sandbox_base_dir) -> MemoryProvider:
    """Fresh MemoryProvider -- always available for memory-only runtime tests."""
    return MemoryProvider(base_dir=sandbox_base_dir)


@pytest.fixture(scope="class")
def class_memory_provider(class_sandbox_base_dir) -> MemoryProvider:
    """Class-scoped MemoryProvider for shared fixtures."""
    return MemoryProvider(base_dir=class_sandbox_base_dir)


@pytest_asyncio.fixture
async def memory_runtime(memory_provider) -> MemoryRuntime:
    """A single MemoryRuntime -- always memory, used by test_runtime_lifecycle.py."""
    runtime = await memory_provider.create(env_vars={"TEST_VAR": "hello"})
    yield runtime
    try:
        state = await runtime.get_state()
        if state.value == "running":
            await runtime.stop()
    except Exception:
        pass


async def _make_provider(
    name: str, sandbox_base_dir: str | None = None
):
    """Internal: build and yield a provider for the given name, then close it."""
    if name == "daytona":
        api_key = os.environ.get("DAYTONA_API_KEY", "")
        if not api_key:
            pytest.skip("DAYTONA_API_KEY not set")
        base_url = os.environ.get(
            "DAYTONA_BASE_URL", "https://app.daytona.io/api"
        )
        from ptc_agent.core.sandbox.providers.daytona import DaytonaProvider

        provider = DaytonaProvider(
            DaytonaConfig(
                api_key=api_key,
                base_url=base_url,
                snapshot_enabled=False,
            )
        )
        yield provider
        await provider.close()
    elif name == "docker":
        from ptc_agent.core.sandbox.providers.docker import DockerProvider

        working_dir = os.environ.get("DOCKER_SANDBOX_WORK_DIR", "/home/workspace")
        provider = DockerProvider(
            DockerConfig(
                image=os.environ.get("DOCKER_SANDBOX_IMAGE", "langalpha-sandbox:latest"),
                dev_mode=os.environ.get("DOCKER_SANDBOX_DEV_MODE", "").lower() in ("1", "true"),
                host_work_dir=os.environ.get("DOCKER_SANDBOX_HOST_DIR"),
            ),
            working_dir=working_dir,
        )
        yield provider
        await provider.close()
    else:
        yield MemoryProvider(base_dir=sandbox_base_dir or "/tmp/sandbox-test")


@pytest_asyncio.fixture
async def sandbox_provider(provider_name, sandbox_base_dir) -> SandboxProvider:
    """Function-scoped provider -- fresh per test, parameterized by provider_name."""
    async for provider in _make_provider(provider_name, sandbox_base_dir):
        yield provider


@pytest_asyncio.fixture(scope="class", loop_scope="class")
async def class_sandbox_provider(tmp_path_factory, provider_name) -> SandboxProvider:
    """Class-scoped provider -- shared across all tests in a class."""
    base_dir = str(tmp_path_factory.mktemp("sandboxes"))
    async for provider in _make_provider(provider_name, base_dir):
        yield provider


@pytest_asyncio.fixture
async def sandbox_runtime(sandbox_provider) -> SandboxRuntime:
    """A fresh runtime per test, with guaranteed cleanup.

    Use for tests that stop/start/delete the sandbox.
    For read-only tests (exec, code_run, file_io), prefer ``shared_runtime``
    which reuses one container across the class -- much faster on Docker.
    """
    runtime = await sandbox_provider.create(env_vars={"TEST_VAR": "hello"})
    yield runtime
    # Guaranteed cleanup: delete the sandbox no matter what
    try:
        state = await runtime.get_state()
        if state.value in ("running", "stopped", "archived"):
            await runtime.delete()
    except Exception:
        pass


@pytest_asyncio.fixture(scope="class", loop_scope="class")
async def shared_runtime(class_sandbox_provider) -> SandboxRuntime:
    """Class-scoped runtime -- one container shared across all tests in a class.

    Dramatically faster on Docker (1 create/delete per class instead of per test).
    Use for non-destructive tests that don't stop/start the sandbox.
    """
    runtime = await class_sandbox_provider.create(env_vars={"TEST_VAR": "hello"})
    yield runtime
    try:
        state = await runtime.get_state()
        if state.value in ("running", "stopped", "archived"):
            await runtime.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Core config fixture -- adapts to provider
# ---------------------------------------------------------------------------


def _build_core_config(provider_name: str, base_dir: str) -> CoreConfig:
    """Build a CoreConfig for the given provider (shared helper)."""
    if provider_name == "daytona":
        api_key = os.environ.get("DAYTONA_API_KEY", "")
        if not api_key:
            pytest.skip("DAYTONA_API_KEY not set")
        base_url = os.environ.get(
            "DAYTONA_BASE_URL", "https://app.daytona.io/api"
        )
        return _make_core_config(
            working_directory="/home/workspace",
            provider="daytona",
            api_key=api_key,
            base_url=base_url,
        )
    elif provider_name == "docker":
        working_dir = os.environ.get("DOCKER_SANDBOX_WORK_DIR", "/home/workspace")
        return _make_core_config(
            working_directory=working_dir,
            provider="docker",
            docker_config=DockerConfig(
                image=os.environ.get("DOCKER_SANDBOX_IMAGE", "langalpha-sandbox:latest"),
                dev_mode=os.environ.get("DOCKER_SANDBOX_DEV_MODE", "").lower() in ("1", "true"),
                host_work_dir=os.environ.get("DOCKER_SANDBOX_HOST_DIR"),
            ),
        )

    # memory provider -- use temp dir as working directory
    return _make_core_config(
        working_directory=base_dir,
        provider="daytona",  # value ignored since create_provider is patched
        api_key="test-key",
    )


@pytest.fixture
def core_config(provider_name, sandbox_base_dir) -> CoreConfig:
    """CoreConfig adapted to the active test provider."""
    return _build_core_config(provider_name, sandbox_base_dir)


@pytest.fixture(scope="class")
def class_core_config(provider_name, class_sandbox_base_dir) -> CoreConfig:
    """Class-scoped CoreConfig adapted to the active test provider."""
    return _build_core_config(provider_name, class_sandbox_base_dir)


# ---------------------------------------------------------------------------
# Provider patching -- only for memory provider
# ---------------------------------------------------------------------------


@pytest.fixture
def _patch_create_provider(memory_provider, provider_name):
    """Patch create_provider for memory provider, or no-op for real providers."""
    if provider_name != "memory":
        yield None
        return

    with patch(
        "ptc_agent.core.sandbox.ptc_sandbox.create_provider",
        return_value=memory_provider,
    ):
        yield memory_provider


@pytest.fixture(scope="class")
def _class_patch_create_provider(class_memory_provider, provider_name):
    """Class-scoped create_provider patch -- for memory provider only."""
    if provider_name != "memory":
        yield None
        return

    with patch(
        "ptc_agent.core.sandbox.ptc_sandbox.create_provider",
        return_value=class_memory_provider,
    ):
        yield class_memory_provider


# ---------------------------------------------------------------------------
# Metrics helper
# ---------------------------------------------------------------------------


@pytest.fixture
def timed(metrics_collector, provider_name, request):
    """Convenience wrapper for metrics_collector.timed() with provider context."""
    def _timed(category: str, operation: str):
        return metrics_collector.timed(
            provider_name, category, operation, request.node.name
        )
    return _timed
