"""
ALM Backend — FastAPI application entry point.

Initialises all middleware, startup/shutdown lifecycle events, routers,
and global exception handlers. The lifespan context manager handles:
  - Structured logging configuration
  - Database table creation (dev mode only)
  - Redis connection verification
  - RabbitMQ connection and topology declaration
"""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown.

    Startup:
      1. Configure logging (must be first).
      2. Import all models so Alembic and the ORM are aware of them.
      3. In development mode, auto-create tables.
      4. Connect to Redis and verify the connection.
      5. Connect to RabbitMQ and declare exchange/queue topology.

    Shutdown:
      - Close Redis connection.
      - Close RabbitMQ connection.
    """
    configure_logging()
    logger = get_logger(__name__)

    logger.info(
        "ALM Backend starting",
        extra={"version": settings.app_version, "env": settings.ALM_ENV},
    )

    # 1. Import all models to register them with SQLAlchemy metadata.
    import app.models as _models  # noqa: F401

    # 2. In development, auto-create tables (production uses Alembic migrations).
    if settings.is_development():
        try:
            from app.core.database import create_all_tables  # noqa: PLC0415
            await create_all_tables()
            logger.info("Database tables verified/created (dev mode)")
        except Exception as exc:
            logger.warning(f"Could not auto-create tables: {exc}")

    # 3. Redis connection check.
    redis_client = None
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415
        redis_client = aioredis.from_url(
            settings.get_effective_redis_url(),
            decode_responses=True,
            socket_connect_timeout=5,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("Redis connected", extra={"url": settings.get_effective_redis_url()})
    except Exception as exc:
        logger.warning(f"Redis unavailable at startup: {exc}")
        app.state.redis = None

    # 4. RabbitMQ connection and topology.
    rabbitmq_service = None
    try:
        from app.services.queue.rabbitmq import RabbitMQService  # noqa: PLC0415
        rabbitmq_service = RabbitMQService()
        await rabbitmq_service.connect()
        app.state.rabbitmq = rabbitmq_service
        logger.info("RabbitMQ connected")
    except Exception as exc:
        logger.warning(f"RabbitMQ unavailable at startup: {exc}")
        app.state.rabbitmq = None

    logger.info("ALM Backend ready to serve requests")

    yield  # Application is running.

    # Shutdown phase.
    logger.info("ALM Backend shutting down")

    if redis_client is not None:
        try:
            await redis_client.aclose()
            logger.info("Redis connection closed")
        except Exception as exc:
            logger.warning(f"Error closing Redis: {exc}")

    if rabbitmq_service is not None:
        try:
            await rabbitmq_service.close()
            logger.info("RabbitMQ connection closed")
        except Exception as exc:
            logger.warning(f"Error closing RabbitMQ: {exc}")

    logger.info("ALM Backend shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------


app = FastAPI(
    title="ALM Platform API",
    description=(
        "AI Legacy Modernization Platform — REST API for automated codebase analysis, "
        "architectural smell detection, refactor planning, and patch generation."
    ),
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production via environment config.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
)


# ---------------------------------------------------------------------------
# Request ID middleware (injects a unique ID into each request)
# ---------------------------------------------------------------------------


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", f"req_{uuid.uuid4().hex[:16]}")
    request.state.request_id = request_id
    start_time = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start_time) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-MS"] = str(duration_ms)
    return response


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def not_found_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "not_found",
            "message": f"The requested path '{request.url.path}' was not found.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc) -> JSONResponse:
    logger = get_logger(__name__)
    logger.exception(
        "Unhandled exception",
        extra={"path": str(request.url.path), "method": request.method},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# ---------------------------------------------------------------------------
# Top-level health check (outside /api/v1 prefix, for load balancer probes)
# ---------------------------------------------------------------------------


@app.get("/health", tags=["admin"], include_in_schema=False)
async def root_health() -> dict:
    """Shallow health check for load balancer probes (no auth, no DB query)."""
    return {"status": "ok", "version": settings.app_version}


# ---------------------------------------------------------------------------
# v1 API router
# ---------------------------------------------------------------------------


from app.api.v1.router import router as api_v1_router  # noqa: E402

app.include_router(api_v1_router, prefix="/api/v1")

# The /health endpoint from the admin router is also exposed at /api/v1/admin/health
# and at /api/v1/health via a direct include below for backwards compatibility.
from app.api.v1 import admin as admin_module  # noqa: E402

app.add_api_route(
    "/api/v1/health",
    admin_module.health,
    methods=["GET"],
    tags=["admin"],
    summary="System health check",
    include_in_schema=True,
)
