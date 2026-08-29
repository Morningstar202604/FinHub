"""Unit tests for ``AgentConfig.client_for_role`` and ``CredentialSource``.

``client_for_role`` must return a distinct ``.model_copy()`` so role-local
mutation never touches the shared main client, honor ``fallback_to_main``,
and read the raw ``llm_client`` field (not ``get_llm_client()``).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ptc_agent.config import AgentConfig, LLMConfig
from ptc_agent.config.agent import CredentialSource
from ptc_agent.config.core import (
    DaytonaConfig,
    FilesystemConfig,
    LoggingConfig,
    MCPConfig,
    SandboxConfig,
    SecurityConfig,
)


@dataclass
class _FakeClient:
    """Minimal stand-in for a BaseChatModel with ``.model_copy()``."""

    name: str
    streaming: bool = True
    _tag: object = field(default_factory=object)

    def model_copy(self) -> "_FakeClient":
        # New instance, equal config, fresh identity tag so identity differs.
        return replace(self, _tag=object())


def _config(**overrides) -> AgentConfig:
    """Minimal AgentConfig matching the construction pattern used elsewhere."""
    base = dict(
        llm=LLMConfig(name="main-model"),
        security=SecurityConfig(),
        logging=LoggingConfig(),
        sandbox=SandboxConfig(daytona=DaytonaConfig(api_key="test-key")),
        mcp=MCPConfig(),
        filesystem=FilesystemConfig(),
    )
    base.update(overrides)
    return AgentConfig(**base)


class TestClientForRole:
    def test_role_present_returns_distinct_copy_with_equal_config(self):
        stored = _FakeClient(name="compaction-model")
        cfg = _config(subsidiary_llm_clients={"compaction": stored})

        result = cfg.client_for_role("compaction")

        assert result is not None
        assert result is not stored  # model_copy -> distinct object
        assert result.name == stored.name
        assert result.streaming == stored.streaming

    def test_role_absent_no_fallback_returns_none(self):
        cfg = _config(subsidiary_llm_clients={})
        assert cfg.client_for_role("compaction") is None

    def test_role_absent_fallback_to_main_returns_copy_of_main(self):
        main = _FakeClient(name="main-client")
        cfg = _config(subsidiary_llm_clients={}, llm_client=main)

        result = cfg.client_for_role("compaction", fallback_to_main=True)

        assert result is not None
        assert result is not main
        assert result.name == main.name

    def test_role_absent_fallback_to_main_but_no_main_returns_none(self):
        cfg = _config(subsidiary_llm_clients={}, llm_client=None)
        assert cfg.client_for_role("compaction", fallback_to_main=True) is None


class TestCredentialSource:
    def test_default_on_fresh_config_is_none(self):
        cfg = _config()
        assert cfg.credential_source is CredentialSource.NONE
