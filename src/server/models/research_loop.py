"""
Request and response models for the Research Loop API.

The research loop is FinHub's core product mainline — a six-stage pipeline
(idea -> data -> model -> report -> track -> trigger) with a managed evidence
index, artifact index, and portfolio linkage per workspace.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ResearchLoopStage(str, Enum):
    """The six stages of the research loop, in pipeline order."""
    IDEA = "idea"
    DATA = "data"
    MODEL = "model"
    REPORT = "report"
    TRACK = "track"
    TRIGGER = "trigger"


class ResearchLoopStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ResearchLoopDirection(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class ResearchLoopCreate(BaseModel):
    goal: str = Field(default="", max_length=1000, description="研究目标")
    thesis: str = Field(default="", max_length=8000, description="核心论点（应可证伪）")
    symbol: Optional[str] = Field(default=None, max_length=32, description="标的代码")
    direction: Optional[ResearchLoopDirection] = None
    portfolio_link: Optional[Dict[str, Any]] = Field(
        default=None,
        description="组合关联：{in_portfolio, in_watchlist, notes}",
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None)


class ResearchLoopUpdate(BaseModel):
    goal: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[ResearchLoopStatus] = None
    current_stage: Optional[ResearchLoopStage] = None
    thesis: Optional[str] = Field(default=None, max_length=8000)
    symbol: Optional[str] = Field(default=None, max_length=32)
    direction: Optional[ResearchLoopDirection] = None
    portfolio_link: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class ResearchLoopStageEntry(BaseModel):
    stage: str
    status: str
    at: str
    note: str = ""


class ResearchLoopEvidenceCreate(BaseModel):
    source: str = Field(..., max_length=500, description="数据来源/工具")
    pulled_at: Optional[str] = Field(default=None, description="拉取时间 ISO")
    caliber: Optional[str] = Field(default=None, max_length=200, description="口径（TTM/季度/单位）")
    level: Literal["verified", "estimated", "user_provided", "unverified"] = "verified"
    note: Optional[str] = Field(default=None, max_length=1000)
    metadata: Optional[Dict[str, Any]] = None


class ResearchLoopArtifactCreate(BaseModel):
    path: str = Field(..., max_length=1000, description="产物路径（results/...）")
    artifact_type: str = Field(..., max_length=64, description="md/html/docx/xlsx/pdf/...")
    title: Optional[str] = Field(default=None, max_length=500)
    metadata: Optional[Dict[str, Any]] = None


class ResearchLoopAdvance(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class ResearchLoopResponse(BaseModel):
    loop_id: str
    workspace_id: str
    user_id: str
    goal: str
    status: str
    current_stage: str
    thesis: str
    symbol: Optional[str] = None
    direction: Optional[str] = None
    stage_history: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    portfolio_link: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ResearchLoopListResponse(BaseModel):
    loops: List[ResearchLoopResponse]
    total: int


class ResearchLoopDeleteResponse(BaseModel):
    deleted: bool
    loop_id: str
