"""Research QA utilities — self-verification auditor (ROADMAP M2-D) + structured output (M2-F)."""

from .artifacts import (
    SCHEMA_VERSION,
    ArtifactType,
    ArtifactVersion,
    EvidenceItem,
    artifact_from_dict,
    artifact_to_dict,
    build_artifact,
)
from .auditor import AuditFinding, AuditReport, ExtractedNumber, audit_report, extract_numbers
from .tool import audit_research_numbers

__all__ = [
    "SCHEMA_VERSION",
    "ArtifactType",
    "ArtifactVersion",
    "EvidenceItem",
    "AuditFinding",
    "AuditReport",
    "ExtractedNumber",
    "artifact_from_dict",
    "artifact_to_dict",
    "audit_report",
    "audit_research_numbers",
    "build_artifact",
    "extract_numbers",
]