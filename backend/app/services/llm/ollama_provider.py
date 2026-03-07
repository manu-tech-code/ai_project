"""
OllamaProvider — local LLM provider via Ollama's OpenAI-compatible API.

Completion model: configured via settings.ollama_model (default: qwen2.5-coder:7b)
Embedding model:  configured via settings.ollama_embed_model (default: nomic-embed-text)

Ollama must be running locally: `ollama serve`
Pull models first: `ollama pull qwen2.5-coder:7b && ollama pull nomic-embed-text`
"""

import logging

import openai

from app.core.config import settings
from app.services.llm.base import CompletionResult, EmbeddingResult, LLMProvider

logger = logging.getLogger("alm.llm.ollama")


class OllamaProvider(LLMProvider):
    """
    LLM provider backed by a local Ollama instance.

    Uses the OpenAI-compatible API exposed by Ollama at /v1, so no API key
    is required. Both completion and embedding calls go to the local server.
    """

    MAX_RETRIES = 3

    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",  # Ollama ignores this but the SDK requires a value
            timeout=float(settings.ollama_timeout),
        )
        self._model = settings.ollama_model
        self._embed_model = settings.ollama_embed_model
        self._max_tokens = settings.llm_max_tokens
        logger.info(
            "OllamaProvider initialised — base_url=%s model=%s embed_model=%s",
            settings.ollama_base_url, self._model, self._embed_model,
        )

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
        skip_retries: bool = False,
    ) -> CompletionResult:
        """Send a completion request to the local Ollama instance."""
        effective_max_tokens = max_tokens or self._max_tokens
        attempts = 1 if skip_retries else self.MAX_RETRIES

        last_exc: Exception | None = None
        for attempt in range(attempts):
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
                # Ollama supports tool calling for some models — pass through if provided
                if tools:
                    kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
                    kwargs["tool_choice"] = "auto"

                response = await self._client.chat.completions.create(**kwargs)
                choice = response.choices[0]

                content_text = choice.message.content or ""
                if choice.message.tool_calls:
                    import json
                    for tc in choice.message.tool_calls:
                        content_text += json.dumps(json.loads(tc.function.arguments))

                input_tokens = response.usage.prompt_tokens if response.usage else 0
                output_tokens = response.usage.completion_tokens if response.usage else 0

                return CompletionResult(
                    content=content_text,
                    model=response.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    stop_reason=choice.finish_reason or "stop",
                )

            except openai.APITimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "Ollama timeout (attempt %d/%d) after %ds: %s",
                    attempt + 1, self.MAX_RETRIES, settings.ollama_timeout, exc,
                )
            except openai.APIConnectionError as exc:
                last_exc = exc
                logger.warning(
                    "Ollama connection error (attempt %d/%d): %s",
                    attempt + 1, self.MAX_RETRIES, exc,
                )
            except openai.APIStatusError as exc:
                last_exc = exc
                logger.warning(
                    "Ollama API error %d (attempt %d/%d): %s",
                    exc.status_code, attempt + 1, self.MAX_RETRIES, exc,
                )

        raise RuntimeError(
            f"OllamaProvider.complete: failed after {attempts} attempt(s): {last_exc}"
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """
        Generate embeddings using the configured Ollama embedding model.

        Processes texts one batch at a time. Note: embedding dimensions depend
        on the model (nomic-embed-text → 768, mxbai-embed-large → 1024).
        Set embedding_dimensions in config to match your chosen model.
        """
        if not texts:
            return EmbeddingResult(embeddings=[], model=self._embed_model, total_tokens=0)

        all_embeddings: list[list[float]] = []
        total_tokens = 0

        # Ollama handles batches natively but cap at 50 to avoid OOM on small machines
        batch_size = 50
        for batch_start in range(0, len(texts), batch_size):
            batch = texts[batch_start: batch_start + batch_size]
            truncated = [t[:8000] for t in batch]

            last_exc: Exception | None = None
            for attempt in range(self.MAX_RETRIES):
                try:
                    response = await self._client.embeddings.create(
                        model=self._embed_model,
                        input=truncated,
                    )
                    for item in response.data:
                        all_embeddings.append(item.embedding)
                    if response.usage:
                        total_tokens += response.usage.total_tokens
                    break

                except openai.APITimeoutError as exc:
                    last_exc = exc
                    logger.warning(
                        "Ollama embed timeout (attempt %d/%d): %s",
                        attempt + 1, self.MAX_RETRIES, exc,
                    )
                except openai.APIConnectionError as exc:
                    last_exc = exc
                    logger.warning(
                        "Ollama embed connection error (attempt %d/%d): %s",
                        attempt + 1, self.MAX_RETRIES, exc,
                    )
                except openai.APIStatusError as exc:
                    last_exc = exc
                    logger.warning(
                        "Ollama embed API error %d (attempt %d/%d): %s",
                        exc.status_code, attempt + 1, self.MAX_RETRIES, exc,
                    )
            else:
                raise RuntimeError(
                    f"OllamaProvider.embed: batch failed after {self.MAX_RETRIES} attempts: {last_exc}"
                )

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._embed_model,
            total_tokens=total_tokens,
        )
