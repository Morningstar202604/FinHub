"""M2-C sandbox quotas — config schema, validation, and 409 mapping."""

import pytest

from ptc_agent.config.core import (
    SandboxConfig,
    SandboxQuotaError,
    SandboxQuotas,
    assert_sandbox_quotas,
)
from ptc_agent.config.utils import create_sandbox_config


class TestSandboxQuotaSchema:
    def test_defaults_are_unbounded(self):
        q = SandboxQuotas()
        assert q.max_workspaces is None
        assert q.max_parallel_runs is None
        assert q.cpu_share is None
        assert q.memory_mb is None
        assert q.idle_minutes is None

    def test_configured_values_roundtrip(self):
        q = SandboxQuotas(max_workspaces=3, max_parallel_runs=1, memory_mb=8192)
        assert q.max_workspaces == 3
        assert q.max_parallel_runs == 1
        assert q.memory_mb == 8192

    def test_zero_is_valid_limit(self):
        q = SandboxQuotas(max_workspaces=0)
        assert q.max_workspaces == 0

    def test_negative_rejected(self):
        with pytest.raises(ValueError, match=">= 0"):
            SandboxQuotas(max_workspaces=-1)

    def test_sandbox_config_default_quotas(self):
        cfg = SandboxConfig()
        assert isinstance(cfg.quotas, SandboxQuotas)
        assert cfg.quotas.max_workspaces is None

    def test_yaml_parsing_reads_quotas(self):
        cfg = create_sandbox_config(
            {
                "sandbox": {
                    "provider": "daytona",
                    "quotas": {
                        "max_workspaces": 2,
                        "max_parallel_runs": 1,
                        "memory_mb": 8192,
                    },
                }
            }
        )
        assert cfg.quotas.max_workspaces == 2
        assert cfg.quotas.max_parallel_runs == 1
        assert cfg.quotas.memory_mb == 8192

    def test_yaml_absent_quotas_unbounded(self):
        cfg = create_sandbox_config({"sandbox": {"provider": "daytona"}})
        assert cfg.quotas.max_workspaces is None


class TestQuotaEnforcement:
    def test_within_limits_passes(self):
        q = SandboxQuotas(max_workspaces=3, max_parallel_runs=2)
        assert_sandbox_quotas(q, workspace_count=2, running_count=1)

    def test_workspace_cap_blocked(self):
        q = SandboxQuotas(max_workspaces=3)
        with pytest.raises(SandboxQuotaError) as exc:
            assert_sandbox_quotas(q, workspace_count=3, running_count=0)
        e = exc.value
        assert e.current == 3 and e.limit == 3
        assert "上限" in e.message

    def test_parallel_cap_blocked(self):
        q = SandboxQuotas(max_parallel_runs=1)
        with pytest.raises(SandboxQuotaError) as exc:
            assert_sandbox_quotas(q, workspace_count=0, running_count=1)
        assert exc.value.current == 1 and exc.value.limit == 1

    def test_unbounded_fields_never_fire(self):
        q = SandboxQuotas()  # all None
        assert_sandbox_quotas(q, workspace_count=999, running_count=999)

    def test_partial_config_only_checks_set_fields(self):
        q = SandboxQuotas(max_workspaces=1)  # parallel unbounded
        assert_sandbox_quotas(q, workspace_count=0, running_count=50)