"""Personal-finance snapshots (个人财务快照).

Revision ID: 035
Revises: 034

Why JSONB items and not an items table
======================================

The ledger (034) gave journal-entry lines their own table because a line is an
auditable *fact* with independent identity — filterable by account, joinable to
a period, individually wrong. A personal-finance snapshot item is not that: it
is a stated value that belongs wholly to its snapshot and is only meaningful
in aggregate. No query of the form "every 房产 row across all users" needs to
be answered here.

The ledger's balance invariant — the actual reason lines needed a table, so a
cross-row check could be pushed into the database — has no analogue: a balance
sheet is not required to balance, so there is no constraint to enforce across
rows. That leaves no technical justification for the extra table, only
speculative query flexibility we do not have a use for.

Money inside ``items`` is stored as integer minor units under an
``amount_minor`` key, never as a decimal string or float, so a JSON round-trip
cannot reintroduce the float drift the finance package exists to prevent.

Idempotent: IF NOT EXISTS throughout.
"""

from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS personal_finance_snapshots (
            snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            kind TEXT NOT NULL
                CHECK (kind IN ('balance_sheet', 'cash_flow')),
            -- Both bounds are stored even for a point-in-time balance sheet
            -- (where they are equal). Giving both kinds the same period shape
            -- means "net worth over time" is one index scan over one table
            -- instead of a UNION of two schemas.
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CNY',
            note TEXT NOT NULL DEFAULT '',
            -- Array of item objects. See module docstring for why this is not
            -- normalised into its own table.
            items JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # The read pattern is always "this user's snapshots, newest period first",
    # optionally filtered by kind.
    op.execute("""
        CREATE INDEX IF NOT EXISTS personal_finance_snapshots_user_period_idx
        ON personal_finance_snapshots (user_id, kind, period_end DESC, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS personal_finance_snapshots_user_period_idx")
    op.execute("DROP TABLE IF EXISTS personal_finance_snapshots")
