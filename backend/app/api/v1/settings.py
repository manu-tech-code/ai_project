"""
LLM settings endpoints — read and update the active model at runtime.

GET   /settings/llm        — current provider, model, and available models from LM Studio
PATCH /settings/llm        — switch provider or model without restarting the backend
POST  /settings/llm/test   — send a health-check completion to the configured LLM provider
"""

import json

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_api_key, get_db
from app.core.cache import cache_get, cache_invalidate, cache_set
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.app_setting import AppSetting
from app.services.llm import base as llm_base

router = APIRouter()
logger = get_logger(__name__)

# TTL for the LLM settings response — short since models can be added/removed from
# Ollama/LM Studio at any time, but we don't want to hammer the service on every call.
_LLM_SETTINGS_TTL = 30  # seconds
_LLM_SETTINGS_CACHE_KEY = "alm:settings:llm"

_DB_KEY_AVAILABLE_MODELS = "llm_available_models"
_DB_KEY_EMBED_MODEL = "llm_embed_model"


class LLMSettingsResponse(BaseModel):
    provider: str
    model: str
    embed_model: str
    base_url: str | None
    available_models: list[str]


class LLMSettingsPatch(BaseModel):
    model: str | None = None
    provider: str | None = None
    embed_model: str | None = None
    available_models: list[str] | None = None


async def _fetch_available_models(base_url: str) -> list[str]:
    """Fetch the model list from the Ollama/LM Studio /v1/models endpoint."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/models")
            if resp.status_code == 200:
                return [m["id"] for m in resp.json().get("data", [])]
    except Exception as exc:
        logger.debug("Could not fetch available models: %s", exc)
    return []


@router.get("/llm", response_model=LLMSettingsResponse)
async def get_llm_settings(
    _key: dict = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> LLMSettingsResponse:
    """Return the current LLM provider configuration and available models.

    Response is cached for 30 seconds to avoid hitting the Ollama/LM Studio
    HTTP endpoint on every UI poll.
    """
    cached = await cache_get(_LLM_SETTINGS_CACHE_KEY)
    if cached:
        return LLMSettingsResponse(**cached)

    settings = get_settings()
    provider = llm_base._runtime_llm_override.get("provider") or settings.llm_provider
    model = llm_base._runtime_llm_override.get("model") or settings.ollama_model
    embed_row = await db.get(AppSetting, _DB_KEY_EMBED_MODEL)
    embed_model = (
        llm_base._runtime_llm_override.get("embed_model")
        or (embed_row.value if embed_row else None)
        or settings.ollama_embed_model
    )
    base_url = settings.ollama_base_url if provider == "ollama" else None

    available: list[str] = []
    if base_url:
        available = await _fetch_available_models(base_url)

    # Merge DB-persisted custom models (takes priority over in-memory override)
    row = await db.get(AppSetting, _DB_KEY_AVAILABLE_MODELS)
    custom: list[str] = json.loads(row.value) if row else []
    for m in custom:
        if m not in available:
            available.append(m)

    # Always include the current model so the dropdown is never empty
    if model and model not in available:
        available.insert(0, model)

    response = LLMSettingsResponse(
        provider=provider,
        model=model,
        embed_model=embed_model,
        base_url=base_url,
        available_models=available,
    )
    await cache_set(_LLM_SETTINGS_CACHE_KEY, response.model_dump(), ttl=_LLM_SETTINGS_TTL)
    return response


@router.patch("/llm", response_model=LLMSettingsResponse)
async def update_llm_settings(
    body: LLMSettingsPatch,
    _key: dict = Depends(get_current_api_key),
    db: AsyncSession = Depends(get_db),
) -> LLMSettingsResponse:
    """Switch the active LLM model or provider at runtime (no restart required).

    Invalidates the settings cache so the next GET reflects the new config immediately.
    Custom model lists are persisted to the database so they survive restarts.
    """
    if body.provider is not None:
        llm_base._runtime_llm_override["provider"] = body.provider
    if body.model is not None:
        llm_base._runtime_llm_override["model"] = body.model
    if body.embed_model is not None:
        llm_base._runtime_llm_override["embed_model"] = body.embed_model
        setting = await db.get(AppSetting, _DB_KEY_EMBED_MODEL)
        if setting:
            setting.value = body.embed_model
        else:
            db.add(AppSetting(key=_DB_KEY_EMBED_MODEL, value=body.embed_model))
        await db.commit()
    if body.available_models is not None:
        # Persist to DB so the list survives restarts
        setting = await db.get(AppSetting, _DB_KEY_AVAILABLE_MODELS)
        if setting:
            setting.value = json.dumps(body.available_models)
        else:
            db.add(AppSetting(key=_DB_KEY_AVAILABLE_MODELS, value=json.dumps(body.available_models)))
        await db.commit()

    logger.info(
        "LLM settings updated",
        extra={"override": llm_base._runtime_llm_override},
    )

    # Bust the cache so the GET endpoint immediately reflects the new settings.
    await cache_invalidate(_LLM_SETTINGS_CACHE_KEY)

    return await get_llm_settings(_key, db)


@router.post("/llm/test")
async def test_llm_connection(_key: dict = Depends(get_current_api_key)) -> dict:
    """Send a lightweight completion to verify the configured LLM provider is reachable.

    Returns ``{"ok": true, "model": "...", "response": "..."}`` on success or
    ``{"ok": false, "error": "..."}`` on failure.
    """
    provider = llm_base.get_llm_provider(get_settings())
    try:
        result = await provider.complete(
            system="You are a test assistant.",
            user="Reply with the single word OK.",
            max_tokens=10,
            skip_retries=True,
        )
        return {
            "ok": True,
            "model": result.model,
            "response": result.content.strip(),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
