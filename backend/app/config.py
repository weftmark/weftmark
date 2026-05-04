from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_secret_key: str = "change-me-in-production"
    app_env: str = "dev"
    app_name: str = "WeftMark"
    seed_enabled: bool = False
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"

    # Database
    # For local dev: set POSTGRES_* vars and leave POSTGRES_DSN blank.
    # For managed Postgres (e.g. Neon):
    #   POSTGRES_DSN        — pooled connection string (app traffic)
    #   POSTGRES_DSN_DIRECT — direct connection string (Alembic migrations only)
    # If POSTGRES_DSN_DIRECT is blank, Alembic falls back to POSTGRES_DSN.
    postgres_dsn: str = ""
    postgres_dsn_direct: str = ""
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "weaving_site"
    postgres_user: str = "weaving_user"
    postgres_password: str = ""

    @property
    def database_url(self) -> str:
        if self.postgres_dsn:
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

            url = self.postgres_dsn.replace("postgres://", "postgresql://", 1)
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            # asyncpg uses ssl=true/require, not libpq's sslmode=; drop channel_binding entirely
            parsed = urlparse(url)
            params: dict[str, str] = {}
            for k, v in parse_qs(parsed.query).items():
                if k == "sslmode":
                    params["ssl"] = v[0]
                elif k != "channel_binding":
                    params[k] = v[0]
            return urlunparse(parsed._replace(query=urlencode(params)))
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        if self.postgres_dsn:
            url = self.postgres_dsn.replace("postgres://", "postgresql://", 1)
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_alembic(self) -> str:
        """Direct (non-pooled) connection for Alembic DDL migrations."""
        dsn = self.postgres_dsn_direct or self.postgres_dsn
        if dsn:
            url = dsn.replace("postgres://", "postgresql://", 1)
            return url.replace("postgresql+asyncpg://", "postgresql://", 1)
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Clerk authentication
    clerk_publishable_key: str = ""
    clerk_secret_key: str = ""
    clerk_webhook_secret: str = ""
    webhook_base_url: str = ""  # public URL reachable by Svix, e.g. https://api.example.com
    clerk_webhook_probe_timeout_s: int = 10
    cf_zero_trust_enabled: bool = False
    cf_access_client_id: str = ""
    cf_access_client_secret: str = ""

    # SMTP (SMTP2Go)
    smtp_host: str = "mail.smtp2go.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "weftmark"

    # Invites
    invite_expiry_days_default: int = 7

    # File storage
    upload_dir: str = "/app/uploads"
    max_upload_size: int = 52428800
    storage_backend: str = "local"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = ""
    s3_region: str = ""

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"

    # Rendering
    render_max_width: int = 4000
    render_max_height: int = 4000
    render_default_zoom: int = 10

    @model_validator(mode="after")
    def _require_secret_key_in_production(self) -> "Settings":
        if not self.debug and self.app_secret_key == _DEFAULT_SECRET:
            raise ValueError(
                "APP_SECRET_KEY is still the insecure default. "
                'Generate a secure value: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
