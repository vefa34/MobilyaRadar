"""Application configuration. Everything is driven by environment variables (see .env.example)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Global Furniture Buyer Intelligence"
    environment: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://fbi:fbi@localhost:5432/fbi"
    redis_url: str = "redis://localhost:6379/0"
    # "celery" dispatches research jobs to the Celery worker, "thread" runs them in-process (dev/tests).
    task_backend: str = "thread"

    secret_key: str = "change-me-in-production-please-32b"
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt connector credentials at rest.
    credentials_encryption_key: str | None = None
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000"

    # Demo mode enables the synthetic MockConnector. Synthetic records are always flagged
    # is_synthetic=True and are excluded from exports unless explicitly requested.
    demo_mode: bool = True

    # Exporter profile used for market/logistics fit (ISO-2).
    exporter_origin_country: str = "TR"

    # --- Licensed / official data provider keys (all optional). Keys can also be stored
    # per-organisation (encrypted) through the Source Manager UI.
    brave_search_api_key: str | None = None
    serpapi_api_key: str | None = None
    google_places_api_key: str | None = None
    companies_house_api_key: str | None = None
    hunter_api_key: str | None = None
    apollo_api_key: str | None = None
    # Overpass endpoint. The public instance is only acceptable for low-volume use; set a
    # self-hosted or commercial endpoint for production volumes.
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_public_max_queries_per_job: int = 25

    # --- LLM (provider-agnostic). provider: none | anthropic | openai
    llm_provider: str = "none"
    llm_model: str = "claude-opus-5-5"
    llm_fallback_model: str | None = "claude-sonnet-5-5"
    llm_effort: str = "low"  # term expansion/classification are simple structured tasks
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Website enrichment
    http_user_agent: str = "GlobalBuyerIntelBot/0.1 (+https://example.com/bot; B2B research)"
    website_max_pages: int = 4
    website_timeout_s: float = 12.0

    # Pipeline tuning
    saturation_window: int = 4           # last N queries per (country, source) inspected
    saturation_min_new_ratio: float = 0.08  # below this new-unique ratio the cell is considered saturated
    max_pages_per_query: int = 3

    bootstrap_admin_email: str | None = Field(default=None)
    bootstrap_admin_password: str | None = Field(default=None)


@lru_cache
def get_settings() -> Settings:
    return Settings()
