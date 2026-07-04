from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), env_file_encoding="utf-8", extra="ignore")

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

    # Optional "LLM Council" answer mode. When enabled, Ask fans out to
    # multiple OpenAI-compatible models, then asks a chair model to synthesize.
    # This is disabled unless models and an API key are configured.
    llm_council_enabled: bool = False
    llm_council_models: str = ""
    llm_council_chair_model: str = ""
    llm_council_api_key: str = ""
    llm_council_base_url: str = ""
    llm_council_available_models: str = ""
    llm_council_max_models: int = 3
    llm_council_timeout_seconds: float = 120.0

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
    rate_limit_per_minute: int = 300

    # caching
    response_cache_ttl_seconds: int = 300

    # observability
    otel_exporter_otlp_endpoint: str = ""

    # storage
    upload_dir: str = "var/uploads"

    # Confluence Cloud source sync. This integration is intentionally read-only:
    # the backend only calls GET endpoints and writes synced content locally.
    confluence_base_url: str = ""
    confluence_space_key: str = "DevOps1"
    confluence_api_token: str = ""
    confluence_email: str = ""
    confluence_auth_mode: str = "auto"  # auto | basic | bearer
    confluence_default_kb_name: str = "Confluence DevOps1"
    confluence_page_limit: int = 100  # API page size, Atlassian Cloud caps this at 100
    confluence_sync_max_pages: int = 0  # 0 means sync every visible page
    confluence_request_timeout_seconds: float = 20.0

    # Jira Software Cloud source sync. Also read-only: GET board/project/issue
    # endpoints only, then local document indexing.
    jira_base_url: str = ""
    jira_project_key: str = ""
    jira_board_id: int = 0
    jira_api_token: str = ""
    jira_email: str = ""
    jira_auth_mode: str = "auto"  # auto | basic | bearer
    jira_default_kb_name: str = "Jira"
    jira_issue_limit: int = 100  # API page size, Atlassian Cloud caps this at 100
    jira_sync_max_issues: int = 0  # 0 means sync every visible issue on the board/project
    jira_request_timeout_seconds: float = 20.0

    # Optional web search for Ask. Disabled by default so the app never fabricates
    # internet results when no real provider is configured.
    web_search_provider: str = "disabled"  # disabled | duckduckgo | brave | tavily | searxng | fake
    web_search_api_key: str = ""
    web_search_base_url: str = ""
    web_search_default_kb_name: str = "Web Search"
    web_search_top_k: int = 5
    web_search_request_timeout_seconds: float = 10.0

    # Discover keeps departments updated with live external news/research plus
    # local Jira/Confluence board pulse. Google News RSS needs no key; Brave,
    # Tavily, and SearXNG use the same shapes as web search.
    discover_enabled: bool = True
    discover_provider: str = "google_news_rss"  # google_news_rss | duckduckgo | brave | tavily | searxng | fake
    discover_api_key: str = ""
    discover_base_url: str = ""
    discover_locale: str = "en-IN"
    discover_region: str = "IN"
    discover_cache_ttl_seconds: int = 900
    discover_items_per_department: int = 8
    discover_department_queries: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
