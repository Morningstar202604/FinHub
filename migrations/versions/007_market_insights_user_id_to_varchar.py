"""Change market_insights.user_id from UUID to VARCHAR(255).

Every other table uses VARCHAR(255) for user_id (matching the users PK).
UUID breaks self-hosted / local-dev where the auth layer returns a plain
string like "local-dev-user".

Revision ID: 007
Revises: 006
Create Date: 2026-03-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cast existing UUID values to text, then change column type
    op.execute("""
        ALTER TABLE market_insights
        ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::text
    """)


def downgrade() -> None:
    # Only safe if all values are valid UUIDs
    op.execute("""
        ALTER TABLE market_insights
        ALTER COLUMN user_id TYPE UUID USING user_id::uuid
    """)
