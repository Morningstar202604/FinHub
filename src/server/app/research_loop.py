"""Research Loop API Router — managed research-loop state per workspace.

The research loop is FinHub's core product mainline (see
plugins/finhub_research/skills/research-loop). This router gives the
six-stage pipeline a managed, queryable surface: create/update the loop,
advance stages, append evidence and artifact entries, and list a user's
loops across workspaces for the dashboard.

Endpoints:
- GET    /api/v1/workspaces/{workspace_id}/research-loop
- POST   /api/v1/workspaces/{workspace_id}/research-loop
- PATCH  /api/v1/workspaces/{workspace_id}/research-loop
- DELETE /api/v1/workspaces/{workspace_id}/research-loop
- POST   /api/v1/workspaces/{workspace_id}/research-loop/advance
- POST   /api/v1/workspaces/{workspace_id}/research-loop/evidence
- POST   /api/v1/workspaces/{workspace_id}/research-loop/artifacts
- GET    /api/v1/research-loops
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from src.server.database.research_loop import (
    add_research_loop_artifact,
    add_research_loop_evidence,
    advance_research_loop_stage,
    create_research_loop,
    delete_research_loop,
    get_research_loop_by_workspace,
    list_research_loops,
    update_research_loop,
)
from src.server.database.workspace import get_workspace as db_get_workspace
from src.server.models.research_loop import (
    ResearchLoopAdvance,
    ResearchLoopArtifactCreate,
    ResearchLoopCreate,
    ResearchLoopDeleteResponse,
    ResearchLoopEvidenceCreate,
    ResearchLoopListResponse,
    ResearchLoopResponse,
    ResearchLoopUpdate,
)
from src.server.utils.api import (
    CurrentUserId,
    handle_api_exceptions,
    require_workspace_owner,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces", tags=["Research Loop"])
user_router = APIRouter(prefix="/api/v1/research-loops", tags=["Research Loop"])


async def _ensure_owner(workspace_id: str, user_id: str) -> None:
    """Look up the workspace and verify the caller owns it (404 / 403)."""
    workspace = await db_get_workspace(workspace_id)
    require_workspace_owner(workspace, user_id=user_id)


def _to_response(row: dict) -> ResearchLoopResponse:
    return ResearchLoopResponse.model_validate(row)


# ---------------------------------------------------------------------------
# Workspace-scoped: single loop per workspace
# ---------------------------------------------------------------------------


@router.get(
    "/{workspace_id}/research-loop",
    response_model=ResearchLoopResponse,
)
@handle_api_exceptions("get research loop", logger)
async def get_research_loop(
    workspace_id: str,
    x_user_id: CurrentUserId,
):
    """Get the workspace's research loop (404 if none has been started)."""
    await _ensure_owner(workspace_id, x_user_id)
    row = await get_research_loop_by_workspace(workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No research loop for this workspace yet")
    return _to_response(row)


@router.post(
    "/{workspace_id}/research-loop",
    response_model=ResearchLoopResponse,
    status_code=201,
)
@handle_api_exceptions("create research loop", logger)
async def create_research_loop_endpoint(
    workspace_id: str,
    request: ResearchLoopCreate,
    x_user_id: CurrentUserId,
):
    """Start a research loop for the workspace (one per workspace)."""
    await _ensure_owner(workspace_id, x_user_id)
    existing = await get_research_loop_by_workspace(workspace_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="Workspace already has a research loop",
        )
    row = await create_research_loop(
        workspace_id=workspace_id,
        user_id=x_user_id,
        goal=request.goal,
        thesis=request.thesis,
        symbol=request.symbol,
        direction=request.direction.value if request.direction else None,
        portfolio_link=request.portfolio_link,
        metadata=request.metadata,
    )
    return _to_response(row)


@router.patch(
    "/{workspace_id}/research-loop",
    response_model=ResearchLoopResponse,
)
@handle_api_exceptions("update research loop", logger)
async def update_research_loop_endpoint(
    workspace_id: str,
    request: ResearchLoopUpdate,
    x_user_id: CurrentUserId,
):
    """Update loop fields; a ``current_stage`` change appends to stage history."""
    await _ensure_owner(workspace_id, x_user_id)
    existing = await get_research_loop_by_workspace(workspace_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No research loop for this workspace yet")
    row = await update_research_loop(
        existing["loop_id"],
        goal=request.goal,
        status=request.status.value if request.status else None,
        current_stage=request.current_stage.value if request.current_stage else None,
        thesis=request.thesis,
        symbol=request.symbol,
        direction=request.direction.value if request.direction else None,
        portfolio_link=request.portfolio_link,
        metadata=request.metadata,
    )
    return _to_response(row)


@router.delete(
    "/{workspace_id}/research-loop",
    response_model=ResearchLoopDeleteResponse,
)
@handle_api_exceptions("delete research loop", logger)
async def delete_research_loop_endpoint(
    workspace_id: str,
    x_user_id: CurrentUserId,
):
    """Delete the workspace's research loop."""
    await _ensure_owner(workspace_id, x_user_id)
    existing = await get_research_loop_by_workspace(workspace_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No research loop for this workspace yet")
    deleted = await delete_research_loop(existing["loop_id"])
    return ResearchLoopDeleteResponse(deleted=deleted, loop_id=existing["loop_id"])


@router.post(
    "/{workspace_id}/research-loop/advance",
    response_model=ResearchLoopResponse,
)
@handle_api_exceptions("advance research loop stage", logger)
async def advance_research_loop_stage_endpoint(
    workspace_id: str,
    request: ResearchLoopAdvance,
    x_user_id: CurrentUserId,
):
    """Advance the loop to the next stage in pipeline order."""
    await _ensure_owner(workspace_id, x_user_id)
    existing = await get_research_loop_by_workspace(workspace_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No research loop for this workspace yet")
    row = await advance_research_loop_stage(existing["loop_id"], note=request.note)
    return _to_response(row)


@router.post(
    "/{workspace_id}/research-loop/evidence",
    response_model=ResearchLoopResponse,
)
@handle_api_exceptions("add research loop evidence", logger)
async def add_research_loop_evidence_endpoint(
    workspace_id: str,
    request: ResearchLoopEvidenceCreate,
    x_user_id: CurrentUserId,
):
    """Append a verified/estimated evidence entry to the loop's evidence index."""
    await _ensure_owner(workspace_id, x_user_id)
    existing = await get_research_loop_by_workspace(workspace_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No research loop for this workspace yet")
    row = await add_research_loop_evidence(
        existing["loop_id"],
        source=request.source,
        pulled_at=request.pulled_at,
        caliber=request.caliber,
        level=request.level,
        note=request.note,
        metadata=request.metadata,
    )
    return _to_response(row)


@router.post(
    "/{workspace_id}/research-loop/artifacts",
    response_model=ResearchLoopResponse,
)
@handle_api_exceptions("add research loop artifact", logger)
async def add_research_loop_artifact_endpoint(
    workspace_id: str,
    request: ResearchLoopArtifactCreate,
    x_user_id: CurrentUserId,
):
    """Append a deliverable (report/model) to the loop's artifact index."""
    await _ensure_owner(workspace_id, x_user_id)
    existing = await get_research_loop_by_workspace(workspace_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="No research loop for this workspace yet")
    row = await add_research_loop_artifact(
        existing["loop_id"],
        path=request.path,
        artifact_type=request.artifact_type,
        title=request.title,
        metadata=request.metadata,
    )
    return _to_response(row)


# ---------------------------------------------------------------------------
# User-scoped: list loops across workspaces (dashboard)
# ---------------------------------------------------------------------------


@user_router.get("", response_model=ResearchLoopListResponse)
@handle_api_exceptions("list research loops", logger)
async def list_research_loops_endpoint(
    x_user_id: CurrentUserId,
    status: str | None = Query(None, description="Filter by loop status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List the caller's research loops across workspaces (dashboard)."""
    rows = await list_research_loops(
        x_user_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return ResearchLoopListResponse(
        loops=[_to_response(r) for r in rows],
        total=len(rows),
    )
