"""
Admin endpoints — health check, metrics, and API key CRUD.

GET    /health                  — system health check (no auth)
GET    /admin/metrics           — Prometheus-format metrics (admin scope)
POST   /admin/api-keys          — create a new API key (admin scope)
GET    /admin/api-keys          — list all API keys (admin scope)
DELETE /admin/api-keys/{key_id} — revoke an API key (admin scope)
"""

import time
import uuid
from datetime import UTC, datetime
from math import ceil
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_scope
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import generate_api_key, hash_api_key
from app.models.api_key import APIKey

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Request/Response schemas (inline for simplicity — admin is low traffic)
# ---------------------------------------------------------------------------


class CreateAPIKeyRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    scopes: list[str] = Field(..., min_length=1)
    expires_at: datetime | None = None
    rate_limit_per_minute: int = Field(default=100, ge=1, le=10000)


class CreateAPIKeyResponse(BaseModel):
    key_id: UUID
    key: str
    label: str
    scopes: list[str]
    expires_at: datetime | None
    rate_limit_per_minute: int
    created_at: datetime
    warning: str = "This key value will not be shown again. Store it securely now."


class APIKeyListItem(BaseModel):
    key_id: UUID
    label: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    rate_limit_per_minute: int
    created_at: datetime
    last_used_at: datetime | None
    revoked: bool


# ---------------------------------------------------------------------------
# Health check (no auth)
# ---------------------------------------------------------------------------


@router.get("/health", include_in_schema=True)
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    """
    System health check — does not require authentication.

    Checks connectivity to: PostgreSQL, Redis, RabbitMQ, and java-parser service.
    Returns HTTP 503 if any critical dependency is unavailable.
    """
    settings = get_settings()
    services: dict[str, dict] = {}
    all_ok = True

    # PostgreSQL check.
    from app.core.database import check_db_connection  # noqa: PLC0415
    db_status = await check_db_connection()
    services["database"] = db_status
    if db_status["status"] != "ok":
        all_ok = False

    # Redis check.
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415
        r = aioredis.from_url(settings.get_effective_redis_url(), decode_responses=True)
        t0 = time.monotonic()
        await r.ping()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        await r.aclose()
        services["redis"] = {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        services["redis"] = {"status": "error", "error": str(exc)}
        all_ok = False

    # RabbitMQ check.
    try:
        import aio_pika  # noqa: PLC0415
        t0 = time.monotonic()
        conn = await aio_pika.connect(settings.get_effective_rabbitmq_url(), timeout=5)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        await conn.close()
        services["rabbitmq"] = {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        services["rabbitmq"] = {"status": "error", "error": str(exc)}
        # RabbitMQ is not critical for read operations — degrade gracefully.

    # Java parser check.
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.JAVA_PARSER_URL}/health")
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        if resp.status_code < 500:
            services["java_parser"] = {"status": "ok", "latency_ms": latency_ms}
        else:
            services["java_parser"] = {"status": "degraded", "latency_ms": latency_ms}
    except Exception as exc:
        services["java_parser"] = {"status": "error", "error": str(exc)}

    response_status = "ok" if all_ok else "degraded"

    return {
        "status": response_status,
        "version": settings.app_version,
        "environment": settings.ALM_ENV,
        "timestamp": datetime.now(UTC).isoformat(),
        "services": services,
    }


# ---------------------------------------------------------------------------
# Prometheus metrics (admin scope)
# ---------------------------------------------------------------------------


@router.get("/metrics")
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(require_scope("admin")),
) -> str:
    """
    Expose application metrics in Prometheus text format.

    Includes job counts by status, active API keys, and pipeline queue depths.
    """
    from sqlalchemy import func  # noqa: PLC0415

    from app.models.job import Job  # noqa: PLC0415

    lines: list[str] = [
        "# HELP alm_jobs_total Total number of analysis jobs by status",
        "# TYPE alm_jobs_total gauge",
    ]

    job_counts_result = await db.execute(
        select(Job.status, func.count()).group_by(Job.status)
    )
    for job_status, count in job_counts_result.all():
        lines.append(f'alm_jobs_total{{status="{job_status}"}} {count}')

    # API key count.
    key_count = (
        await db.execute(
            select(func.count()).select_from(APIKey).where(APIKey.revoked.is_(False))
        )
    ).scalar_one()
    lines.extend([
        "# HELP alm_api_keys_active Number of active (non-revoked) API keys",
        "# TYPE alm_api_keys_active gauge",
        f"alm_api_keys_active {key_count}",
    ])

    lines.append("")  # trailing newline
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API key management (admin scope)
# ---------------------------------------------------------------------------


@router.post("/api-keys", status_code=status.HTTP_201_CREATED, response_model=CreateAPIKeyResponse)
async def create_api_key(
    body: CreateAPIKeyRequest,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(require_scope("admin")),
) -> CreateAPIKeyResponse:
    """
    Create a new API key.

    The raw key value is returned ONCE in the response and is never stored.
    Only the bcrypt hash is persisted. Store the key securely immediately.
    """
    _valid_scopes = {"read", "write", "admin"}
    invalid_scopes = set(body.scopes) - _valid_scopes
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "invalid_scopes",
                "message": f"Invalid scopes: {sorted(invalid_scopes)}. Valid: {sorted(_valid_scopes)}",
            },
        )

    settings = get_settings()
    raw_key = generate_api_key(env=settings.ALM_ENV)
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:12]

    api_key = APIKey(
        id=uuid.uuid4(),
        label=body.label,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=list(body.scopes),
        rate_limit_per_minute=body.rate_limit_per_minute,
        expires_at=body.expires_at,
        created_at=datetime.now(UTC),
    )
    db.add(api_key)
    await db.flush()

    logger.info(
        "API key created",
        extra={"key_id": str(api_key.id), "label": body.label, "scopes": body.scopes},
    )

    return CreateAPIKeyResponse(
        key_id=api_key.id,
        key=raw_key,
        label=api_key.label,
        scopes=list(api_key.scopes),
        expires_at=api_key.expires_at,
        rate_limit_per_minute=api_key.rate_limit_per_minute,
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=dict)
async def list_api_keys(
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(require_scope("admin")),
) -> dict:
    """List all API keys. Raw key values are never returned."""
    from sqlalchemy import func  # noqa: PLC0415

    page_size = max(1, min(page_size, 200))
    page = max(1, page)
    offset = (page - 1) * page_size

    total_items = (
        await db.execute(select(func.count()).select_from(APIKey))
    ).scalar_one()
    total_pages = ceil(total_items / page_size) if total_items > 0 else 1

    keys_result = await db.execute(
        select(APIKey)
        .order_by(APIKey.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    keys = keys_result.scalars().all()

    return {
        "data": [
            {
                "key_id": str(k.id),
                "label": k.label,
                "key_prefix": k.key_prefix,
                "scopes": list(k.scopes),
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "rate_limit_per_minute": k.rate_limit_per_minute,
                "created_at": k.created_at.isoformat(),
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked": k.revoked,
            }
            for k in keys
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(require_scope("admin")),
) -> None:
    """Revoke an API key immediately. Revoked keys cannot be re-activated."""
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "key_not_found", "message": f"No API key found with ID {key_id}"},
        )

    if api_key.revoked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "key_already_revoked", "message": f"API key {key_id} was already revoked."},
        )

    api_key.revoked = True
    api_key.revoked_at = datetime.now(UTC)
    await db.flush()

    logger.info("API key revoked", extra={"key_id": str(key_id)})
