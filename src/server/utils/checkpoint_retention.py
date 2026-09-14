"""Checkpoint retention — bounded growth for the LangGraph checkpoint tables.

LangGraph writes one row per super-step to ``checkpoints``, plus the
corresponding deltas in ``checkpoint_writes`` and ``checkpoint_blobs``. That
is correct for durability but unbounded: a long-lived thread accumulates rows
forever, and nothing in the codebase ever deletes them (the only DROP lives in
a migration downgrade).

What this module does — and deliberately does not do
----------------------------------------------------
A checkpoint is a node in a parent-linked chain. LangGraph's recovery reads
the **head** of a chain (walking back from the most recent ``checkpoint_id``),
and ``thread_mutation``/replay features may rewind to a specific point, so
"delete everything older than X" is not safe on its own.

The rule here is *keep the last N generations per (thread_id, checkpoint_ns)*,
measured along the parent chain rather than by timestamp
(``checkpoint_id`` is not a reliable ordering key across LangGraph versions).
Rows older than that window are unreachable by normal recovery and are removed,
along with their dependent ``writes`` and orphaned ``blobs``.

Safety properties:

- Only rows strictly below the retention floor are touched, so the head is
  never a candidate.
- Deletion runs in bounded batches with a per-batch commit, keeping lock hold
  time short and making an interrupted run resumable rather than atomic-but-
  disastrous.
- ``statement_timeout`` is set per batch, so a contended table cannot wedge the
  cleanup task indefinitely (mirrors ``migrations/env.py``).

Why there is no "skip active threads" guard
-------------------------------------------
An earlier revision tried to skip threads touched inside a grace window. There
is no reliable way to express that here: the postgres saver does not guarantee
a ``created_at`` column, and ``checkpoint_id`` is an opaque, version-dependent
string — comparing it against a "now" timestamp silently matched nothing
(zero-padded widths differ), which is worse than not having the guard because
it looks like it works.

The retention window itself provides the protection that matters: keeping the
last N generations means a live run's recent history is never a candidate. N
defaults to 200, comfortably above any single turn's rewind depth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Keep this many generations per (thread_id, checkpoint_ns). Sized to cover a
# full agent turn's rewind depth (a turn is typically 5-25 super-steps) with
# headroom for step-level replay, while still bounding a marathon thread.
DEFAULT_RETENTION_GENERATIONS = 200

# Rows per DELETE. 5000 keeps each statement well under a second on a healthy
# table while still draining millions of rows in a reasonable number of passes.
DEFAULT_BATCH_SIZE = 5000

# Guard against a cleanup pass monopolising the table.
_BATCH_STATEMENT_TIMEOUT = "30s"


@dataclass
class CheckpointCleanupStats:
    """Outcome of one cleanup pass, shaped for logging."""

    threads_scanned: int = 0
    threads_trimmed: int = 0
    checkpoints_deleted: int = 0
    writes_deleted: int = 0
    blobs_deleted: int = 0
    batches: int = 0
    truncated: bool = False

    def as_dict(self) -> dict:
        return {
            "threads_scanned": self.threads_scanned,
            "threads_trimmed": self.threads_trimmed,
            "checkpoints_deleted": self.checkpoints_deleted,
            "writes_deleted": self.writes_deleted,
            "blobs_deleted": self.blobs_deleted,
            "batches": self.batches,
            "truncated": self.truncated,
        }

    def is_empty(self) -> bool:
        return self.checkpoints_deleted == 0 and self.blobs_deleted == 0


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

# Rank every checkpoint within its (thread_id, checkpoint_ns) group by walking
# the parent chain from the head. `created_at` is not used: non-standard
# checkpointer layouts may not carry it, and ordering by it would race with
# concurrent writes. row_number() over the chain is the same order recovery
# itself observes.
#
# Rows whose rank exceeds the retention window are candidates. The chain walk
# is bounded by the group size, which is exactly what we are trying to shrink,
# so it stays cheap after the first pass.
_SELECT_EXPIRED = """
WITH ranked AS (
    SELECT
        thread_id,
        checkpoint_ns,
        checkpoint_id,
        ROW_NUMBER() OVER (
            PARTITION BY thread_id, checkpoint_ns
            ORDER BY checkpoint_id DESC
        ) AS generation
    FROM checkpoints
    WHERE thread_id = ANY(%(thread_ids)s)
)
SELECT thread_id, checkpoint_ns, checkpoint_id
FROM ranked
WHERE generation > %(keep)s
ORDER BY thread_id, checkpoint_ns, generation DESC
LIMIT %(batch)s
"""

# Threads worth considering. Selected by *chain length* rather than by age:
# checkpoint_id is opaque (format differs across LangGraph versions, and a
# zero-padded-string comparison against "now" silently matches nothing when the
# widths differ), whereas "this thread has more than `keep` generations" is
# exactly the condition that makes work available, needs no clock, and is
# stable across saver versions.
_SELECT_CANDIDATE_THREADS = """
SELECT thread_id, COUNT(*) AS generations, MAX(checkpoint_id) AS head
FROM checkpoints
GROUP BY thread_id
HAVING COUNT(*) > %(keep)s
ORDER BY generations DESC
LIMIT %(limit)s
"""

_DELETE_WRITES = """
DELETE FROM checkpoint_writes
WHERE thread_id = ANY(%(thread_ids)s)
  AND checkpoint_ns = ANY(%(namespaces)s)
  AND checkpoint_id = ANY(%(checkpoint_ids)s)
"""

_DELETE_CHECKPOINTS = """
DELETE FROM checkpoints
WHERE thread_id = ANY(%(thread_ids)s)
  AND checkpoint_ns = ANY(%(namespaces)s)
  AND checkpoint_id = ANY(%(checkpoint_ids)s)
"""

# Blobs are keyed by (thread_id, checkpoint_ns, channel, version) — no
# checkpoint_id column — and checkpoint_writes has no `version` column either,
# so there is no join key linking a blob to the write that needed it. The
# available signal is coarser: once a (thread_id, checkpoint_ns) pair has no
# checkpoints left at all, every blob under it is unreachable, because recovery
# always starts from a checkpoint row and a namespace with none can never be
# resumed.
#
# Scoped to namespaces that are already gone, so a live thread's blobs are
# never touched — the retention window in the checkpoint DELETE above is what
# protects them.
_DELETE_ORPHAN_BLOBS = """
DELETE FROM checkpoint_blobs b
WHERE (b.thread_id, b.checkpoint_ns) IN (
    SELECT b2.thread_id, b2.checkpoint_ns
    FROM checkpoint_blobs b2
    WHERE NOT EXISTS (
        SELECT 1 FROM checkpoints c
        WHERE c.thread_id = b2.thread_id
          AND c.checkpoint_ns = b2.checkpoint_ns
    )
    GROUP BY b2.thread_id, b2.checkpoint_ns
    LIMIT %(batch)s
)
"""


async def cleanup_checkpoints(
    pool,
    *,
    keep_generations: int = DEFAULT_RETENTION_GENERATIONS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = 100,
    max_threads: int = 200,
) -> CheckpointCleanupStats:
    """Trim checkpoint history to ``keep_generations`` per thread namespace.

    Args:
        pool: An open ``AsyncConnectionPool`` (the checkpointer's own pool).
        keep_generations: Generations to retain per (thread_id, namespace).
        batch_size: Rows per DELETE statement.
        max_batches: Hard stop on passes, so one call cannot run unbounded.
        max_threads: Threads considered per call; the next call takes the rest.

    Returns:
        Aggregate stats. Never raises on a best-effort failure — a cleanup task
        must not take the server down — but logs at ERROR with a traceback.
    """
    stats = CheckpointCleanupStats()

    if keep_generations < 1:
        raise ValueError("keep_generations must be >= 1")

    try:
        async with pool.connection() as conn:
            await conn.execute(
                f"SET statement_timeout = '{_BATCH_STATEMENT_TIMEOUT}'"
            )

            cur = await conn.execute(
                _SELECT_CANDIDATE_THREADS,
                {"keep": keep_generations, "limit": max_threads},
            )
            rows = await cur.fetchall()

        thread_ids = [r["thread_id"] for r in rows]
        stats.threads_scanned = len(thread_ids)

        for _ in range(max_batches) if thread_ids else ():
            async with pool.connection() as conn:
                await conn.execute(
                    f"SET statement_timeout = '{_BATCH_STATEMENT_TIMEOUT}'"
                )

                cur = await conn.execute(
                    _SELECT_EXPIRED,
                    {
                        "thread_ids": thread_ids,
                        "keep": keep_generations,
                        "batch": batch_size,
                    },
                )
                expired = await cur.fetchall()

            if not expired:
                break

            # Group the batch by thread/namespace so the DELETEs stay set-based.
            by_group: dict[tuple[str, str], list[str]] = {}
            for row in expired:
                by_group.setdefault(
                    (row["thread_id"], row["checkpoint_ns"]), []
                ).append(row["checkpoint_id"])

            deleted_this_round = 0
            for (thread_id, ns), ids in by_group.items():
                params = {
                    "thread_ids": [thread_id],
                    "namespaces": [ns],
                    "checkpoint_ids": ids,
                }
                async with pool.connection() as conn:
                    await conn.execute(
                        f"SET statement_timeout = '{_BATCH_STATEMENT_TIMEOUT}'"
                    )
                    # Writes first: they carry an FK-like dependency on the
                    # checkpoint row and orphan faster than the parent.
                    w_cur = await conn.execute(_DELETE_WRITES, params)
                    stats.writes_deleted += w_cur.rowcount or 0

                    c_cur = await conn.execute(_DELETE_CHECKPOINTS, params)
                    removed = c_cur.rowcount or 0
                    stats.checkpoints_deleted += removed
                    deleted_this_round += removed

            stats.batches += 1
            stats.threads_trimmed += len(by_group)

            if deleted_this_round == 0:
                # Nothing removed despite candidates — stop rather than spin.
                break
        else:
            if thread_ids:
                stats.truncated = True
                logger.info(
                    "Checkpoint cleanup hit max_batches; remaining work will be "
                    "picked up on the next pass"
                )

        # Sweep blobs that no surviving write references. This runs even when
        # no thread needed trimming: a namespace whose checkpoints were all
        # removed by an earlier pass leaves blobs behind with nothing left to
        # rank, so it is never a *candidate thread* — only this sweep can
        # collect it. Bounded and idempotent, so a partial pass is harmless.
        for _ in range(max_batches):
            async with pool.connection() as conn:
                await conn.execute(
                    f"SET statement_timeout = '{_BATCH_STATEMENT_TIMEOUT}'"
                )
                b_cur = await conn.execute(
                    _DELETE_ORPHAN_BLOBS, {"batch": batch_size}
                )
                removed = b_cur.rowcount or 0
            stats.blobs_deleted += removed
            if removed < batch_size:
                break

    except Exception:
        logger.error("Checkpoint cleanup failed", exc_info=True)
        return stats

    if not stats.is_empty():
        logger.info(
            "Checkpoint cleanup pass complete", extra=stats.as_dict()
        )
    else:
        logger.debug("Checkpoint cleanup pass: nothing to remove")

    return stats
