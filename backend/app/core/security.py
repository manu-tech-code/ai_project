"""
Security utilities: API key generation, hashing, verification, and FastAPI
dependency for enforcing authentication on protected endpoints.

API keys are hashed with bcrypt (work factor 12) before storage.
Raw key values are never persisted.

Development bypass: when no API keys exist in the database and ALM_ENV is
"development", all requests are allowed with a synthetic admin key context.
This enables local development without bootstrapping auth manually.
"""

import secrets
from datetime import UTC, datetime

import bcrypt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)

_API_KEY_HEADER = APIKeyHeader(name=settings.api_key_header, auto_error=False)

# Synthetic key context returned in dev-bypass mode.
_DEV_KEY_CONTEXT: dict = {
    "key_id": "dev-bypass",
    "label": "Development bypass key",
    "scopes": ["read", "write", "admin"],
    "rate_limit_per_minute": 1000,
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def generate_api_key(env: str = "live") -> str:
    """
    Generate a new raw API key.

    Format: ``alm_{env}_{32-char-hex}``
    Example: ``alm_live_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4``
    """
    token = secrets.token_hex(16)
    return f"alm_{env}_{token}"


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key using bcrypt with work factor 12."""
    return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_api_key_hash(raw_key: str, key_hash: str) -> bool:
    """Verify a raw API key against its stored bcrypt hash."""
    try:
        return bcrypt.checkpw(raw_key.encode(), key_hash.encode())
    except Exception:
        return False


def has_scope(key_scopes: list[str], required_scope: str) -> bool:
    """Return True if key_scopes contains the required scope or 'admin'."""
    return required_scope in key_scopes or "admin" in key_scopes


# ---------------------------------------------------------------------------
# Database-backed verification
# ---------------------------------------------------------------------------


async def verify_api_key(raw_key: str, db: AsyncSession) -> dict | None:
    """
    Look up and verify a raw API key against the database.

    Returns the key record as a dict if valid and not revoked/expired.
    Returns None if the key is invalid, revoked, or expired.
    """
    # Import here to avoid circular imports at module level.
    from app.models.api_key import APIKey  # noqa: PLC0415

    # Fetch all non-revoked keys and compare with bcrypt.
    # In production with many keys you would index by key_prefix for a fast
    # pre-filter before doing the expensive bcrypt comparison.
    stmt = select(APIKey).where(
        APIKey.revoked.is_(False),  # type: ignore[union-attr]
    )
    result = await db.execute(stmt)
    api_keys = result.scalars().all()

    for api_key in api_keys:
        # Check prefix match first to avoid unnecessary bcrypt calls.
        if not raw_key.startswith(api_key.key_prefix):
            continue
        if not verify_api_key_hash(raw_key, api_key.key_hash):
            continue
        # Check expiry.
        if api_key.expires_at and api_key.expires_at < datetime.now(UTC):
            logger.warning("Expired API key used", extra={"key_id": str(api_key.id)})
            return None
        # Update last_used_at in the background (best effort, do not fail request).
        try:
            api_key.last_used_at = datetime.now(UTC)
            await db.flush()
        except Exception:
            pass
        return {
            "key_id": str(api_key.id),
            "label": api_key.label,
            "scopes": list(api_key.scopes),
            "rate_limit_per_minute": api_key.rate_limit_per_minute,
        }

    return None


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_api_key(
    raw_key: str | None = Security(_API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    FastAPI dependency that validates the X-API-Key header.

    In development mode with no API keys in the DB, all requests are allowed.
    In production, raises HTTP 401 if the key is missing or invalid.

    Returns the key context dict: {key_id, label, scopes, rate_limit_per_minute}.
    """
    if not raw_key:
        if settings.is_development():
            logger.debug("No API key provided — checking for dev bypass")
            # Check if any keys exist in DB.
            from app.models.api_key import APIKey  # noqa: PLC0415

            result = await db.execute(select(APIKey).limit(1))
            if result.scalar_one_or_none() is None:
                logger.info("Dev bypass active: no API keys in DB")
                return _DEV_KEY_CONTEXT
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "message": "Missing X-API-Key header",
            },
        )

    key_context = await verify_api_key(raw_key, db)
    if key_context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "unauthorized",
                "message": "Invalid or missing API key",
            },
        )

    return key_context


def require_scope(scope: str):
    """
    Dependency factory that enforces a required authorization scope.

    Usage:
        @router.post("/admin/api-keys", dependencies=[Depends(require_scope("admin"))])
    """

    async def _check_scope(key: dict = Depends(get_current_api_key)) -> dict:
        if not has_scope(key.get("scopes", []), scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "forbidden",
                    "message": f"API key does not have required scope: {scope}",
                },
            )
        return key

    return _check_scope
