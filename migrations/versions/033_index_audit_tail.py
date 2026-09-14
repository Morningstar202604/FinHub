"""Index-audit tail (M3-B): composite indexes for two hot paginated reads.

Runs on 033 (Revises: 032).

1. ``research_loops (user_id, status, updated_at DESC)`` — the research-loop
   dashboard ``list_research_loops`` filters by user (+ optional status) and
   orders by ``updated_at DESC``; the existing single-column ``user_id`` and
   ``status`` indexes each leave a Sort, and the ``user_id`` filter alone
   scatter-reads across all of a user's rows.

2. ``automation_executions (automation_id, created_at DESC)`` — the execution
   history page filters by ``automation_id`` and orders by ``created_at DESC``
   with LIMIT/OFFSET paging; ``idx_automation_executions_automation_id``
   covers the filter but not the sort, so every page pays a Sort of all of
   that automation's executions.

Both index builds are intentionally NOT ``CONCURRENTLY``, for the reason
recorded in 017: at current table sizes the write-blocking window of a plain
CREATE INDEX is negligible, while CONCURRENTLY cannot run inside alembic's
transaction and would need an ``autocommit_block`` per statement (plus a
manual cleanup path for INVALID indexes left by a failed build). Revisit if a
deployment ever carries genuinely large history for either table.

Both statements are ``IF NOT EXISTS``-idempotent, so re-runs are no-ops.

Revision ID: 033
Revises: 032
"""

from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Plain multi-column btree: the composite key itself is the optimisation
    # here, so no CONCURRENTLY trade-off is needed at current scale.
    op.execute("""
        CREATE INDEX IF NOT EXISTS research_loops_user_status_updated_idx
        ON research_loops (user_id, status, updated_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS automation_executions_automation_created_idx
        ON automation_executions (automation_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS automation_executions_automation_created_idx")
    op.execute("DROP INDEX IF EXISTS research_loops_user_status_updated_idx")