"""Unit tests for structured research artifacts (ROADMAP M2-F)."""

from __future__ import annotations

from src.tools.research_qa.artifacts import (
    SCHEMA_VERSION,
    ArtifactType,
    EvidenceItem,
    artifact_from_dict,
    artifact_to_dict,
    build_artifact,
)


def test_build_artifact_defaults_roundtrip() -> None:
    artifact = build_artifact(
        ArtifactType.REPORT,
        title="AAPL 覆盖报告",
        body_markdown="# 正文",
    )
    assert artifact.version == SCHEMA_VERSION
    assert artifact.artifact_type == ArtifactType.REPORT
    assert artifact.key_numbers == []
    assert artifact.evidence == []
    assert artifact.metadata == {}

    d = artifact_to_dict(artifact)
    assert d["artifact_type"] == "report"
    assert d["title"] == "AAPL 覆盖报告"

    restored = artifact_from_dict(d)
    assert restored == artifact


def test_artifact_with_evidence_and_key_numbers() -> None:
    artifact = build_artifact(
        ArtifactType.REPORT,
        title="NVDA 财务",
        key_numbers=[{"label": "营收(FY25)", "value": 130.5, "unit": "B", "delta": 0.0}],
        evidence=[
            EvidenceItem(
                source="sec-10k",
                url="https://www.sec.gov/archives/edgar/data/1045810/000104581025000008/nvda-20250126.htm",
                caliber="FY2025",
                value=130.5,
                note="audited",
            )
        ],
    )
    assert artifact.evidence[0].source == "sec-10k"
    # JSON round-trip keeps decimals/fields intact.
    restored = artifact_from_dict(artifact_to_dict(artifact))
    assert restored.key_numbers[0]["value"] == 130.5


def test_from_dict_defaults_missing_version() -> None:
    restored = artifact_from_dict({"title": "no-version", "artifact_type": "thesis"})
    assert restored.version == SCHEMA_VERSION
    assert restored.artifact_type == ArtifactType.THESIS