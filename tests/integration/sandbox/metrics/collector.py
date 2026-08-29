from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OperationMetric:
    provider: str  # "memory", "docker", "daytona"
    category: str  # "lifecycle", "exec", "code_run", "file_io", "full_lifecycle"
    operation: str  # "create", "exec.echo", "upload_file", etc.
    test_name: str  # pytest node name
    duration_s: float
    success: bool
    error: str | None = None
    bytes_transferred: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def throughput_mbps(self) -> float | None:
        if self.bytes_transferred and self.duration_s > 0:
            return (self.bytes_transferred / 1024 / 1024) / self.duration_s
        return None


@dataclass
class RetryMetric:
    provider: str
    operation: str
    test_name: str
    total_attempts: int
    transient_errors: int
    final_success: bool
    total_duration_s: float


class MetricsCollector:
    def __init__(self):
        self.operations: list[OperationMetric] = []
        self.retries: list[RetryMetric] = []
        self._enabled = False

    def enable(self):
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_operation(self, metric: OperationMetric):
        if self._enabled:
            self.operations.append(metric)

    def record_retry(self, metric: RetryMetric):
        if self._enabled:
            self.retries.append(metric)

    def timed(self, provider: str, category: str, operation: str, test_name: str):
        return _TimedContext(self, provider, category, operation, test_name)


class _TimedContext:
    """Async context manager that auto-records an OperationMetric on exit."""

    def __init__(self, collector, provider, category, operation, test_name):
        self._collector = collector
        self._provider = provider
        self._category = category
        self._operation = operation
        self._test_name = test_name
        self._start: float = 0
        self.metadata: dict[str, Any] = {}
        self.bytes_transferred: int | None = None

    async def __aenter__(self):
        self._start = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self._start
        self._collector.record_operation(
            OperationMetric(
                provider=self._provider,
                category=self._category,
                operation=self._operation,
                test_name=self._test_name,
                duration_s=duration,
                success=exc_type is None,
                error=str(exc_val) if exc_val else None,
                metadata=self.metadata,
                bytes_transferred=self.bytes_transferred,
            )
        )
        return False  # Don't suppress exceptions
