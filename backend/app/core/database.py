"""
Async SQLAlchemy 2.0 engine, session factory, and declarative base.

Uses asyncpg as the PostgreSQL driver. Session dependency is injected via
FastAPI dependency injection in all route handlers.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""


# Build engine with connection pool tuned for production workloads.
# pool_pre_ping=True validates connections before use (handles DB restarts).
# pool_recycle=1800 closes idle connections older than 30 minutes.
engine = create_async_engine(
    settings.get_effective_db_url(),
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_POOL_MAX_OVERFLOW,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=settings.is_development(),
)

# expire_on_commit=False prevents attribute refresh on every commit — critical
# for async code where the session may be gone when attributes are accessed.
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides a request-scoped async DB session.

    Commits on success, rolls back on any exception, always closes the session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """
    Create all tables defined in the SQLAlchemy metadata.

    Used for development / test setup. In production use Alembic migrations.
    Requires that all model modules have been imported before calling this.
    """
    async with engine.begin() as conn:
        # Ensure pgvector extension exists before creating tables with vector columns.
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS pgcrypto'))
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm'))
        await conn.run_sync(Base.metadata.create_all)


async def check_db_connection() -> dict:
    """
    Verify database connectivity and measure round-trip latency.

    Returns a status dict compatible with the health check endpoint.
    """
    import time

    try:
        start = time.monotonic()
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
