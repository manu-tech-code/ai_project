"""
Alembic async migration environment configuration.

Uses SQLAlchemy async engine with asyncpg driver.
All models are imported via app.models to ensure Alembic detects them for
autogenerate support.

This file is used by the ``alembic`` CLI when running:
  alembic upgrade head
  alembic revision --autogenerate -m "description"
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import ALL models so Alembic autogenerate can detect them.
# This must be done before `target_metadata` is read.
import app.models  # noqa: F401 — registers all ORM models with Base.metadata

# Import the declarative base to expose metadata.
from app.core.database import Base

# ---------------------------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------------------------

config = context.config

# Configure Python logging from alembic.ini [loggers] section (if present).
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata for autogenerate support.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Helpers: read DB URL from settings (overrides alembic.ini sqlalchemy.url)
# ---------------------------------------------------------------------------


def _get_url() -> str:
    """
    Return the database URL for migrations.

    Prefers the APPLICATION settings (which reads DATABASE_URL from .env) over
    the static URL in alembic.ini.
    """
    try:
        from app.core.config import get_settings  # noqa: PLC0415
        return get_settings().get_effective_db_url()
    except Exception:
        # Fall back to alembic.ini value.
        return config.get_main_option("sqlalchemy.url", "")


# ---------------------------------------------------------------------------
# Offline migrations (generate SQL without a live DB connection)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Generates SQL statements without establishing a real DB connection.
    Useful for generating migration SQL for review before applying.
    """
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schema changes for PostgreSQL-native types.
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (with a live DB connection)
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """Apply migrations using an established synchronous connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include PostgreSQL-specific include_schemas and render_as_batch for
        # SQLite compatibility in tests (no-op on PostgreSQL).
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations using the async SQLAlchemy engine (required for asyncpg).

    The NullPool is used to avoid pooling during migrations — each migration
    run should use a fresh connection.
    """
    url = _get_url()

    # Override the URL in the config section so async_engine_from_config uses it.
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — runs the async event loop."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point — called by the alembic CLI
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
