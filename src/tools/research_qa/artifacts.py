"""Structured output schemas (ROADMAP M2-F) — the rendering contract.

Deterministic, Pydantic-based shapes that every research deliverable maps
into before it hits the UI or an export. Frontend components render
``artifact_type``-specific fields; versioning via ``schema_version`` keeps
older artifacts readable when new fields are added (missing fields default).

Using pydantic (already a core dependency) — no bespoke validation lib.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION: int = 1


class ArtifactType(str, Enum):
    """The artifact vocabulary the UI knows how to render."""

    THESIS = "thesis"                  # idea-generation / research-loop kickoff
    EVIDENCE = "evidence"              # evidence snapshot / data pull
    MODEL = "model"                    # DCF / comps / three-statement
    REPORT = "report"                  # coverage / earnings / morning note
    WIDGET = "widget"                  # inline HTML widget (ShowWidget)
    CHART = "chart"                    # chart annotation / market chart
    TRACKER = "tracker"                # thesis scorecard / catalyst calendar
    OTHER = "other"


class EvidenceItem(BaseModel):
    source: str = Field(..., description="SOCIUM: provider/source id (SEC filing, tradingview, fmp…)")
    url: Optional[str] = None
    pulled_at: Optional[datetime] = None
    caliber: Optional[str] = Field(default=None, description="TTM / FY / 单季度")
    value: Optional[float] = None
    note: str = ""


class ArtifactVersion(BaseModel):
    version: int = SCHEMA_VERSION
    artifact_type: ArtifactType = ArtifactType.OTHER
    title: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    body_markdown: str = ""                      # canonical rendering source
    key_numbers: List[Dict[str, Any]] = Field(default_factory=list)  # UI metric cards
    evidence: List[EvidenceItem] = Field(default_factory=list)      # citation trail
    metadata: Dict[str, Any] = Field(default_factory=dict)          # workspace/symbol/direction
    payload: Optional[Dict[str, Any]] = Field(default=None)         # type-specific extras


def build_artifact(
    artifact_type: ArtifactType,
    *,
    title: str = "",
    body_markdown: str = "",
    key_numbers: Optional[List[Dict[str, Any]]] = None,
    evidence: Optional[List[EvidenceItem]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> ArtifactVersion:
    """Construct a versioned artifact with sane defaults (drop-in for callers)."""
    return ArtifactVersion(
        artifact_type=artifact_type,
        title=title,
        body_markdown=body_markdown,
        key_numbers=key_numbers or [],
        evidence=evidence or [],
        metadata=metadata or {},
        payload=payload,
    )


def artifact_to_dict(artifact: ArtifactVersion) -> Dict[str, Any]:
    """JSON-safe dict for storage/SSE (Pydantic model_dump under the hood)."""
    return artifact.model_dump(mode="json", exclude_none=False)


def artifact_from_dict(data: Dict[str, Any]) -> ArtifactVersion:
    """Rebuild an artifact from a stored dict, defaulting missing fields."""
    return ArtifactVersion.model_validate(data)


__all__ = [
    "SCHEMA_VERSION",
    "ArtifactType",
    "ArtifactVersion",
    "EvidenceItem",
    "artifact_to_dict",
    "artifact_from_dict",
    "build_artifact",
]