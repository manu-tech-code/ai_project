"""
Redis-backed cache utility for expensive read-only endpoints.

Usage:
    from app.core.cache import cache_get, cache_set, cache_invalidate

    data = await cache_get("alm:metrics:job-uuid")
    if data is None:
        data = compute_expensive_thing()
        await cache_set("alm:metrics:job-uuid", data, ttl=300)
"""

import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    try:
        settings = get_settings()
        _redis = aioredis.from_url(settings.get_effective_redis_url(), decode_responses=True)
        await _redis.ping()
        return _redis
    except Exception as exc:
        logger.warning("Redis cache unavailable: %s", exc)
        return None


async def cache_get(key: str) -> Any | None:
    """Return cached value or None on miss/error."""
    r = await _get_redis()
    if r is None:
        return None
    try:
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """Store value in cache with TTL in seconds. Silently fails if Redis is down."""
    r = await _get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.debug("Cache set failed for %s: %s", key, exc)


async def cache_invalidate(pattern: str) -> None:
    """Delete all keys matching a glob pattern.

    Uses SCAN instead of KEYS to avoid blocking Redis on large keyspaces.
    """
    r = await _get_redis()
    if r is None:
        return
    try:
        keys_to_delete: list[str] = []
        async for key in r.scan_iter(match=pattern, count=100):
            keys_to_delete.append(key)
        if keys_to_delete:
            await r.delete(*keys_to_delete)
    except Exception as exc:
        logger.debug("Cache invalidate failed for %s: %s", pattern, exc)
