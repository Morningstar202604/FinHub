"""Add personalization_completed column to users table.

Tracks whether a user has completed the BYOK setup wizard
(personalization flow). Separate from onboarding_completed which
tracks the investment-preferences onboarding.

Revision ID: 006
Revises: 005
Create Date: 2026-03-28
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS personalization_completed BOOLEAN DEFAULT FALSE
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS personalization_completed")
