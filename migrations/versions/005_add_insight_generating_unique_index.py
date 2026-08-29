"""Add partial unique index to prevent duplicate generating insights per user.

Revision ID: 005
Revises: 004
"""

from alembic import op

revision = "005"
down_revision = "004"


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_insights_user_generating
        ON market_insights (user_id)
        WHERE status = 'generating'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_market_insights_user_generating")
