from __future__ import annotations

import pytest

from .collector import MetricsCollector


def pytest_addoption(parser):
    group = parser.getgroup("sandbox-metrics", "Sandbox operation metrics")
    group.addoption(
        "--sandbox-metrics",
        action="store_true",
        default=False,
        help="Enable sandbox operation metrics collection and reporting.",
    )
    group.addoption(
        "--sandbox-metrics-file",
        default="sandbox_metrics.json",
        help="Output file for sandbox metrics JSON (default: sandbox_metrics.json).",
    )


def pytest_configure(config):
    collector = MetricsCollector()
    if config.getoption("--sandbox-metrics", default=False):
        collector.enable()
    config._sandbox_metrics_collector = collector


@pytest.fixture(scope="session")
def metrics_collector(request) -> MetricsCollector:
    collector = getattr(request.config, "_sandbox_metrics_collector", None)
    if collector is None:
        collector = MetricsCollector()
    return collector


def pytest_sessionfinish(session, exitstatus):
    collector = getattr(session.config, "_sandbox_metrics_collector", None)
    if collector is None or not collector.enabled or not collector.operations:
        return
    output_file = session.config.getoption("--sandbox-metrics-file", default="sandbox_metrics.json")
    try:
        from .reporter import write_json_report, print_terminal_summary

        write_json_report(collector, output_file)
        print_terminal_summary(collector)
    except ImportError:
        pass
