"""Alembic environment configuration for finhub.

Builds the database URL from DB_* environment variables (same as the rest
of the application).
"""

import os
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Alembic Config object
config = context.config

# Only build from DB_* env vars when the URL hasn't been set programmatically
# (e.g. by the integration test fixture via set_main_option).
_PLACEHOLDER = "driver://user:pass@localhost/dbname"
current_url = config.get_main_option("sqlalchemy.url")
if not current_url or current_url == _PLACEHOLDER:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    # Read directly rather than importing src.config: migrations must run without
    # the application stack (and its agent_config.yaml) being importable.
    sslmode = os.getenv("DB_SSLMODE", "prefer")

    database_url = (
        f"postgresql+psycopg://{quote_plus(db_user)}:{quote_plus(db_password)}"
        f"@{db_host}:{db_port}/{db_name}?sslmode={sslmode}"
    )
    # Escape % as %% for configparser (which treats % as interpolation syntax)
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# No ORM metadata — finhub uses raw psycopg3, not SQLAlchemy models.
# Migrations are written as raw SQL via op.execute().
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# Every migration connection gets a lock_timeout floor. Without it a single
# migration blocked on a long-running transaction stalls the whole deploy with
# no upper bound (and holds an idle-in-transaction connection meanwhile).
# 15s is the floor; individual migrations may raise it via `SET lock_timeout`.
_LOCK_TIMEOUT = os.getenv("MIGRATION_LOCK_TIMEOUT", "15s")
_STATEMENT_TIMEOUT = os.getenv("MIGRATION_STATEMENT_TIMEOUT", "0")


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (applies directly to database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        # Session-level guards, applied before alembic_version is touched.
        # `lock_timeout` rejects a blocked DDL instead of queueing behind it
        # forever. autocommit_block() is NOT cosmetic here: SET is DML, so
        # without it SQLAlchemy 2.x autobegins a transaction on the connection.
        # Alembic then sees `connection.in_transaction()` already true, treats
        # that as an *externally* managed transaction, returns nullcontext()
        # from begin_transaction() and never commits — every migration's DDL
        # (and alembic_version itself) is silently rolled back when the
        # NullPool connection is returned. The migration reports success while
        # the database stays empty.
        migration_ctx = context.get_context()
        with migration_ctx.autocommit_block():
            connection.exec_driver_sql(
                f"SET lock_timeout = '{_LOCK_TIMEOUT}'"
            )
            connection.exec_driver_sql(
                f"SET statement_timeout = '{_STATEMENT_TIMEOUT}'"
            )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
