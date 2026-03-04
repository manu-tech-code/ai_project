"""
Unit tests for app.core.config.Settings.

Tests verify default values, env-var overrides, and helper methods.
No external services required.
"""

import pytest

from app.core.config import Settings


# ---------------------------------------------------------------------------
# Default settings
# ---------------------------------------------------------------------------


def test_default_env_is_development():
    s = Settings()
    assert s.env == "development"


def test_default_llm_provider_is_anthropic():
    s = Settings()
    assert s.llm_provider == "anthropic"


def test_default_postgres_url_contains_port():
    """The default postgres_url must reference port 5432."""
    s = Settings()
    assert "5432" in s.postgres_url


def test_default_debug_is_false():
    s = Settings()
    assert s.debug is False


def test_default_max_upload_size():
    s = Settings()
    assert s.MAX_UPLOAD_SIZE_MB == 500


def test_default_sandbox_timeout():
    s = Settings()
    assert s.SANDBOX_TIMEOUT_SECONDS == 30


def test_default_max_concurrent_jobs():
    s = Settings()
    assert s.MAX_CONCURRENT_JOBS == 10


def test_default_embedding_dimensions():
    s = Settings()
    assert s.embedding_dimensions == 1536


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    s = Settings()
    assert s.env == "production"


def test_settings_alm_env_override(monkeypatch):
    monkeypatch.setenv("ALM_ENV", "staging")
    s = Settings()
    assert s.ALM_ENV == "staging"


def test_settings_debug_false_from_env(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    s = Settings()
    assert s.debug is False


def test_settings_debug_true_from_env(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    s = Settings()
    assert s.debug is True


def test_settings_log_level_override(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.LOG_LEVEL == "DEBUG"


# ---------------------------------------------------------------------------
# is_development() helper
# ---------------------------------------------------------------------------


def test_is_development_returns_true_by_default():
    s = Settings()
    assert s.is_development() is True


def test_is_development_false_for_production(monkeypatch):
    monkeypatch.setenv("ALM_ENV", "production")
    s = Settings()
    assert s.is_development() is False


def test_is_development_true_for_dev_alias(monkeypatch):
    monkeypatch.setenv("ALM_ENV", "dev")
    s = Settings()
    assert s.is_development() is True


def test_is_development_true_for_local(monkeypatch):
    monkeypatch.setenv("ALM_ENV", "local")
    s = Settings()
    assert s.is_development() is True


def test_is_development_false_for_staging(monkeypatch):
    monkeypatch.setenv("ALM_ENV", "staging")
    s = Settings()
    assert s.is_development() is False


# ---------------------------------------------------------------------------
# Effective URL helpers
# ---------------------------------------------------------------------------


def test_get_effective_db_url_returns_database_url():
    s = Settings()
    assert s.get_effective_db_url() == s.DATABASE_URL


def test_get_effective_redis_url_returns_redis_url():
    s = Settings()
    assert s.get_effective_redis_url() == s.REDIS_URL


def test_get_effective_rabbitmq_url_returns_rabbitmq_url():
    s = Settings()
    assert s.get_effective_rabbitmq_url() == s.RABBITMQ_URL


def test_get_effective_anthropic_key_prefers_uppercase(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-upper")
    s = Settings()
    # Pydantic-settings maps env vars case-insensitively; key should be non-empty
    assert s.get_effective_anthropic_key() in ("sk-ant-upper", "sk-ant-lower")


def test_get_effective_openai_key_prefers_uppercase(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-upper")
    s = Settings()
    assert s.get_effective_openai_key() == "sk-openai-upper"
