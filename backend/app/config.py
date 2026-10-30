from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://career:career@localhost:5432/career_intel"
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_hours: int = 72
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Comma-separated emails that become admins on sign-up (can import postings, reindex).
    admin_emails: str = ""

    # AI providers. Without keys the app runs in offline mode:
    # keyword tag extraction, hashing embeddings, extractive answers.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"  # Ask and research
    # Model per job. "critical" = checker and analyst; falls back when the account cannot use it.
    model_bulk: str = "claude-haiku-5-5"
    model_critical: str = "claude-fable-5-1"
    model_critical_fallback: str = "claude-opus-5-5"
    # API spending cap: the agents stop when this month's spend reaches allowance x share.
    api_monthly_allowance_usd: float = 20.0
    budget_share: float = 0.5
    # Agent team
    inbox_dir: str = "/data/inbox"
    agents_enabled: bool = True
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3.5"
    embedding_dim: int = 1024
    # Rough token budget per Voyage request; keep low for accounts with small rate limits.
    voyage_max_batch_tokens: int = 8000

    rag_top_k: int = 8

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def monthly_cap_usd(self) -> float:
        return round(self.api_monthly_allowance_usd * self.budget_share, 2)

    @property
    def embedding_model_name(self) -> str:
        return self.voyage_model if self.voyage_api_key else "local-hash-v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
