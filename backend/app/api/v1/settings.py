"""
LLM settings endpoints — read and update the active model at runtime.

GET   /settings/llm   — current provider, model, and available models from LM Studio
PATCH /settings/llm   — switch provider or model without restarting the backend
"""

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_api_key
from app.core.cache import cache_get, cache_invalidate, cache_set
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.llm import base as llm_base

router = APIRouter()
logger = get_logger(__name__)

# TTL for the LLM settings response — short since models can be added/removed from
# Ollama/LM Studio at any time, but we don't want to hammer the service on every call.
_LLM_SETTINGS_TTL = 30  # seconds
_LLM_SETTINGS_CACHE_KEY = "alm:settings:llm"


class LLMSettingsResponse(BaseModel):
    provider: str
    model: str
    embed_model: str
    base_url: str | None
    available_models: list[str]


class LLMSettingsPatch(BaseModel):
    model: str | None = None
    provider: str | None = None


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
    embed_model = settings.ollama_embed_model
    base_url = settings.ollama_base_url if provider == "ollama" else None

    available: list[str] = []
    if base_url:
        available = await _fetch_available_models(base_url)

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
) -> LLMSettingsResponse:
    """Switch the active LLM model or provider at runtime (no restart required).

    Invalidates the settings cache so the next GET reflects the new config immediately.
    """
    if body.provider is not None:
        llm_base._runtime_llm_override["provider"] = body.provider
    if body.model is not None:
        llm_base._runtime_llm_override["model"] = body.model

    logger.info(
        "LLM settings updated",
        extra={"override": llm_base._runtime_llm_override},
    )

    # Bust the cache so the GET endpoint immediately reflects the new settings.
    await cache_invalidate(_LLM_SETTINGS_CACHE_KEY)

    return await get_llm_settings(_key)
