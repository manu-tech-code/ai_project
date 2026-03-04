"""
Application configuration using pydantic-settings v2.

All settings are loaded from environment variables (or .env file).
See docs/tech-spec.md section 12 for the full environment variable reference.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "ALM Platform"
    app_version: str = "0.2.0"
    ALM_ENV: str = "development"
    env: str = "development"  # alias used in spec
    LOG_LEVEL: str = "INFO"
    debug: bool = False
    SECRET_KEY: str = "changeme-replace-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://alm:alm@localhost:5432/alm"
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/alm"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_POOL_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    redis_url: str = "redis://localhost:6379/0"

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://alm:alm@localhost:5672/"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # LLM
    llm_provider: str = "anthropic"  # anthropic | openai
    ANTHROPIC_API_KEY: str = ""
    anthropic_api_key: str = ""
    OPENAI_API_KEY: str = ""
    openai_api_key: str = ""
    llm_model: str = "claude-opus-4-6"
    llm_max_tokens: int = 4096

    # Java parser service
    JAVA_PARSER_URL: str = "http://localhost:8080"
    java_parser_url: str = "http://localhost:8090/parse"
    java_parser_timeout: int = 60

    # Security
    api_key_header: str = "X-API-Key"

    # Vector DB / Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Upload limits
    MAX_UPLOAD_SIZE_MB: int = 500

    # Pipeline
    SANDBOX_TIMEOUT_SECONDS: int = 30
    MAX_CONCURRENT_JOBS: int = 10

    def get_effective_db_url(self) -> str:
        """Return the database URL to use, preferring DATABASE_URL env var."""
        return self.DATABASE_URL

    def get_effective_redis_url(self) -> str:
        """Return the Redis URL to use."""
        return self.REDIS_URL

    def get_effective_rabbitmq_url(self) -> str:
        """Return the RabbitMQ URL to use."""
        return self.RABBITMQ_URL

    def get_effective_anthropic_key(self) -> str:
        """Return the Anthropic API key, preferring ANTHROPIC_API_KEY env var."""
        return self.ANTHROPIC_API_KEY or self.anthropic_api_key

    def get_effective_openai_key(self) -> str:
        """Return the OpenAI API key, preferring OPENAI_API_KEY env var."""
        return self.OPENAI_API_KEY or self.openai_api_key

    def is_development(self) -> bool:
        return self.ALM_ENV.lower() in ("development", "dev", "local")


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Re-used across the application lifecycle."""
    return Settings()


# Module-level singleton for backwards compatibility with existing imports.
settings = get_settings()
