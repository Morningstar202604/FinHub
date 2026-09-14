"""Ledger persistence (M-Fin): accounts + journal entries + entry lines.

Revision ID: 034
Revises: 033

Why three tables and not one
============================

A journal entry is a *header* (date, memo, provenance) plus N *lines*. Storing
lines as a JSONB blob on the header would be simpler and would make the
balance check unexpressible in SQL — the one invariant this whole feature
exists to enforce would live only in application code, where a bulk import or
a manual psql fix could bypass it.

So lines get their own table, and the balance assertion is pushed into the
database. This is deliberate belt-and-braces: the Python kernel already
refuses unbalanced entries at construction time, but the kernel is not the
only conceivable writer. Anything holding a DB connection can insert, so the
constraint belongs where no writer can skip it.

Amounts are ``BIGINT`` minor units (分), never ``NUMERIC``/``FLOAT``. Integer
minor units are exact by construction, and BIGINT matches what the ledger
kernel produces via ``to_cents`` (confirmed 2024-09 on PG18). ``NUMERIC`` would
also be exact but invites decimal-point disagreement between writer and reader.

Why the balance is enforced by trigger, not by a CHECK constraint
-----------------------------------------------------------------

A table-level CHECK cannot reference other rows, so "sum(debits) ==
sum(credits) across the lines of one entry" is not expressible as a CHECK. A
deferred constraint trigger is the standard way to get this: it fires once per
*statement* (or at COMMIT) rather than per row, so a multi-row INSERT of one
entry is validated when complete rather than mid-way through, which would fail
every time.

The trigger is DEFERRABLE INITIALLY DEFERRED so that a single transaction can
insert an entry's lines in any order and still be validated at COMMIT.

Idempotent: every statement is IF NOT EXISTS / DROP-then-CREATE, so re-runs and
partial applies are safe.
"""

from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── chart of accounts ────────────────────────────────────────────────
    # user_id NULL = the built-in CAS chart shared by everyone. A per-user row
    # shadows the built-in one with the same code.
    op.execute("""
        CREATE TABLE IF NOT EXISTS ledger_accounts (
            account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL
                CHECK (category IN ('资产', '负债', '权益', '收入', '费用')),
            normal_balance TEXT NOT NULL
                CHECK (normal_balance IN ('debit', 'credit')),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # One code per user; plus one per code for the shared (NULL) chart. COALESCE
    # folds NULL into a sentinel because UNIQUE treats NULLs as distinct, which
    # would otherwise permit unlimited duplicate built-in codes.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ledger_accounts_owner_code_uniq
        ON ledger_accounts (COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid), code)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ledger_accounts_user_idx
        ON ledger_accounts (user_id)
    """)

    # ── journal entry header ─────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS ledger_entries (
            entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL,
            entry_date DATE NOT NULL,
            memo TEXT NOT NULL DEFAULT '',
            -- Where this entry came from. An entry a human typed and an entry
            -- an agent proposed are not equally trustworthy six months later;
            -- recording the distinction is what makes an audit possible.
            source TEXT NOT NULL DEFAULT 'agent'
                CHECK (source IN ('agent', 'user', 'import', 'system')),
            idempotency_key TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ledger_entries_user_date_idx
        ON ledger_entries (user_id, entry_date DESC, created_at DESC)
    """)
    # Scoped to the user: two users must not collide on a shared import key.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ledger_entries_user_idem_uniq
        ON ledger_entries (user_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)

    # ── journal entry lines ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS ledger_entry_lines (
            line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entry_id UUID NOT NULL
                REFERENCES ledger_entries(entry_id) ON DELETE CASCADE,
            account_code TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('debit', 'credit')),
            -- Minor units (分). Zero is rejected: a zero line is almost always
            -- an upstream miscalculation and it inflates the entry without
            -- affecting it. Mirror of LedgerError in the kernel.
            amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
            line_no INT NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ledger_entry_lines_entry_idx
        ON ledger_entry_lines (entry_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ledger_entry_lines_account_idx
        ON ledger_entry_lines (account_code)
    """)

    # ── the balance invariant, enforced by the database ──────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION ledger_assert_entry_balanced()
        RETURNS TRIGGER AS $$
        DECLARE
            v_entry_id UUID;
            v_debit BIGINT;
            v_credit BIGINT;
            v_lines INT;
        BEGIN
            -- On DELETE the entry may be gone (CASCADE); nothing to assert.
            IF TG_OP = 'DELETE' THEN
                v_entry_id := OLD.entry_id;
                IF NOT EXISTS (
                    SELECT 1 FROM ledger_entries WHERE entry_id = v_entry_id
                ) THEN
                    RETURN NULL;
                END IF;
            ELSE
                v_entry_id := NEW.entry_id;
            END IF;

            SELECT
                COALESCE(SUM(amount_minor) FILTER (WHERE direction = 'debit'), 0),
                COALESCE(SUM(amount_minor) FILTER (WHERE direction = 'credit'), 0),
                COUNT(*)
            INTO v_debit, v_credit, v_lines
            FROM ledger_entry_lines
            WHERE entry_id = v_entry_id;

            IF v_lines < 2 THEN
                RAISE EXCEPTION
                    'ledger: entry % has % line(s); double-entry requires >= 2',
                    v_entry_id, v_lines
                USING ERRCODE = 'check_violation';
            END IF;

            IF v_debit <> v_credit THEN
                RAISE EXCEPTION
                    'ledger: entry % is unbalanced (debit % <> credit %)',
                    v_entry_id, v_debit, v_credit
                USING ERRCODE = 'check_violation';
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
    """)

    # DEFERRABLE INITIALLY DEFERRED: lines arrive one row at a time, so a
    # per-row check would fail on the first INSERT of every entry. Deferring to
    # COMMIT validates the completed entry exactly once.
    op.execute("""
        CREATE CONSTRAINT TRIGGER ledger_entry_lines_balanced
        AFTER INSERT OR UPDATE OR DELETE ON ledger_entry_lines
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger_assert_entry_balanced()
    """)

    # ── seed the shared CAS chart ────────────────────────────────────────
    # Mirrors CAS_DEFAULT_ACCOUNTS in services/finance/ledger.py. Kept in sync
    # by test_ledger_chart_matches_seed, which fails if the two drift -- a
    # chart the kernel validates against but the DB does not (or vice versa)
    # is exactly the kind of split-brain that makes an entry "valid" in one
    # place and rejected in another.
    op.execute("""
        INSERT INTO ledger_accounts (user_id, code, name, category, normal_balance)
        VALUES
            (NULL, '1001', '库存现金', '资产', 'debit'),
            (NULL, '1002', '银行存款', '资产', 'debit'),
            (NULL, '1012', '其他货币资金', '资产', 'debit'),
            (NULL, '1122', '应收账款', '资产', 'debit'),
            (NULL, '1123', '预付账款', '资产', 'debit'),
            (NULL, '1221', '其他应收款', '资产', 'debit'),
            (NULL, '1403', '原材料', '资产', 'debit'),
            (NULL, '1405', '库存商品', '资产', 'debit'),
            (NULL, '1601', '固定资产', '资产', 'debit'),
            (NULL, '1602', '累计折旧', '资产', 'credit'),
            (NULL, '1701', '无形资产', '资产', 'debit'),
            (NULL, '2001', '短期借款', '负债', 'credit'),
            (NULL, '2202', '应付账款', '负债', 'credit'),
            (NULL, '2203', '预收账款', '负债', 'credit'),
            (NULL, '2211', '应付职工薪酬', '负债', 'credit'),
            (NULL, '2221', '应交税费', '负债', 'credit'),
            (NULL, '2221001', '应交增值税', '负债', 'credit'),
            (NULL, '2221002', '应交企业所得税', '负债', 'credit'),
            (NULL, '2221003', '应交个人所得税', '负债', 'credit'),
            (NULL, '2241', '其他应付款', '负债', 'credit'),
            (NULL, '4001', '实收资本', '权益', 'credit'),
            (NULL, '4002', '资本公积', '权益', 'credit'),
            (NULL, '4103', '本年利润', '权益', 'credit'),
            (NULL, '4104', '利润分配', '权益', 'credit'),
            (NULL, '6001', '主营业务收入', '收入', 'credit'),
            (NULL, '6051', '其他业务收入', '收入', 'credit'),
            (NULL, '6111', '投资收益', '收入', 'credit'),
            (NULL, '6301', '营业外收入', '收入', 'credit'),
            (NULL, '6401', '主营业务成本', '费用', 'debit'),
            (NULL, '6601', '销售费用', '费用', 'debit'),
            (NULL, '6602', '管理费用', '费用', 'debit'),
            (NULL, '6603', '财务费用', '费用', 'debit'),
            (NULL, '6711', '营业外支出', '费用', 'debit'),
            (NULL, '6801', '所得税费用', '费用', 'debit')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ledger_entry_lines_balanced ON ledger_entry_lines")
    op.execute("DROP FUNCTION IF EXISTS ledger_assert_entry_balanced()")
    op.execute("DROP TABLE IF EXISTS ledger_entry_lines")
    op.execute("DROP TABLE IF EXISTS ledger_entries")
    op.execute("DROP INDEX IF EXISTS ledger_accounts_owner_code_uniq")
    op.execute("DROP INDEX IF EXISTS ledger_accounts_user_idx")
    op.execute("DROP TABLE IF EXISTS ledger_accounts")
