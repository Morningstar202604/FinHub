from __future__ import annotations

import pytest

from tests.integration.sandbox.metrics.collector import (
    MetricsCollector,
    OperationMetric,
    RetryMetric,
)


def _make_operation(**overrides) -> OperationMetric:
    defaults = dict(
        provider="memory",
        category="lifecycle",
        operation="create",
        test_name="test_example",
        duration_s=0.5,
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


class TestMetricsCollectorState:
    def test_collector_disabled_by_default(self):
        collector = MetricsCollector()
        assert collector.enabled is False

    def test_collector_enable(self):
        collector = MetricsCollector()
        collector.enable()
        assert collector.enabled is True


class TestMetricsCollectorRecording:
    def test_disabled_collector_ignores_records(self):
        collector = MetricsCollector()
        collector.record_operation(_make_operation())
        assert len(collector.operations) == 0

    def test_enabled_collector_records_operation(self):
        collector = MetricsCollector()
        collector.enable()
        metric = _make_operation(provider="docker", operation="exec.echo")
        collector.record_operation(metric)
        assert len(collector.operations) == 1
        assert collector.operations[0].provider == "docker"
        assert collector.operations[0].operation == "exec.echo"

    def test_enabled_collector_records_retry(self):
        collector = MetricsCollector()
        collector.enable()
        metric = _make_retry(provider="daytona", total_attempts=5)
        collector.record_retry(metric)
        assert len(collector.retries) == 1
        assert collector.retries[0].provider == "daytona"
        assert collector.retries[0].total_attempts == 5


class TestTimedContext:
    @pytest.mark.asyncio(loop_scope="function")
    async def test_timed_records_metric(self):
        collector = MetricsCollector()
        collector.enable()
        async with collector.timed("memory", "lifecycle", "create", "test_timed"):
            pass  # simulate a fast operation
        assert len(collector.operations) == 1
        recorded = collector.operations[0]
        assert recorded.provider == "memory"
        assert recorded.category == "lifecycle"
        assert recorded.operation == "create"
        assert recorded.test_name == "test_timed"
        assert recorded.duration_s > 0
        assert recorded.success is True
        assert recorded.error is None

    @pytest.mark.asyncio(loop_scope="function")
    async def test_timed_captures_error(self):
        collector = MetricsCollector()
        collector.enable()
        with pytest.raises(ValueError, match="boom"):
            async with collector.timed("docker", "exec", "run", "test_err"):
                raise ValueError("boom")
        assert len(collector.operations) == 1
        recorded = collector.operations[0]
        assert recorded.success is False
        assert recorded.error == "boom"

    @pytest.mark.asyncio(loop_scope="function")
    async def test_timed_does_not_suppress_exception(self):
        collector = MetricsCollector()
        collector.enable()
        with pytest.raises(RuntimeError):
            async with collector.timed("memory", "lifecycle", "create", "test_propagate"):
                raise RuntimeError("should propagate")

    @pytest.mark.asyncio(loop_scope="function")
    async def test_timed_bytes_transferred(self):
        collector = MetricsCollector()
        collector.enable()
        async with collector.timed("docker", "file_io", "upload", "test_bytes") as ctx:
            ctx.bytes_transferred = 2048
        assert len(collector.operations) == 1
        recorded = collector.operations[0]
        assert recorded.bytes_transferred == 2048


class TestThroughputCalculation:
    def test_throughput_calculation(self):
        metric = _make_operation(
            bytes_transferred=1048576,  # 1 MiB
            duration_s=2.0,
        )
        assert metric.throughput_mbps is not None
        assert metric.throughput_mbps == pytest.approx(0.5, rel=1e-6)

    def test_throughput_none_when_no_bytes(self):
        metric = _make_operation(bytes_transferred=None, duration_s=1.0)
        assert metric.throughput_mbps is None
