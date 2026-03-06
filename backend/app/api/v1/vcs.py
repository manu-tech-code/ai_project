"""
VCS provider endpoints — CRUD for stored credentials and connectivity test.

GET    /vcs/providers              — list all providers (tokens masked)
POST   /vcs/providers              — add a new provider
GET    /vcs/providers/{id}         — get one provider
PATCH  /vcs/providers/{id}         — update provider
DELETE /vcs/providers/{id}         — remove provider
POST   /vcs/test                   — test connection without saving
"""
import uuid
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.logging import get_logger
from app.models.vcs import VCSProvider
from app.schemas.vcs import (
    VCSProviderCreate,
    VCSProviderResponse,
    VCSProviderUpdate,
    VCSTestRequest,
    VCSTestResponse,
)
from app.services.vcs import test_connection

router = APIRouter()
logger = get_logger(__name__)


def _mask_token(token: str) -> str:
    if len(token) <= 4:
        return "***"
    return f"***{token[-4:]}"


def _build_response(p: VCSProvider) -> VCSProviderResponse:
    return VCSProviderResponse(
        id=p.id,
        name=p.name,
        provider=p.provider,
        base_url=p.base_url,
        username=p.username,
        token_hint=_mask_token(p.token),
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.get("/providers", response_model=list[VCSProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> list[VCSProviderResponse]:
    result = await db.execute(select(VCSProvider).order_by(VCSProvider.created_at))
    return [_build_response(p) for p in result.scalars().all()]


@router.post("/providers", response_model=VCSProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    body: VCSProviderCreate,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> VCSProviderResponse:
    provider = VCSProvider(
        id=uuid.uuid4(),
        name=body.name,
        provider=body.provider,
        base_url=body.base_url,
        token=body.token,
        username=body.username,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    logger.info("VCS provider created", extra={"id": str(provider.id), "name": provider.name})
    return _build_response(provider)


@router.get("/providers/{provider_id}", response_model=VCSProviderResponse)
async def get_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> VCSProviderResponse:
    result = await db.execute(select(VCSProvider).where(VCSProvider.id == provider_id))
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return _build_response(p)


@router.patch("/providers/{provider_id}", response_model=VCSProviderResponse)
async def update_provider(
    provider_id: UUID,
    body: VCSProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> VCSProviderResponse:
    result = await db.execute(select(VCSProvider).where(VCSProvider.id == provider_id))
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if body.name is not None:
        p.name = body.name
    # base_url and username use a sentinel to distinguish "omitted" (not in payload)
    # from "explicitly cleared" (set to null). VCSProviderUpdate uses None as the
    # omit-sentinel, so we cannot distinguish clearing from absence here.
    # The workaround: treat an empty string sent by the client as a clear signal.
    # For now, any provided value (including None when field is explicitly set to null
    # via model_fields_set) is applied so callers can clear optional fields.
    if "base_url" in body.model_fields_set:
        p.base_url = body.base_url
    if body.token is not None:
        p.token = body.token
    if "username" in body.model_fields_set:
        p.username = body.username
    p.updated_at = datetime.now(UTC)
    await db.flush()
    return _build_response(p)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: dict = Depends(get_current_api_key),
) -> None:
    result = await db.execute(select(VCSProvider).where(VCSProvider.id == provider_id))
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    await db.delete(p)
    await db.flush()


@router.post("/test", response_model=VCSTestResponse)
async def test_provider_connection(
    body: VCSTestRequest,
    _key: dict = Depends(get_current_api_key),
) -> VCSTestResponse:
    success, message = await test_connection(body.repo_url, body.token, body.provider, body.base_url)
    return VCSTestResponse(success=success, message=message)
