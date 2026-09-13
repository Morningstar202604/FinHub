"""
Database utility functions for research-loop management.

One managed loop per workspace: the six-stage research pipeline
(idea -> data -> model -> report -> track -> trigger) is persisted as a
Postgres row with an append-only JSONB evidence index, artifact index, and
stage history — so the frontend can render the full loop without joins and
the agent can query/advance its own loop programmatically.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.server.database.pool import get_db_connection

logger = logging.getLogger(__name__)

# Ordered research-loop stages (see plugins/finhub_research/skills/research-loop).
RESEARCH_LOOP_STAGES: tuple[str, ...] = (
    "idea",
    "data",
    "model",
    "report",
    "track",
    "trigger",
)

RESEARCH_LOOP_COLUMNS = """
    loop_id, workspace_id, user_id, goal, status, current_stage, thesis,
    symbol, direction, stage_history, evidence, artifacts, portfolio_link,
    metadata, created_at, updated_at
"""


def _next_stage(current: str) -> Optional[str]:
    """Return the stage after ``current``, or None at the last stage."""
    try:
        idx = RESEARCH_LOOP_STAGES.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(RESEARCH_LOOP_STAGES):
        return None
    return RESEARCH_LOOP_STAGES[idx + 1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Create / Read
# =============================================================================


async def create_research_loop(
    workspace_id: str,
    user_id: str,
    *,
    goal: str = "",
    thesis: str = "",
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    portfolio_link: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a research loop for a workspace (one per workspace).

    The loop starts at stage ``idea`` with an empty stage history containing
    the creation entry.
    """
    loop_id = str(uuid4())
    stage_history = [{"stage": "idea", "status": "active", "at": _now(), "note": "loop created"}]

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                INSERT INTO research_loops (
                    loop_id, workspace_id, user_id, goal, status, current_stage,
                    thesis, symbol, direction, stage_history, evidence, artifacts,
                    portfolio_link, metadata, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, 'active', 'idea',
                    %s, %s, %s, %s, '[]', '[]',
                    %s, %s, NOW(), NOW()
                )
                RETURNING {RESEARCH_LOOP_COLUMNS}
                """,
                (
                    loop_id, workspace_id, user_id, goal, thesis,
                    symbol, direction, Json(stage_history),
                    Json(portfolio_link) if portfolio_link is not None else None,
                    Json(metadata or {}),
                ),
            )
            row = await cur.fetchone()
    logger.info("Created research loop %s for workspace %s", loop_id, workspace_id)
    return row


async def get_research_loop(loop_id: str) -> Optional[Dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT {RESEARCH_LOOP_COLUMNS} FROM research_loops WHERE loop_id = %s",
                (loop_id,),
            )
            return await cur.fetchone()


async def get_research_loop_by_workspace(workspace_id: str) -> Optional[Dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT {RESEARCH_LOOP_COLUMNS} FROM research_loops WHERE workspace_id = %s",
                (workspace_id,),
            )
            return await cur.fetchone()


async def list_research_loops(
    user_id: str,
    *,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List the user's research loops across workspaces (for the dashboard)."""
    clauses = ["user_id = %s"]
    params: list[Any] = [user_id]
    if status:
        clauses.append("status = %s")
        params.append(status)
    where = " AND ".join(clauses)
    params.extend([limit, offset])

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT {RESEARCH_LOOP_COLUMNS} FROM research_loops
                WHERE {where}
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
                """,
                params,
            )
            return await cur.fetchall()


# =============================================================================
# Update
# =============================================================================


async def update_research_loop(
    loop_id: str,
    *,
    goal: Optional[str] = None,
    status: Optional[str] = None,
    current_stage: Optional[str] = None,
    thesis: Optional[str] = None,
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    portfolio_link: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Update mutable fields of a loop.

    When ``current_stage`` changes, a history entry is appended so the
    pipeline timeline is preserved. Empty updates are a no-op returning the
    current row.
    """
    sets: list[str] = []
    params: list[Any] = []

    if goal is not None:
        sets.append("goal = %s"); params.append(goal)
    if status is not None:
        sets.append("status = %s"); params.append(status)
    if thesis is not None:
        sets.append("thesis = %s"); params.append(thesis)
    if symbol is not None:
        sets.append("symbol = %s"); params.append(symbol)
    if direction is not None:
        sets.append("direction = %s"); params.append(direction)
    if portfolio_link is not None:
        sets.append("portfolio_link = %s"); params.append(Json(portfolio_link))
    if metadata is not None:
        sets.append("metadata = %s"); params.append(Json(metadata))
    if current_stage is not None:
        sets.append("current_stage = %s"); params.append(current_stage)
        entry = [{"stage": current_stage, "status": "active", "at": _now(), "note": "stage advanced"}]
        sets.append("stage_history = COALESCE(stage_history, '[]'::jsonb) || %s::jsonb")
        params.append(Json(entry))

    if not sets:
        return await get_research_loop(loop_id)

    sets.append("updated_at = NOW()")
    params.append(loop_id)
    sql = (
        f"UPDATE research_loops SET {', '.join(sets)} WHERE loop_id = %s "
        f"RETURNING {RESEARCH_LOOP_COLUMNS}"
    )

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
    return row


async def advance_research_loop_stage(
    loop_id: str,
    *,
    note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Advance the loop to the next stage, appending to stage history."""
    loop = await get_research_loop(loop_id)
    if loop is None:
        return None
    nxt = _next_stage(loop["current_stage"])
    if nxt is None:
        # Already at the last stage — return current state unchanged.
        return loop
    entry = Json([{"stage": nxt, "status": "active", "at": _now(), "note": note or "stage advanced"}])

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                UPDATE research_loops
                SET current_stage = %s,
                    stage_history = COALESCE(stage_history, '[]'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE loop_id = %s
                RETURNING {RESEARCH_LOOP_COLUMNS}
                """,
                (nxt, entry, loop_id),
            )
            row = await cur.fetchone()
    logger.info("Advanced research loop %s to stage %s", loop_id, nxt)
    return row


# =============================================================================
# Evidence / artifact append
# =============================================================================


async def add_research_loop_evidence(
    loop_id: str,
    *,
    source: str,
    pulled_at: Optional[str] = None,
    caliber: Optional[str] = None,
    level: str = "verified",
    note: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Append an evidence entry to the loop's evidence index."""
    entry = {
        "id": str(uuid4()),
        "source": source,
        "pulled_at": pulled_at or _now(),
        "caliber": caliber or "",
        "level": level,
        "note": note or "",
        "metadata": metadata or {},
        "at": _now(),
    }

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                UPDATE research_loops
                SET evidence = COALESCE(evidence, '[]'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE loop_id = %s
                RETURNING {RESEARCH_LOOP_COLUMNS}
                """,
                (Json([entry]), loop_id),
            )
            row = await cur.fetchone()
    return row


async def add_research_loop_artifact(
    loop_id: str,
    *,
    path: str,
    artifact_type: str,
    title: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Append an artifact (deliverable) entry to the loop's artifact index."""
    entry = {
        "id": str(uuid4()),
        "path": path,
        "type": artifact_type,
        "title": title or "",
        "metadata": metadata or {},
        "at": _now(),
    }

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                UPDATE research_loops
                SET artifacts = COALESCE(artifacts, '[]'::jsonb) || %s::jsonb,
                    updated_at = NOW()
                WHERE loop_id = %s
                RETURNING {RESEARCH_LOOP_COLUMNS}
                """,
                (Json([entry]), loop_id),
            )
            row = await cur.fetchone()
    return row


# =============================================================================
# Delete
# =============================================================================


async def delete_research_loop(loop_id: str) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM research_loops WHERE loop_id = %s", (loop_id,))
            return cur.rowcount > 0
