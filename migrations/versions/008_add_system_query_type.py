"""Add 'system' and 'steering' to conversation_queries type CHECK constraint.

Revision ID: 008
"""

from alembic import op


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE conversation_queries
            DROP CONSTRAINT IF EXISTS conversation_queries_type_check
    """)
    op.execute("""
        ALTER TABLE conversation_queries
            ADD CONSTRAINT conversation_queries_type_check
            CHECK (type IN (
                'initial', 'follow_up', 'resume_feedback', 'regenerate',
                'steering', 'system'
            ))
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE conversation_queries SET type = 'initial'
        WHERE type IN ('steering', 'system')
    """)
    op.execute("""
        ALTER TABLE conversation_queries
            DROP CONSTRAINT IF EXISTS conversation_queries_type_check
    """)
    op.execute("""
        ALTER TABLE conversation_queries
            ADD CONSTRAINT conversation_queries_type_check
            CHECK (type IN (
                'initial', 'follow_up', 'resume_feedback', 'regenerate'
            ))
    """)
