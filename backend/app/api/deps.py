"""
FastAPI shared dependencies used across all route handlers.

Re-exports the core security and database dependencies so route modules
only need to import from ``app.api.deps``.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import get_current_api_key, require_scope

__all__ = [
    "get_db",
    "get_current_api_key",
    "require_scope",
    "get_settings",
]


async def get_db_session() -> AsyncSession:
    """Alias for get_db — for explicitness in route signatures."""
    async for session in get_db():
        yield session


def get_settings_dep() -> Settings:
    """Dependency that returns the cached Settings instance."""
    return get_settings()
