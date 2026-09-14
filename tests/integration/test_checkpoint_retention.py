"""Checkpoint retention — bounded growth without breaking recovery.

LangGraph persists one row per super-step into ``checkpoints`` (plus
``checkpoint_writes`` / ``checkpoint_blobs``) and nothing in this codebase ever
deletes them, so a long-lived thread grows without bound.

These tests pin the properties that make the cleanup safe:

- the head of the chain is never deleted;
- exactly ``keep_generations`` rows survive per (thread_id, checkpoint_ns);
- an idle thread under the window is left completely alone;
- namespaces are trimmed independently;
- blobs under a still-live namespace are never touched;
- a failure inside the pass is swallowed and reported, not raised at the caller.

Integration tests: they run against the real database (the DDL for these tables
comes from the checkpointer migrations, not from application code), and the
shared ``test_db_pool`` fixture supplies an isolated schema per session.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_chain(pool, thread_id: str, count: int, ns: str = "") -> None:
    """Insert a linear parent-linked chain of ``count`` checkpoints."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO checkpoints
                (thread_id, checkpoint_ns, checkpoint_id,
                 parent_checkpoint_id, type, checkpoint, metadata)
            SELECT %(t)s, %(ns)s,
                   lpad((2000000000000 + g)::text, 32, '0'),
                   CASE WHEN g = 1 THEN NULL
                        ELSE lpad((2000000000000 + g - 1)::text, 32, '0') END,
                   'json', '{}'::jsonb, '{}'::jsonb
            FROM generate_series(1, %(n)s) g
            """,
            {"t": thread_id, "ns": ns, "n": count},
        )


async def _insert_blob(pool, thread_id: str, ns: str = "") -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO checkpoint_blobs
                (thread_id, checkpoint_ns, channel, version, type, blob)
            VALUES (%(t)s, %(ns)s, 'ch1',
                    '00000000000000000000000000000001', 'json', 'x'::bytea)
            """,
            {"t": thread_id, "ns": ns},
        )


async def _count(pool, thread_id: str, ns: str | None = None) -> int:
    async with pool.connection() as conn:
        if ns is None:
            cur = await conn.execute(
                "SELECT count(*) AS n FROM checkpoints WHERE thread_id = %s",
                (thread_id,),
            )
        else:
            cur = await conn.execute(
                "SELECT count(*) AS n FROM checkpoints "
                "WHERE thread_id = %s AND checkpoint_ns = %s",
                (thread_id, ns),
            )
        return (await cur.fetchone())["n"]


async def _blob_count(pool, thread_id: str) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT count(*) AS n FROM checkpoint_blobs WHERE thread_id = %s",
            (thread_id,),
        )
        return (await cur.fetchone())["n"]


async def _head(pool, thread_id: str) -> str | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT max(checkpoint_id) AS head FROM checkpoints WHERE thread_id = %s",
            (thread_id,),
        )
        return (await cur.fetchone())["head"]


@pytest_asyncio.fixture(autouse=True)
async def _clean_checkpoint_tables(test_db_pool):
    """The shared truncate list does not cover LangGraph's tables."""
    async with test_db_pool.connection() as conn:
        await conn.execute("TRUNCATE checkpoints, checkpoint_writes, checkpoint_blobs")
    yield
    async with test_db_pool.connection() as conn:
        await conn.execute("TRUNCATE checkpoints, checkpoint_writes, checkpoint_blobs")


# ---------------------------------------------------------------------------


async def test_trims_to_the_retention_window(test_db_pool):
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _seed_chain(test_db_pool, "t1", 300)
    head_before = await _head(test_db_pool, "t1")

    stats = await cleanup_checkpoints(test_db_pool, keep_generations=50)

    assert stats.checkpoints_deleted == 250
    assert await _count(test_db_pool, "t1") == 50
    # The recovery head must survive — everything else is negotiable.
    assert await _head(test_db_pool, "t1") == head_before


async def test_thread_under_the_window_is_untouched(test_db_pool):
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _seed_chain(test_db_pool, "short", 10)
    stats = await cleanup_checkpoints(test_db_pool, keep_generations=50)

    assert stats.checkpoints_deleted == 0
    assert await _count(test_db_pool, "short") == 10


async def test_namespaces_are_trimmed_independently(test_db_pool):
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _seed_chain(test_db_pool, "shared", 100, ns="alpha")
    await _seed_chain(test_db_pool, "shared", 5, ns="beta")

    await cleanup_checkpoints(test_db_pool, keep_generations=20)

    assert await _count(test_db_pool, "shared", ns="alpha") == 20
    # beta was under the window and must not be collateral damage.
    assert await _count(test_db_pool, "shared", ns="beta") == 5


async def test_multiple_threads_are_each_trimmed(test_db_pool):
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _seed_chain(test_db_pool, "a", 100)
    await _seed_chain(test_db_pool, "b", 100)

    stats = await cleanup_checkpoints(test_db_pool, keep_generations=25)

    assert await _count(test_db_pool, "a") == 25
    assert await _count(test_db_pool, "b") == 25
    assert stats.threads_scanned == 2


async def test_idempotent_second_pass(test_db_pool):
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _seed_chain(test_db_pool, "t1", 100)

    first = await cleanup_checkpoints(test_db_pool, keep_generations=30)
    second = await cleanup_checkpoints(test_db_pool, keep_generations=30)

    assert first.checkpoints_deleted == 70
    assert second.checkpoints_deleted == 0
    assert await _count(test_db_pool, "t1") == 30


async def test_orphaned_namespace_blobs_are_removed(test_db_pool):
    """Blobs under a namespace with no checkpoints left can never be resumed."""
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _insert_blob(test_db_pool, "orphan")

    stats = await cleanup_checkpoints(test_db_pool, keep_generations=10)

    assert stats.blobs_deleted == 1
    assert await _blob_count(test_db_pool, "orphan") == 0


async def test_live_thread_blobs_survive(test_db_pool):
    """A thread that still has checkpoints keeps its blobs."""
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    await _seed_chain(test_db_pool, "live", 10)
    await _insert_blob(test_db_pool, "live")

    await cleanup_checkpoints(test_db_pool, keep_generations=10)

    assert await _blob_count(test_db_pool, "live") == 1


async def test_rejects_nonsense_retention():
    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    with pytest.raises(ValueError):
        await cleanup_checkpoints(None, keep_generations=0)


async def test_failure_is_reported_not_raised():
    """A cleanup pass must never take the caller down."""

    class _Boom:
        def connection(self):
            raise RuntimeError("pool is closed")

    from src.server.utils.checkpoint_retention import cleanup_checkpoints

    stats = await cleanup_checkpoints(_Boom(), keep_generations=10)
    assert stats.checkpoints_deleted == 0
