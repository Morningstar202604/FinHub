from __future__ import annotations

import json
from unittest.mock import patch

import io
import pytest

from tests.integration.sandbox.metrics.collector import (
    MetricsCollector,
    OperationMetric,
    RetryMetric,
)
from tests.integration.sandbox.metrics.reporter import (
    _percentile,
    print_terminal_summary,
    write_json_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_operation(**overrides) -> OperationMetric:
    defaults = dict(
        provider="memory",
        category="exec",
        operation="echo",
        test_name="test_example",
        duration_s=0.05,
        success=True,
    )
    defaults.update(overrides)
    return OperationMetric(**defaults)


def _make_retry(**overrides) -> RetryMetric:
    defaults = dict(
        provider="memory",
        operation="create",
        test_name="test_example",
        total_attempts=3,
        transient_errors=2,
        final_success=True,
        total_duration_s=1.5,
    )
    defaults.update(overrides)
    return RetryMetric(**defaults)


def _collector_with_two_providers() -> MetricsCollector:
    """Return an enabled collector populated with operations from two providers."""
    collector = MetricsCollector()
    collector.enable()

    # memory provider operations
    for dur in [0.04, 0.05, 0.06]:
        collector.record_operation(
            _make_operation(provider="memory", category="exec", duration_s=dur)
        )
    for dur in [0.10, 0.12, 0.14]:
        collector.record_operation(
            _make_operation(provider="memory", category="code_run", duration_s=dur)
        )

    # docker provider operations
    for dur in [0.14, 0.15, 0.16]:
        collector.record_operation(
            _make_operation(provider="docker", category="exec", duration_s=dur)
        )
    for dur in [0.30, 0.35, 0.40]:
        collector.record_operation(
            _make_operation(provider="docker", category="code_run", duration_s=dur)
        )

    # A retry record
    collector.record_retry(_make_retry(provider="docker"))

    return collector


# ---------------------------------------------------------------------------
# _percentile tests
# ---------------------------------------------------------------------------

class TestPercentile:
    def test_percentile_basic(self):
        values = [1, 2, 3, 4, 5]
        assert _percentile(values, 50) == 3.0
        # p95: index = 0.95 * 4 = 3.8 => 4 + 0.8*(5-4) = 4.8
        assert _percentile(values, 95) == pytest.approx(4.8)

    def test_percentile_empty(self):
        assert _percentile([], 50) == 0.0

    def test_percentile_single(self):
        assert _percentile([42.0], 50) == 42.0
        assert _percentile([42.0], 95) == 42.0
        assert _percentile([42.0], 0) == 42.0


# ---------------------------------------------------------------------------
# write_json_report tests
# ---------------------------------------------------------------------------

class TestWriteJsonReport:
    def test_write_json_report_structure(self, tmp_path):
        collector = _collector_with_two_providers()
        output = str(tmp_path / "report.json")

        write_json_report(collector, output)

        with open(output) as f:
            data = json.load(f)

        # Top-level keys
        assert "timestamp" in data
        assert "providers_tested" in data
        assert "summary" in data
        assert "cross_provider_comparison" in data
        assert "operations" in data
        assert "retries" in data

        # Providers
        assert sorted(data["providers_tested"]) == ["docker", "memory"]

        # Summary structure for each provider
        for provider in ("memory", "docker"):
            prov_summary = data["summary"][provider]
            assert "total_operations" in prov_summary
            assert "total_duration_s" in prov_summary
            assert "success_rate" in prov_summary
            assert "by_category" in prov_summary
            for _cat, cat_stats in prov_summary["by_category"].items():
                assert "count" in cat_stats
                assert "mean_s" in cat_stats
                assert "median_s" in cat_stats
                assert "p95_s" in cat_stats
                assert "max_s" in cat_stats
                assert "min_s" in cat_stats

        # Operations array: 6 memory + 6 docker = 12
        assert len(data["operations"]) == 12

        # Retries array: 1
        assert len(data["retries"]) == 1

    def test_write_json_report_empty_collector(self, tmp_path):
        collector = MetricsCollector()
        collector.enable()
        output = str(tmp_path / "empty.json")

        write_json_report(collector, output)

        with open(output) as f:
            data = json.load(f)

        assert data["providers_tested"] == []
        assert data["summary"] == {}
        assert data["cross_provider_comparison"] == {}
        assert data["operations"] == []
        assert data["retries"] == []


# ---------------------------------------------------------------------------
# print_terminal_summary tests
# ---------------------------------------------------------------------------

class TestTerminalSummary:
    def test_terminal_summary_format(self):
        collector = _collector_with_two_providers()

        buf = io.StringIO()
        with patch("sys.stderr", buf):
            print_terminal_summary(collector)

        output = buf.getvalue()

        # Header
        assert "Sandbox Metrics Summary" in output

        # Provider names
        assert "memory" in output
        assert "docker" in output

        # Column headers
        assert "Provider" in output
        assert "Ops" in output
        assert "Duration" in output
        assert "Success" in output
        assert "Exec (p50)" in output
        assert "CodeRun (p50)" in output
        assert "FileIO (p50)" in output

        # Footer
        assert "Full report:" in output


# ---------------------------------------------------------------------------
# cross_provider_comparison tests
# ---------------------------------------------------------------------------

class TestCrossProviderComparison:
    def test_cross_provider_comparison(self, tmp_path):
        collector = _collector_with_two_providers()
        output = str(tmp_path / "comparison.json")

        write_json_report(collector, output)

        with open(output) as f:
            data = json.load(f)

        comparison = data["cross_provider_comparison"]

        # Both providers have "exec" and "code_run" categories
        assert "exec" in comparison
        assert "code_run" in comparison

        # exec comparison
        exec_cmp = comparison["exec"]
        assert "memory_mean_s" in exec_cmp
        assert "docker_mean_s" in exec_cmp
        assert "slowdown_factor" in exec_cmp
        # "docker" is alphabetically first, so it is the baseline.
        assert "memory_vs_docker" in exec_cmp["slowdown_factor"]

        # The memory exec mean (0.05) is 1/3 of the docker exec mean (0.15)
        docker_mean = exec_cmp["docker_mean_s"]
        memory_mean = exec_cmp["memory_mean_s"]
        assert docker_mean > memory_mean
        assert exec_cmp["slowdown_factor"]["memory_vs_docker"] == pytest.approx(1.0 / 3.0, rel=0.01)
