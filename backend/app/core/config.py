"""Application settings loaded from environment variables (twelve-factor, Section 5.5).

Secrets (JWT key, encryption keys, provider secrets) are only ever read from the
environment / the hosting platform's secret store and never committed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "change-me-dev-only-secret-key-at-least-32-chars"  # noqa: S105 - refused outside dev
_DEV_ENCRYPTION_KEYS = "dev1:ZGV2LW9ubHktZW5jcnlwdGlvbi1rZXktMzItYnl0ZXM="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---------------------------------------------------------------
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_public_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # --- Security --------------------------------------------------------------
    secret_key: str = Field(default=_DEV_SECRET, min_length=32)
    encryption_keys: str = _DEV_ENCRYPTION_KEYS
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 14
    email_token_ttl_hours: int = 48
    password_reset_ttl_minutes: int = 30  # REQ-AC-6
    invitation_ttl_days: int = 7
    max_failed_logins: int = 5  # REQ-AC-2
    lockout_minutes: int = 15  # REQ-AC-2
    login_rate_limit_per_minute: int = 20  # SEC-7 (per IP)

    # --- Data services -----------------------------------------------------------
    database_url: str = "sqlite+pysqlite:///./intelliflow.sqlite3"
    database_echo: bool = False
    redis_url: str | None = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    # --- LLM ------------------------------------------------------------------------
    llm_provider: Literal["fake", "anthropic"] = "fake"
    llm_model: str = "claude-opus-5-5"
    llm_timeout_seconds: float = 90.0
    llm_max_retries: int = 2
    default_ai_credit_limit: int = 2000  # AI calls per workspace per month (BR-6)

    # --- Product rules ------------------------------------------------------------
    interview_max_questions: int = 12  # REQ-FM-2
    default_approval_threshold: int = 10_000  # BR-5 (PKR)
    approval_reminder_minutes: int = 120  # REQ-AP-5
    approval_timeout_minutes: int = 1440  # REQ-AP-5
    automation_failure_threshold: int = 5  # REQ-WE-7
    messages_per_hour_limit: int = 100  # SAF-4
    auto_send_min_clean_approvals: int = 20  # SAF-1
    webhook_dedupe_ttl_seconds: int = 24 * 3600  # Algorithm 5.4

    # --- WhatsApp Cloud API ------------------------------------------------------------
    whatsapp_app_secret: str = "dev-whatsapp-app-secret"  # noqa: S105 - refused outside dev
    whatsapp_verify_token: str = "dev-verify-token"  # noqa: S105 - dev default
    whatsapp_graph_api_version: str = "v23.0"
    whatsapp_graph_base_url: str = "https://graph.facebook.com"

    # --- Google OAuth ------------------------------------------------------------------
    google_client_id: str | None = None
    google_client_secret: str | None = None

    # --- Notifications -------------------------------------------------------------------
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "IntelliFlow <no-reply@intelliflow.local>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@intelliflow.local"

    # --- Observability -----------------------------------------------------------------
    sentry_dsn: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_dev_like(self) -> bool:
        return self.environment in {"development", "test"}

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def web_push_enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)

    @model_validator(mode="after")
    def _refuse_dev_secrets_outside_dev(self) -> Settings:
        if self.environment in {"staging", "production"}:
            if self.secret_key == _DEV_SECRET or self.encryption_keys == _DEV_ENCRYPTION_KEYS:
                raise ValueError(
                    "Refusing to start: development secrets are configured in a "
                    f"{self.environment} environment. Set SECRET_KEY and ENCRYPTION_KEYS."
                )
            if self.whatsapp_app_secret == "dev-whatsapp-app-secret":  # noqa: S105
                raise ValueError("Refusing to start: set WHATSAPP_APP_SECRET.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that patch the environment."""
    get_settings.cache_clear()
