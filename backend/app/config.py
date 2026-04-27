from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_secret_key: str = "change-me-in-production"
    debug: bool = False
    allowed_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"

    # Database
    # For local dev: set POSTGRES_* vars and leave POSTGRES_DSN blank.
    # For managed Postgres (e.g. Neon): set POSTGRES_DSN to the full connection string;
    # the individual POSTGRES_* vars are ignored.
    postgres_dsn: str = ""
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "weaving_site"
    postgres_user: str = "weaving_user"
    postgres_password: str = ""

    @property
    def database_url(self) -> str:
        if self.postgres_dsn:
            url = self.postgres_dsn.replace("postgres://", "postgresql://", 1)
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
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

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # OIDC — primary provider (Google or any single OIDC endpoint)
    oidc_discovery_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:3000/auth/callback"

    # Apple Sign In (optional second provider)
    # client_secret must be a pre-generated ES256 JWT (valid up to 6 months).
    # Generate with: https://developer.apple.com/documentation/sign_in_with_apple/generate_and_validate_tokens
    oidc_apple_client_id: str = ""
    oidc_apple_client_secret: str = ""
    oidc_apple_redirect_uri: str = "http://localhost:3000/auth/callback"

    @property
    def active_providers(self) -> dict[str, dict[str, str]]:
        """Returns configured OIDC providers keyed by provider name."""
        providers: dict[str, dict[str, str]] = {}
        if self.oidc_discovery_url and self.oidc_client_id:
            providers["google"] = {
                "discovery_url": self.oidc_discovery_url,
                "client_id": self.oidc_client_id,
                "client_secret": self.oidc_client_secret,
                "redirect_uri": self.oidc_redirect_uri,
            }
        if self.oidc_apple_client_id:
            providers["apple"] = {
                "discovery_url": "https://appleid.apple.com",
                "client_id": self.oidc_apple_client_id,
                "client_secret": self.oidc_apple_client_secret,
                "redirect_uri": self.oidc_apple_redirect_uri,
            }
        return providers

    # SMTP (SMTP2Go)
    smtp_host: str = "mail.smtp2go.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "WeftMark"

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
