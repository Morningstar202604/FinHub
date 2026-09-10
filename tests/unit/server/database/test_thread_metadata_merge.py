"""M4-1: thread-metadata intent stamping.

``update_thread_metadata_merge`` performs an idempotent JSONB merge into the
``conversation_threads.metadata`` column so the auto-routing decision produced
by the intent classifier (M2-B) can be persisted and rendered by the
frontend's route-reason panel. Unit tests protect the SQL shape (merge, not
overwrite) and the no-clobber / no-op contracts — the same guards the merge
is designed to give the thread row.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.database.conversation import update_thread_metadata_merge


def _fake_db(fetchone_value=None):
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=fetchone_value)
    conn = MagicMock()

    @asynccontextmanager
    async def _cursor_cm(**kwargs):
        yield cursor

    conn.cursor = _cursor_cm

    @asynccontextmanager
    async def _get_db_connection():
        yield conn

    return _get_db_connection, cursor


def _row(**overrides):
    base = {
        "conversation_thread_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "current_status": "in_progress",
        "msg_type": "ptc",
        "thread_index": 1,
        "title": "hello",
        "platform": None,
        "metadata": {"intent": {"mode": "ptc", "reason": "strong ptc signal keyword", "confidence": 0.9}},
        "is_shared": False,
        "is_pinned": False,
        "archived_at": None,
        "last_seen_run_seq": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_merge_stamps_intent_patch():
    """The UPDATE uses ``metadata || patch`` — a merge, not an overwrite.

    The SQL literal must keep the COALESCE-to-'{{}}' guard so a NULL metadata
    column still accepts the first intent stamp.
    """
    tid = str(uuid.uuid4())
    fake_db, cursor = _fake_db(fetchone_value=_row())

    with patch("src.server.database.pool.get_db_connection", new=fake_db):
        got = await update_thread_metadata_merge(
            tid, {"intent": {"mode": "flash", "reason": "default quick path", "confidence": 0.55}}
        )

    assert got is not None
    sql = cursor.execute.await_args.args[0]
    # Merge semantics, never assignment.
    assert "metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb" in sql
    # Target row only — never blanket update.
    assert "WHERE conversation_thread_id = %s" in sql
    # Idempotent: no second statement, no subquery, one UPDATE only.
    assert sql.count("UPDATE conversation_threads") == 1


@pytest.mark.asyncio
async def test_merge_uses_normalized_uuid():
    tid = str(uuid.uuid4()).upper()
    fake_db, cursor = _fake_db(fetchone_value=_row())

    with patch("src.server.database.pool.get_db_connection", new=fake_db):
        await update_thread_metadata_merge(tid, {"intent": {"mode": "ptc", "reason": "r", "confidence": 0.5}})

    bound = cursor.execute.await_args.args[1]
    assert bound[1] == tid.lower()  # normalized uuid bound as the WHERE param


@pytest.mark.asyncio
async def test_merge_noop_when_thread_missing():
    """A missing row returns None — the caller treats it as an acceptable
    degradation (legacy POST /messages creates the row later)."""
    tid = str(uuid.uuid4())
    fake_db, cursor = _fake_db(fetchone_value=None)

    with patch("src.server.database.pool.get_db_connection", new=fake_db):
        got = await update_thread_metadata_merge(tid, {"intent": {"mode": "flash", "reason": "r", "confidence": 0.5}})

    assert got is None
    assert cursor.execute.await_args is not None


@pytest.mark.asyncio
async def test_merge_keeps_unrelated_top_level_keys_in_patch():
    """A patch may carry several top-level keys; all of them merge together —
    the frontend reason panel reads ``metadata.intent`` while ``origin`` and
    other writers' keys stay intact (that survival is the DB join, asserted
    here at the SQL-shape level)."""
    tid = str(uuid.uuid4())
    fake_db, cursor = _fake_db(fetchone_value=_row())

    with patch("src.server.database.pool.get_db_connection", new=fake_db):
        await update_thread_metadata_merge(
            tid,
            {
                "intent": {"mode": "flash", "reason": "hello", "confidence": 0.9},
                "pinged_at": "2026-01-01",
            },
        )

    bound = cursor.execute.await_args.args[1]
    patch_json = bound[0]
    # psycopg Json wrapper carries the dict in .obj.
    if not isinstance(patch_json, dict):
        patch_json = patch_json.obj
    assert set(patch_json.keys()) == {"intent", "pinged_at"}