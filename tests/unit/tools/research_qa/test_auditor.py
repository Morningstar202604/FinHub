"""Unit tests for the research auditor (ROADMAP M2-D)."""

from __future__ import annotations

import pytest

from src.tools.research_qa.auditor import audit_report, extract_numbers


class TestExtractNumbers:
    def test_usd_million_normalization(self) -> None:
        nums = extract_numbers("Apple revenue was $12.4B, costs $430M, EPS $1.2")
        usd = [n for n in nums if n.kind == "usd"]
        assert len(usd) == 3
        by_raw = {n.raw: n.value_usd_m for n in usd}
        assert by_raw["$12.4B"] == pytest.approx(12_400.0, rel=1e-3)
        assert by_raw["$430M"] == pytest.approx(430.0)
        assert by_raw["$1.2"] == pytest.approx(1.2e-6)

    def test_percent_and_multipliers_captured(self) -> None:
        nums = extract_numbers("margin 45%, growth 2.3x, 业绩增长8.5%")
        kinds = {n.kind for n in nums}
        assert {"pct", "mult"} <= kinds


class TestAuditNumberVerification:
    def test_delta_beyond_tolerance_is_error(self) -> None:
        report = audit_report(
            "营收为 $12.4B",
            known_data={"营收": 18_000.0},  # $18B baseline vs $12.4B stated
        )
        errors = report.errors()
        assert any(f.kind == "noverify" for f in errors)

    def test_delta_within_tolerance_passes(self) -> None:
        report = audit_report(
            "营收为 $18.2B",
            known_data={"营收": 18_000.0},
            num_tolerance_pct=2.0,
        )
        assert report.passed

    def test_missing_metric_is_warning(self) -> None:
        report = audit_report(
            "本季度表现良好",
            known_data={"毛利率": 45.0},
        )
        assert any(f.level == "warning" and f.kind == "noverify" for f in report.findings)


class TestAuditCitations:
    def test_uncited_claim_flagged(self) -> None:
        report = audit_report(
            "我们认为毛利率将达到 45%，因为订单强劲增长",
            provenance_sources=("sec-10k",),
        )
        assert any(f.kind == "uncited" for f in report.findings)

    def test_cited_claim_passes(self) -> None:
        report = audit_report(
            "毛利率45% per sec-10k，订单增长强劲",
            provenance_sources=("sec-10k",),
        )
        assert not any(f.kind == "uncited" for f in report.findings)


class TestAuditConflicts:
    def test_conflicting_metrics_detected(self) -> None:
        report = audit_report("毛利率为 45%，但后文写 毛利率 55%")
        assert any(f.kind == "conflict" and f.level == "error" for f in report.findings)

    def test_consistent_text_no_conflict(self) -> None:
        report = audit_report("毛利率为 45%，目标价提高至买入，营收 12.4B")
        assert not any(f.kind == "conflict" for f in report.findings)


def test_passed_means_no_errors_only() -> None:
    report = audit_report(
        "营收为 $18.2B，毛利率 45%",
        known_data={"营收": 18_000.0},
    )
    assert report.passed