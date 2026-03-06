"""
LLMProvider — abstract base class for LLM provider implementations.

All LLM calls in the agent pipeline go through this interface.
Concrete implementations: AnthropicProvider, OpenAIProvider, StubProvider.

Usage pattern:
    provider = AnthropicProvider()
    response = await provider.complete(
        system="You are an expert code reviewer.",
        user="<task>Identify god classes</task><context>...</context>",
        temperature=0.2,
        max_tokens=4096,
    )
    embeddings = await provider.embed(["class UserService { ... }"])
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CompletionResult:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


@dataclass
class EmbeddingResult:
    embeddings: list[list[float]]  # shape: [n_texts, 1536]
    model: str
    total_tokens: int


class LLMProvider(ABC):
    """
    Abstract LLM provider interface.

    Subclasses must implement `complete()` and `embed()`.
    Both methods handle rate limiting and retry internally.
    """

    @abstractmethod
    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        """
        Send a completion request to the LLM.

        Args:
            system: System prompt establishing context and output format.
            user: User message with task and context.
            temperature: Sampling temperature (0.0–1.0).
            max_tokens: Maximum output tokens.
            tools: Optional tool definitions for structured output.

        Returns:
            CompletionResult with content, token counts, and model used.
        """

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """
        Generate embeddings for a list of text strings.

        Args:
            texts: List of text strings to embed (max 100 per call).

        Returns:
            EmbeddingResult with 1536-dimensional vectors for each input.
        """


class StubProvider(LLMProvider):
    """
    No-op LLM provider used when no API keys are configured.
    Returns deterministic placeholder content and zero-vectors.
    """

    MODEL_NAME = "stub"

    async def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        preview = user[:120].replace("\n", " ")
        return CompletionResult(
            content=f"[LLM not configured] Would process: {preview}...",
            model=self.MODEL_NAME,
            input_tokens=0,
            output_tokens=0,
            stop_reason="stub",
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            embeddings=[[0.0] * 1536 for _ in texts],
            model=self.MODEL_NAME,
            total_tokens=0,
        )


# Runtime overrides — updated via PATCH /api/v1/settings/llm without restart.
_runtime_llm_override: dict = {}


def get_llm_provider(settings) -> LLMProvider:
    """
    Factory: returns the configured LLM provider based on settings.
    Falls back to StubProvider if no valid API key is found.
    Runtime overrides in _runtime_llm_override take precedence over config.
    """
    anthropic_key = (
        settings.get_effective_anthropic_key() if hasattr(settings, "get_effective_anthropic_key")
        else (settings.ANTHROPIC_API_KEY or "")
    )
    openai_key = (
        settings.get_effective_openai_key() if hasattr(settings, "get_effective_openai_key")
        else (settings.OPENAI_API_KEY or "")
    )
    provider_pref = _runtime_llm_override.get("provider") or getattr(settings, "llm_provider", "anthropic")

    if provider_pref == "ollama":
        from app.services.llm.ollama_provider import OllamaProvider
        provider = OllamaProvider()
        if "model" in _runtime_llm_override:
            provider._model = _runtime_llm_override["model"]
        return provider
    elif provider_pref == "anthropic" and anthropic_key:
        from app.services.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    elif openai_key:
        from app.services.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    else:
        return StubProvider()
