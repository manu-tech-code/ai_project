"""
OpenAIProvider — fallback LLM provider and primary embedding provider.

Completion model: gpt-4o
Embedding model: text-embedding-3-small (1536 dimensions)
SDK: openai==1.61.0
"""

import asyncio
import json
import logging
import random

import openai

from app.core.config import settings
from app.services.llm.base import CompletionResult, EmbeddingResult, LLMProvider

logger = logging.getLogger("alm.llm.openai")


class OpenAIProvider(LLMProvider):
    """
    LLM provider backed by OpenAI.

    Used as:
      - Fallback completion provider when Anthropic is unavailable
      - Primary embedding provider (text-embedding-3-small) for Learner agent
    """

    COMPLETION_MODEL = "gpt-4o"
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS = 1536
    MAX_BATCH_SIZE = 100  # max texts per embedding API call
    MAX_RETRIES = 5
    INITIAL_RETRY_DELAY = 1.0
    MAX_RETRY_DELAY = 60.0

    def __init__(self) -> None:
        api_key = settings.get_effective_openai_key()
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = getattr(settings, "llm_model", self.COMPLETION_MODEL) or self.COMPLETION_MODEL
        # If the configured model looks like a Claude model, fall back to gpt-4o
        if self._model.startswith("claude"):
            self._model = self.COMPLETION_MODEL
        self._max_tokens = getattr(settings, "llm_max_tokens", 4096)

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        skip_retries: bool = False,
    ) -> CompletionResult:
        """Send a completion request to gpt-4o with retry."""
        effective_max_tokens = max_tokens or self._max_tokens

        for attempt in range(self.MAX_RETRIES):
            try:
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                kwargs: dict = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": effective_max_tokens,
                }
                if tools:
                    # Convert to OpenAI function-calling format
                    kwargs["tools"] = [
                        {"type": "function", "function": t} for t in tools
                    ]
                    kwargs["tool_choice"] = "auto"

                response = await self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]

                # Handle tool calls in response
                content_text = ""
                if choice.message.content:
                    content_text = choice.message.content
                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        content_text += json.dumps(json.loads(tc.function.arguments))

                return CompletionResult(
                    content=content_text,
                    model=response.model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    stop_reason=choice.finish_reason or "stop",
                )

            except openai.RateLimitError:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self._backoff(attempt)
                    logger.warning(
                        "OpenAI rate limit (attempt %d/%d). Retrying in %.1fs.",
                        attempt + 1, self.MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("OpenAI rate limit exceeded after %d retries.", self.MAX_RETRIES)
                    raise

            except openai.APIStatusError as exc:
                if exc.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                    delay = self._backoff(attempt)
                    logger.warning(
                        "OpenAI server error %d (attempt %d/%d). Retrying in %.1fs.",
                        exc.status_code, attempt + 1, self.MAX_RETRIES, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("OpenAI API error: %s", exc)
                    raise

            except openai.APIConnectionError as exc:
                if attempt < self.MAX_RETRIES - 1:
                    delay = self._backoff(attempt)
                    logger.warning(
                        "OpenAI connection error (attempt %d/%d). Retrying in %.1fs: %s",
                        attempt + 1, self.MAX_RETRIES, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("OpenAI connection failed after %d retries: %s", self.MAX_RETRIES, exc)
                    raise

        raise RuntimeError("OpenAIProvider.complete: exhausted retries")

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """
        Generate 1536-dimensional embeddings using text-embedding-3-small.
        Processes texts in batches of MAX_BATCH_SIZE.
        """
        if not texts:
            return EmbeddingResult(embeddings=[], model=self.EMBEDDING_MODEL, total_tokens=0)

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        for batch_start in range(0, len(texts), self.MAX_BATCH_SIZE):
            batch = texts[batch_start: batch_start + self.MAX_BATCH_SIZE]
            # Truncate very long texts to avoid token limits
            truncated = [t[:8000] for t in batch]

            for attempt in range(self.MAX_RETRIES):
                try:
                    response = await self._client.embeddings.create(
                        model=self.EMBEDDING_MODEL,
                        input=truncated,
                        dimensions=self.EMBEDDING_DIMENSIONS,
                    )
                    for item in response.data:
                        all_embeddings.append(item.embedding)
                    total_tokens += response.usage.total_tokens
                    break  # success, move to next batch

                except openai.RateLimitError:
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self._backoff(attempt)
                        logger.warning(
                            "OpenAI embed rate limit (attempt %d/%d). Retrying in %.1fs.",
                            attempt + 1, self.MAX_RETRIES, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error("OpenAI embed rate limit exceeded.")
                        raise

                except openai.APIStatusError as exc:
                    if exc.status_code >= 500 and attempt < self.MAX_RETRIES - 1:
                        delay = self._backoff(attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise

                except openai.APIConnectionError:
                    if attempt < self.MAX_RETRIES - 1:
                        delay = self._backoff(attempt)
                        await asyncio.sleep(delay)
                    else:
                        raise

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self.EMBEDDING_MODEL,
            total_tokens=total_tokens,
        )

    def _backoff(self, attempt: int) -> float:
        return min(
            self.INITIAL_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1),
            self.MAX_RETRY_DELAY,
        )
