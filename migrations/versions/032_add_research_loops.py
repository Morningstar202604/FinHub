"""Research Loop ledger — one managed loop per workspace.

The research-loop skill (plugins/finhub_research/skills/research-loop) is the
product mainline; this table makes it *systematically managed* instead of
prose in agent.md. A row is the durable home for a loop's state: which of the
six stages (idea -> data -> model -> report -> track -> trigger) it is on, its
evidence index, artifact index, and portfolio linkage.

One active loop per workspace — the skill model is "每个工作区对应一个研究目标"
(one workspace per research goal), so a second loop is an error until the
first is completed/archived. JSONB columns keep evidence/artifacts/stage
history append-only so the frontend can render a full pipeline without joins.

Revision ID: 032
Revises: 031
"""

from alembic import op


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS research_loops (
            loop_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID NOT NULL
                REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
            user_id UUID NOT NULL,
            goal TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'completed', 'archived')),
            current_stage TEXT NOT NULL DEFAULT 'idea'
                CHECK (current_stage IN
                    ('idea', 'data', 'model', 'report', 'track', 'trigger')),
            thesis TEXT NOT NULL DEFAULT '',
            symbol TEXT,
            direction TEXT
                CHECK (direction IS NULL OR direction IN ('long', 'short', 'neutral')),
            stage_history JSONB NOT NULL DEFAULT '[]',
            evidence JSONB NOT NULL DEFAULT '[]',
            artifacts JSONB NOT NULL DEFAULT '[]',
            portfolio_link JSONB,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS research_loops_workspace_key
            ON research_loops (workspace_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS research_loops_user_idx
            ON research_loops (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS research_loops_status_idx
            ON research_loops (status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS research_loops")
