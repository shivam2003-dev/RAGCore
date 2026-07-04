from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # app
    app_env: str = "local"
    app_debug: bool = False
    app_secret_key: str = "dev-secret-change-me"  # noqa: S105 — overridden via env
    app_name: str = "kimbal-backend"

    # database
    database_url: str = "postgresql+asyncpg://kimbal:kimbal_dev_password@localhost:5433/kimbal"
    database_url_test: str = "postgresql+asyncpg://kimbal:kimbal_dev_password@localhost:5433/kimbal_test"
    database_pool_size: int = 10
    database_max_overflow: int = 10

    # redis
    redis_url: str = "redis://localhost:6379/0"

    # auth
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 1_209_600

    # embeddings
    embedding_provider: str = "fake"  # openai | jina | voyage | tei | fake
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_base_url: str = ""  # for tei/self-hosted OpenAI-compatible servers
    embedding_cache_ttl_seconds: int = 604_800
    openai_api_key: str = ""
    jina_api_key: str = ""
    voyage_api_key: str = ""

    # llm
    llm_provider: str = "fake"  # anthropic | openai | openrouter | fake
    llm_model: str = "claude-sonnet-5"
    llm_base_url: str = ""  # override for OpenAI-compatible gateways (OpenRouter etc.)
    llm_max_output_tokens: int = 1024
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

    # retrieval
    retrieval_top_k: int = 8
    retrieval_candidate_k: int = 24  # per-arm candidates before fusion
    retrieval_dense_weight: float = 0.7
    retrieval_sparse_weight: float = 0.3

    # chunking
    chunk_size_tokens: int = 400
    chunk_overlap_tokens: int = 60

    # limits
    upload_max_bytes: int = 52_428_800
    rate_limit_per_minute: int = 60

    # caching
    response_cache_ttl_seconds: int = 300

    # observability
    otel_exporter_otlp_endpoint: str = ""

    # storage
    upload_dir: str = "var/uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
