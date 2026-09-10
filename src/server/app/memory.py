"""Read-only API for the agent's long-term memory (LangGraph store)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.server.app import setup
from src.server.app._store_helpers import (
    MAX_LIST_LIMIT,
    aget,
    asearch,
    coerce_str,
    paginate_namespace,
    require_store,
    validate_key,
)
from src.server.database.workspace import get_workspace as db_get_workspace
from src.server.utils.api import CurrentUserId, require_workspace_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])


class MemoryEntry(BaseModel):
    key: str
    size: int
    created_at: str | None = None
    modified_at: str | None = None


class MemoryListResponse(BaseModel):
    tier: str  # "user" | "workspace"
    entries: list[MemoryEntry]
    truncated: bool = False


class MemoryReadResponse(BaseModel):
    tier: str
    key: str
    content: str
    encoding: str
    created_at: str | None = None
    modified_at: str | None = None


def _value_to_entry(key: str, value: Any) -> MemoryEntry:
    if not isinstance(value, dict):
        return MemoryEntry(key=key, size=0)
    content = value.get("content")
    size = len(content) if isinstance(content, str) else 0
    return MemoryEntry(
        key=key,
        size=size,
        created_at=coerce_str(value.get("created_at")) or None,
        modified_at=coerce_str(value.get("modified_at")) or None,
    )


def _value_to_read(tier: str, key: str, value: Any) -> MemoryReadResponse:
    if not isinstance(value, dict):
        # Store corruption — return empty instead of 500.
        logger.warning("memory entry has non-dict value", extra={"key": key})
        return MemoryReadResponse(tier=tier, key=key, content="", encoding="utf-8")
    return MemoryReadResponse(
        tier=tier,
        key=key,
        content=coerce_str(value.get("content")),
        encoding=coerce_str(value.get("encoding"), "utf-8") or "utf-8",
        created_at=coerce_str(value.get("created_at")) or None,
        modified_at=coerce_str(value.get("modified_at")) or None,
    )


# --- User tier ---------------------------------------------------------------


@router.get("/user", response_model=MemoryListResponse)
async def list_user_memory(user_id: CurrentUserId) -> MemoryListResponse:
    """List all user-tier memory entries for the caller."""
    store = require_store(setup.store)
    namespace = (user_id, "memory")
    entries, truncated = await paginate_namespace(store, namespace, _value_to_entry)
    return MemoryListResponse(tier="user", entries=entries, truncated=truncated)


@router.get("/user/read", response_model=MemoryReadResponse)
async def read_user_memory(
    user_id: CurrentUserId,
    key: str = Query(..., description="Key relative to the user memory root"),
) -> MemoryReadResponse:
    """Read one user-tier memory file by its key."""
    validate_key(key)
    store = require_store(setup.store)
    item = await aget(store, (user_id, "memory"), key)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return _value_to_read("user", key, item.value)


# --- Workspace tier ----------------------------------------------------------


@router.get("/workspaces/{workspace_id}", response_model=MemoryListResponse)
async def list_workspace_memory(
    workspace_id: str,
    user_id: CurrentUserId,
) -> MemoryListResponse:
    """List all workspace-tier memory entries for the caller's workspace."""
    workspace = await db_get_workspace(workspace_id)
    require_workspace_owner(workspace, user_id=user_id)
    store = require_store(setup.store)
    namespace = (user_id, "workspaces", workspace_id, "memory")
    entries, truncated = await paginate_namespace(store, namespace, _value_to_entry)
    return MemoryListResponse(
        tier="workspace", entries=entries, truncated=truncated
    )


@router.get("/workspaces/{workspace_id}/read", response_model=MemoryReadResponse)
async def read_workspace_memory(
    workspace_id: str,
    user_id: CurrentUserId,
    key: str = Query(..., description="Key relative to the workspace memory root"),
) -> MemoryReadResponse:
    """Read one workspace-tier memory file by its key."""
    validate_key(key)
    workspace = await db_get_workspace(workspace_id)
    require_workspace_owner(workspace, user_id=user_id)
    store = require_store(setup.store)
    namespace = (user_id, "workspaces", workspace_id, "memory")
    item = await aget(store, namespace, key)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return _value_to_read("workspace", key, item.value)


# --- Recall (M2-E BM25 over the caller's memory corpus, M4-3 browser) --------


class RecallHitModel(BaseModel):
    text: str
    source: str = ""
    score: float = 0.0
    chars: int = 0


class MemoryRecallResponse(BaseModel):
    tier: str
    query: str
    hits: list[RecallHitModel] = []


async def _all_memory_docs(
    store: Any,
    namespace: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Pull every entry's text from a namespace (truncated at the list cap)."""
    rows: list[tuple[str, str]] = []
    offset = 0
    page = 100
    while len(rows) < MAX_LIST_LIMIT:
        results = await asearch(store, namespace, limit=page, offset=offset)
        if not results:
            break
        for item in results:
            value = item.value if isinstance(item.value, dict) else {}
            content = value.get("content")
            if isinstance(content, str) and content:
                rows.append((item.key, content))
        offset += page
    return rows[:MAX_LIST_LIMIT]


def _recall_hits(query: str, docs: list[tuple[str, str]], top_k: int) -> list[RecallHitModel]:
    """BM25 recall (reused M2-E impl, no embedding provider)."""
    from src.tools.memory.retrieval import build_chunks, recall

    hits = recall(query, build_chunks(docs), top_k=top_k)
    return [
        RecallHitModel(text=h.text, source=h.source, score=round(h.score, 4), chars=h.chars)
        for h in hits
    ]


@router.get("/recall", response_model=MemoryRecallResponse)
async def recall_memory(
    user_id: CurrentUserId,
    q: str = Query(..., min_length=1, description="Search query"),
    workspace_id: Optional[str] = Query(None, description="Restrict to a workspace tier"),
    top_k: int = Query(5, ge=1, le=20, description="Max recall hits"),
) -> MemoryRecallResponse:
    """BM25 keyword recall over the caller's long-term memory.

    User-tier (agent.md / memory / memo) when ``workspace_id`` is omitted;
    workspace-tier only when given (owner-guarded). Deterministic and keyless —
    the same ``recall_memory`` tool the PTC agent uses, exposed read-only so
    the frontend memory browser can preview what a query would surface.
    """
    store = require_store(setup.store)
    if workspace_id:
        workspace = await db_get_workspace(workspace_id)
        require_workspace_owner(workspace, user_id=user_id)
        namespace = (user_id, "workspaces", workspace_id, "memory")
        tier = "workspace"
    else:
        namespace = (user_id, "memory")
        tier = "user"
    docs = await _all_memory_docs(store, namespace)
    return MemoryRecallResponse(
        tier=tier,
        query=q,
        hits=_recall_hits(q, docs, top_k=top_k),
    )
