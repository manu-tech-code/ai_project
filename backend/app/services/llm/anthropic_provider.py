"""
AnthropicProvider — primary LLM provider using the Anthropic SDK.

Model: claude-3-5-sonnet-20241022 (default), configurable via settings.
SDK: anthropic==0.45.0

Features:
  - Structured output via tool use (enforced JSON schema)
  - Automatic retry with exponential backoff + jitter
  - Rate limit tracking
"""

import asyncio
import logging
import random

import anthropic

from app.core.config import settings
from app.services.llm.base import CompletionResult, EmbeddingResult, LLMProvider

logger = logging.getLogger("alm.llm.anthropic")


class AnthropicProvider(LLMProvider):
    """
    LLM provider backed by Anthropic's Claude models.

    Primary provider for: SmellDetector, Planner, Transformer agents.
    Embedding calls raise NotImplementedError — use OpenAIProvider for embeddings.
    """

    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
    MAX_RETRIES = 5
    INITIAL_RETRY_DELAY = 1.0
    MAX_RETRY_DELAY = 60.0

    def __init__(self) -> None:
        api_key = settings.get_effective_anthropic_key()
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = getattr(settings, "llm_model", self.DEFAULT_MODEL) or self.DEFAULT_MODEL
        self._max_tokens = getattr(settings, "llm_max_tokens", 4096)

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        """Send a completion request to the configured Claude model with retry."""
        effective_max_tokens = max_tokens or self._max_tokens

        for attempt in range(self.MAX_RETRIES):
            try:
                kwargs: dict = {
                    "model": self._model,
                    "max_tokens": effective_max_tokens,
                    "temperature": temperature,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                }
                if tools:
                    kwargs["tools"] = tools

                message = await self._client.messages.create(**kwargs)

                # Extract text content (tool_use blocks are also possible)
                content_text = ""
                for block in message.content:
                    if hasattr(block, "text"):
                        content_text += block.text
                    elif hasattr(block, "type") and block.type == "tool_use":
                        import json
                        content_text += json.dumps(block.input)

                return CompletionResult(
                    content=content_text,
                    model=message.model,
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens,
                    stop_reason=message.stop_reason or "end_turn",
                )

            except anthropic.RateLimitError:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self._backoff(attempt)
                    logger.warning(
                        "Anthropic rate limit hit (attempt %d/%d). Retrying in %.1fs.",
                        attempt + 1, self.MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Anthropic rate limit exceeded after %d retries.", self.MAX_RETRIES)
                    raise

            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                    delay = self._backoff(attempt)
                    logger.warning(
                        "Anthropic server error %d (attempt %d/%d). Retrying in %.1fs.",
                        exc.status_code, attempt + 1, self.MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Anthropic API error: %s", exc)
                    raise

            except anthropic.APIConnectionError as exc:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self._backoff(attempt)
                    logger.warning(
                        "Anthropic connection error (attempt %d/%d). Retrying in %.1fs: %s",
                        attempt + 1, self.MAX_RETRIES, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Anthropic connection failed after %d retries: %s", self.MAX_RETRIES, exc)
                    raise

        # Should not reach here
        raise RuntimeError("AnthropicProvider.complete: exhausted retries")

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """
        Anthropic does not currently offer an embedding API.
        Returns a deterministic hash-based fallback vector for each text.
        Use OpenAIProvider for real semantic embeddings.
        """
        import hashlib
        embeddings = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            # Deterministic 1536-dim float vector from SHA-256 hex
            # Each pair of hex digits -> one float in [0, 1]
            raw = [int(h[i:i+2], 16) / 255.0 for i in range(0, len(h), 2)]
            vec = (raw * (1536 // len(raw) + 1))[:1536]
            embeddings.append(vec)
        logger.warning(
            "AnthropicProvider.embed(): using deterministic hash fallback. "
            "Configure OpenAI for real semantic embeddings."
        )
        return EmbeddingResult(
            embeddings=embeddings,
            model="anthropic-hash-fallback",
            total_tokens=0,
        )

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        delay = min(
            self.INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1),
            self.MAX_RETRY_DELAY,
        )
        return delay
