"""
Unit tests for app.services.llm.base (StubProvider, get_llm_provider).

No real API calls are made. Provider selection is tested via mocked settings.
"""

import pytest
from unittest.mock import MagicMock

from app.services.llm.base import (
    CompletionResult,
    EmbeddingResult,
    LLMProvider,
    StubProvider,
    get_llm_provider,
)


# ---------------------------------------------------------------------------
# StubProvider — complete()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stub_provider_complete_returns_completion_result():
    provider = StubProvider()
    result = await provider.complete(system="sys", user="user prompt")

    assert isinstance(result, CompletionResult)
    assert result is not None


@pytest.mark.asyncio
async def test_stub_provider_complete_content_is_string():
    provider = StubProvider()
    result = await provider.complete(system="sys", user="hello")

    assert isinstance(result.content, str)
    assert len(result.content) > 0


@pytest.mark.asyncio
async def test_stub_provider_complete_model_is_stub():
    provider = StubProvider()
    result = await provider.complete(system="sys", user="test")

    assert result.model == "stub"


@pytest.mark.asyncio
async def test_stub_provider_complete_token_counts_are_zero():
    provider = StubProvider()
    result = await provider.complete(system="sys", user="prompt")

    assert result.input_tokens == 0
    assert result.output_tokens == 0


@pytest.mark.asyncio
async def test_stub_provider_complete_stop_reason_is_stub():
    provider = StubProvider()
    result = await provider.complete(system="sys", user="test")

    assert result.stop_reason == "stub"


@pytest.mark.asyncio
async def test_stub_provider_complete_includes_user_preview():
    """The stub content should include a preview of the user message."""
    provider = StubProvider()
    result = await provider.complete(system="sys", user="analyze this code snippet")

    assert "analyze this code snippet" in result.content or "Would process" in result.content


# ---------------------------------------------------------------------------
# StubProvider — embed()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stub_provider_embed_returns_embedding_result():
    provider = StubProvider()
    result = await provider.embed(["text 1", "text 2"])

    assert isinstance(result, EmbeddingResult)


@pytest.mark.asyncio
async def test_stub_provider_embed_returns_correct_count():
    provider = StubProvider()
    result = await provider.embed(["a", "b", "c"])

    assert len(result.embeddings) == 3


@pytest.mark.asyncio
async def test_stub_provider_embed_each_vector_is_1536_dim():
    provider = StubProvider()
    result = await provider.embed(["test text"])

    assert len(result.embeddings[0]) == 1536


@pytest.mark.asyncio
async def test_stub_provider_embed_vectors_are_zero():
    provider = StubProvider()
    result = await provider.embed(["zero vector"])

    assert all(v == 0.0 for v in result.embeddings[0])


@pytest.mark.asyncio
async def test_stub_provider_embed_model_is_stub():
    provider = StubProvider()
    result = await provider.embed(["text"])

    assert result.model == "stub"


@pytest.mark.asyncio
async def test_stub_provider_embed_empty_list():
    provider = StubProvider()
    result = await provider.embed([])

    assert result.embeddings == []
    assert result.total_tokens == 0


# ---------------------------------------------------------------------------
# StubProvider — is_a LLMProvider
# ---------------------------------------------------------------------------


def test_stub_provider_is_llm_provider():
    provider = StubProvider()
    assert isinstance(provider, LLMProvider)


# ---------------------------------------------------------------------------
# get_llm_provider factory
# ---------------------------------------------------------------------------


def test_get_llm_provider_returns_stub_when_no_keys():
    settings = MagicMock()
    settings.llm_provider = "anthropic"
    settings.ANTHROPIC_API_KEY = ""
    settings.anthropic_api_key = ""
    settings.OPENAI_API_KEY = ""
    settings.openai_api_key = ""
    settings.get_effective_anthropic_key = lambda: ""
    settings.get_effective_openai_key = lambda: ""

    provider = get_llm_provider(settings)

    assert isinstance(provider, StubProvider)


def test_get_llm_provider_returns_stub_when_anthropic_key_empty_and_openai_empty():
    settings = MagicMock()
    settings.llm_provider = "openai"
    settings.ANTHROPIC_API_KEY = ""
    settings.anthropic_api_key = ""
    settings.OPENAI_API_KEY = ""
    settings.openai_api_key = ""
    settings.get_effective_anthropic_key = lambda: ""
    settings.get_effective_openai_key = lambda: ""

    provider = get_llm_provider(settings)
    assert isinstance(provider, StubProvider)


def test_get_llm_provider_returns_anthropic_when_key_set():
    """When an Anthropic key is present, AnthropicProvider should be returned."""
    settings = MagicMock()
    settings.llm_provider = "anthropic"
    settings.ANTHROPIC_API_KEY = "sk-ant-test123"
    settings.anthropic_api_key = "sk-ant-test123"
    settings.OPENAI_API_KEY = ""
    settings.openai_api_key = ""
    settings.get_effective_anthropic_key = lambda: "sk-ant-test123"
    settings.get_effective_openai_key = lambda: ""

    try:
        from app.services.llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415
        provider = get_llm_provider(settings)
        assert isinstance(provider, AnthropicProvider)
    except ImportError:
        pytest.skip("AnthropicProvider not available in test environment")


def test_get_llm_provider_returns_openai_when_pref_openai_and_key_set():
    """When OpenAI is preferred and key exists, OpenAIProvider should be returned."""
    settings = MagicMock()
    settings.llm_provider = "openai"
    settings.ANTHROPIC_API_KEY = ""
    settings.anthropic_api_key = ""
    settings.OPENAI_API_KEY = "sk-openai-test123"
    settings.openai_api_key = "sk-openai-test123"
    settings.get_effective_anthropic_key = lambda: ""
    settings.get_effective_openai_key = lambda: "sk-openai-test123"

    try:
        from app.services.llm.openai_provider import OpenAIProvider  # noqa: PLC0415
        provider = get_llm_provider(settings)
        assert isinstance(provider, OpenAIProvider)
    except ImportError:
        pytest.skip("OpenAIProvider not available in test environment")


# ---------------------------------------------------------------------------
# CompletionResult / EmbeddingResult dataclasses
# ---------------------------------------------------------------------------


def test_completion_result_fields():
    result = CompletionResult(
        content="test",
        model="claude-3-5-sonnet",
        input_tokens=100,
        output_tokens=50,
        stop_reason="end_turn",
    )
    assert result.content == "test"
    assert result.model == "claude-3-5-sonnet"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.stop_reason == "end_turn"


def test_embedding_result_fields():
    vectors = [[0.1, 0.2, 0.3]]
    result = EmbeddingResult(
        embeddings=vectors,
        model="text-embedding-3-small",
        total_tokens=5,
    )
    assert result.embeddings == vectors
    assert result.model == "text-embedding-3-small"
    assert result.total_tokens == 5
