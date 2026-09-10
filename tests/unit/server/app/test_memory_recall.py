"""M4-3: memory recall endpoint (BM25 over the caller's memory corpus).

The endpoint reuses the deterministic M2-E `recall_memory` implementation, so
the unit tests protect the HTTP contract: tier selection (workspace vs user),
owner guarding, and graceful degradation on an empty corpus. BM25 itself is
already covered by tests/unit/tools/memory/.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.server.app import memory as memory_app


class _MemItem:
    def __init__(self, key: str, content: str):
        self.key = key
        self.value = {"content": content}


def _fake_store(entries: list[_MemItem]) -> AsyncMock:
    store = AsyncMock()

    async def fake_asearch(namespace, limit, offset):
        return entries[offset : offset + limit]

    store.asearch = fake_asearch
    return store


@pytest.mark.asyncio
async def test_recall_user_tier_returns_hits():
    store = _fake_store(
        [
            _MemItem("memory.md", "苹果 2024 营收 3910 亿美元，净利润 937 亿。"),
            _MemItem("agent.md", "我们是投研助手，专注 DCF 与财务建模。"),
        ]
    )
    with (
        patch.object(memory_app.setup, "store", store),
        patch(
            "src.server.app.memory.require_store",
            return_value=store,
        ),
    ):
        resp = await memory_app.recall_memory("u1", "营收", workspace_id=None, top_k=3)

    assert resp.tier == "user"
    assert resp.query == "营收"
    assert len(resp.hits) >= 1
    assert "营收" in resp.hits[0].text
    assert resp.hits[0].source  # source tag populated


@pytest.mark.asyncio
async def test_recall_workspace_tier_without_owner_blocks():
    store = _fake_store([])

    def deny(*args, **kwargs):
        raise PermissionError("denied")

    with (
        patch.object(memory_app.setup, "store", store),
        patch(
            "src.server.app.memory.require_store",
            return_value=store,
        ),
        patch("src.server.app.memory.db_get_workspace", return_value={"workspace_id": "w"}),
        patch("src.server.app.memory.require_workspace_owner", side_effect=deny),
    ):
        with pytest.raises(PermissionError):
            await memory_app.recall_memory("u1", "q", workspace_id="w", top_k=3)


@pytest.mark.asyncio
async def test_recall_empty_corpus_degrades_gracefully():
    store = _fake_store([])
    with (
        patch.object(memory_app.setup, "store", store),
        patch(
            "src.server.app.memory.require_store",
            return_value=store,
        ),
    ):
        resp = await memory_app.recall_memory("u1", "任何词", workspace_id=None, top_k=3)

    assert resp.hits == []
    assert resp.tier == "user"


@pytest.mark.asyncio
async def test_recall_skips_non_dict_entries():
    store = AsyncMock()
    calls = {"n": 0}

    async def fake_asearch(namespace, limit, offset):
        if calls["n"] > 0:
            return []
        calls["n"] += 1
        return [type("I", (), {"key": "junk", "value": "not-a-dict"})()]

    store.asearch = fake_asearch
    with (
        patch.object(memory_app.setup, "store", store),
        patch(
            "src.server.app.memory.require_store",
            return_value=store,
        ),
    ):
        resp = await memory_app.recall_memory("u1", "q", workspace_id=None, top_k=3)

    assert resp.hits == []