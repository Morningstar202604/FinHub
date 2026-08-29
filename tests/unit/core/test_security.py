"""Tests for ptc_agent.core.security module.

Covers ExecutionMonitor, RateLimiter, ResourceMonitor, and SecurityLogger.
"""

import time

from ptc_agent.core.security import (
    ExecutionMonitor,
    RateLimiter,
    ResourceMonitor,
    SecurityLogger,
)


class TestExecutionMonitor:
    """Tests for ExecutionMonitor tracking and statistics."""

    def test_start_execution_tracks_active(self):
        monitor = ExecutionMonitor()
        monitor.start_execution("exec-1", "print('hi')", "sandbox-1")
        assert "exec-1" in monitor.active_executions
        info = monitor.active_executions["exec-1"]
        assert info["execution_id"] == "exec-1"
        assert info["sandbox_id"] == "sandbox-1"
        assert info["code_length"] == len("print('hi')")

    def test_end_execution_moves_to_history(self):
        monitor = ExecutionMonitor()
        monitor.start_execution("exec-1", "x = 1", "sandbox-1")
        monitor.end_execution("exec-1", success=True, output="done")
        assert "exec-1" not in monitor.active_executions
        assert len(monitor.execution_history) == 1
        entry = monitor.execution_history[0]
        assert entry["success"] is True
        assert entry["output_length"] == 4
        assert entry["duration"] >= 0

    def test_end_execution_unknown_id_is_noop(self):
        monitor = ExecutionMonitor()
        # Should not raise, just log a warning
        monitor.end_execution("nonexistent", success=False, error="oops")
        assert len(monitor.execution_history) == 0

    def test_get_execution_stats_empty(self):
        monitor = ExecutionMonitor()
        stats = monitor.get_execution_stats()
        assert stats["total_executions"] == 0
        assert stats["success_rate"] == 0
        assert stats["average_duration"] == 0
        assert stats["active_executions"] == 0

    def test_get_execution_stats_with_data(self):
        monitor = ExecutionMonitor()
        # Run two executions: one success, one failure
        monitor.start_execution("e1", "ok", "sb")
        monitor.end_execution("e1", success=True)
        monitor.start_execution("e2", "err", "sb")
        monitor.end_execution("e2", success=False, error="fail")

        stats = monitor.get_execution_stats()
        assert stats["total_executions"] == 2
        assert stats["successful_executions"] == 1
        assert stats["failed_executions"] == 1
        assert stats["success_rate"] == 0.5

    def test_get_recent_executions_respects_limit(self):
        monitor = ExecutionMonitor()
        for i in range(5):
            monitor.start_execution(f"e{i}", "code", "sb")
            monitor.end_execution(f"e{i}", success=True)

        recent = monitor.get_recent_executions(limit=3)
        assert len(recent) == 3
        # Should be the last 3
        assert recent[0]["execution_id"] == "e2"
        assert recent[2]["execution_id"] == "e4"

    def test_code_hash_is_sha256(self):
        import hashlib

        monitor = ExecutionMonitor()
        code = "print('hello world')"
        monitor.start_execution("e1", code, "sb")
        expected_hash = hashlib.sha256(code.encode()).hexdigest()
        assert monitor.active_executions["e1"]["code_hash"] == expected_hash

    def test_end_execution_records_error(self):
        monitor = ExecutionMonitor()
        monitor.start_execution("e1", "bad code", "sb")
        monitor.end_execution("e1", success=False, error="SyntaxError")
        entry = monitor.execution_history[0]
        assert entry["error"] == "SyntaxError"
        assert entry["success"] is False


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_allows_within_limit(self):
        limiter = RateLimiter(max_executions=5, window_seconds=60)
        allowed, msg = limiter.check_rate_limit()
        assert allowed is True
        assert msg is None

    def test_blocks_when_limit_exceeded(self):
        limiter = RateLimiter(max_executions=2, window_seconds=3600)
        limiter.record_execution()
        limiter.record_execution()
        allowed, msg = limiter.check_rate_limit()
        assert allowed is False
        assert "Rate limit exceeded" in msg

    def test_record_execution_increases_count(self):
        limiter = RateLimiter(max_executions=10, window_seconds=60)
        assert len(limiter.execution_timestamps) == 0
        limiter.record_execution()
        assert len(limiter.execution_timestamps) == 1
        limiter.record_execution()
        assert len(limiter.execution_timestamps) == 2

    def test_old_timestamps_are_pruned(self):
        limiter = RateLimiter(max_executions=2, window_seconds=1)
        # Add timestamps in the past
        limiter.execution_timestamps = [time.time() - 10, time.time() - 10]
        allowed, msg = limiter.check_rate_limit()
        assert allowed is True
        # Old entries should have been cleaned up
        assert len(limiter.execution_timestamps) == 0


class TestResourceMonitor:
    """Tests for ResourceMonitor."""

    def test_track_sandbox_initializes_stats(self):
        monitor = ResourceMonitor()
        monitor.track_sandbox("sb-1")
        assert "sb-1" in monitor.sandbox_resources
        stats = monitor.sandbox_resources["sb-1"]
        assert stats["execution_count"] == 0
        assert stats["total_code_length"] == 0
        assert stats["files_created"] == 0

    def test_record_execution_increments_counters(self):
        monitor = ResourceMonitor()
        monitor.track_sandbox("sb-1")
        monitor.record_execution("sb-1", code_length=100)
        monitor.record_execution("sb-1", code_length=50)
        stats = monitor.sandbox_resources["sb-1"]
        assert stats["execution_count"] == 2
        assert stats["total_code_length"] == 150

    def test_record_execution_auto_tracks_sandbox(self):
        monitor = ResourceMonitor()
        monitor.record_execution("sb-new", code_length=42)
        assert "sb-new" in monitor.sandbox_resources
        assert monitor.sandbox_resources["sb-new"]["execution_count"] == 1

    def test_record_file_operation_create(self):
        monitor = ResourceMonitor()
        monitor.track_sandbox("sb-1")
        monitor.record_file_operation("sb-1", "create")
        monitor.record_file_operation("sb-1", "create")
        assert monitor.sandbox_resources["sb-1"]["files_created"] == 2

    def test_record_file_operation_non_create(self):
        monitor = ResourceMonitor()
        monitor.track_sandbox("sb-1")
        monitor.record_file_operation("sb-1", "read")
        monitor.record_file_operation("sb-1", "delete")
        assert monitor.sandbox_resources["sb-1"]["files_created"] == 0

    def test_get_sandbox_stats_returns_copy_with_age(self):
        monitor = ResourceMonitor()
        monitor.track_sandbox("sb-1")
        stats = monitor.get_sandbox_stats("sb-1")
        assert stats is not None
        assert "age_seconds" in stats
        assert stats["age_seconds"] >= 0

    def test_get_sandbox_stats_unknown_returns_none(self):
        monitor = ResourceMonitor()
        assert monitor.get_sandbox_stats("nonexistent") is None

    def test_cleanup_sandbox_removes_tracking(self):
        monitor = ResourceMonitor()
        monitor.track_sandbox("sb-1")
        monitor.cleanup_sandbox("sb-1")
        assert "sb-1" not in monitor.sandbox_resources

    def test_cleanup_sandbox_noop_for_unknown(self):
        monitor = ResourceMonitor()
        # Should not raise
        monitor.cleanup_sandbox("nonexistent")


class TestSecurityLogger:
    """Tests for SecurityLogger."""

    def test_log_validation_failure(self):
        logger = SecurityLogger()
        logger.log_validation_failure("abc123", "blocked import", "os.system")
        events = logger.get_security_events()
        assert len(events) == 1
        event = events[0]
        assert event["type"] == "validation_failure"
        assert event["code_hash"] == "abc123"
        assert event["reason"] == "blocked import"
        assert event["blocked_pattern"] == "os.system"

    def test_log_execution_timeout(self):
        logger = SecurityLogger()
        logger.log_execution_timeout("exec-1", duration=120.5)
        events = logger.get_security_events()
        assert len(events) == 1
        assert events[0]["type"] == "execution_timeout"
        assert events[0]["execution_id"] == "exec-1"
        assert events[0]["duration"] == 120.5

    def test_log_suspicious_activity(self):
        logger = SecurityLogger()
        logger.log_suspicious_activity(
            "rapid_execution",
            {"count": 50, "window_seconds": 10},
        )
        events = logger.get_security_events()
        assert len(events) == 1
        assert events[0]["type"] == "suspicious_activity"
        assert events[0]["activity_type"] == "rapid_execution"
        assert events[0]["details"]["count"] == 50

    def test_get_security_events_respects_limit(self):
        logger = SecurityLogger()
        for i in range(20):
            logger.log_validation_failure(f"hash{i}", f"reason{i}")
        events = logger.get_security_events(limit=5)
        assert len(events) == 5
        # Should be the last 5
        assert events[0]["code_hash"] == "hash15"

    def test_get_security_events_default_limit(self):
        logger = SecurityLogger()
        for i in range(5):
            logger.log_validation_failure(f"hash{i}", f"reason{i}")
        events = logger.get_security_events()
        assert len(events) == 5
