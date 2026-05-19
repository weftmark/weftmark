from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_env: str = "dev"
    app_name: str = "weftmark"
    seed_enabled: bool = False
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    frontend_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    app_base_url: str = ""  # public-facing URL for alert email links; falls back to frontend_url when empty
    stack_alert_emails_enabled: bool = True  # set false in dev to suppress startup/shutdown alert emails
    email_ttl_hours: int = 6  # discard queued emails older than this
    email_staleness_warning_minutes: int = 60  # inject staleness banner after this many minutes in queue

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

    # OpenTelemetry — set to the OTLP HTTP collector base URL to enable (e.g. http://otel-collector:4318)
    # Leave empty (default) to disable telemetry; SDK no-ops gracefully in local dev.
    # OTEL_SERVICE_NAME is read natively by the SDK from the environment variable.
    otel_exporter_otlp_endpoint: str = ""

    # GeoIP (MaxMind GeoLite2-City) — leave license key empty to disable geo lookups
    maxmind_license_key: str = ""
    geoip_db_path: str = "/app/data/GeoLite2-City.mmdb"

    # GitHub Discussions feedback integration (optional — issue #34)
    # PAT with write:discussion + read:discussion scopes on the target repo.
    # Leave empty to store feedback locally only; no error surfaced to users.
    github_feedback_token: str = ""
    github_feedback_repo: str = "weftmark/weftmark"

    # Feedback rate limiting
    feedback_rate_limit_per_hour: int = 5

    # Data retention
    soft_delete_retention_days: int = 365

    # Rendering
    render_max_width: int = 4000
    render_max_height: int = 4000
    render_default_zoom: int = 10
    drawdown_preview_max_px: int = 800
    tile_row_count: int = 100
    tile_col_count: int = 200
    tile_prune_inactive_days: int = 10

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level(cls, v: object) -> str:
        _VALID = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        s = str(v).upper().strip()
        if s not in _VALID:
            raise ValueError(f"LOG_LEVEL {v!r} is invalid. Must be one of: {', '.join(sorted(_VALID))}")
        return s

    @field_validator("storage_backend", mode="before")
    @classmethod
    def _validate_storage_backend(cls, v: object) -> str:
        s = str(v).lower().strip()
        if s not in ("local", "s3"):
            raise ValueError(f"STORAGE_BACKEND {v!r} is invalid. Must be 'local' or 's3'.")
        return s

    def config_warnings(self) -> list[str]:
        """Return human-readable warnings for non-fatal configuration issues.

        Surfaced via /health/ready through _probe_config(). Does not raise —
        callers decide severity.
        """
        issues: list[str] = []

        # S3 credentials must all be set together when STORAGE_BACKEND=s3
        if self.storage_backend == "s3":
            missing = [
                k
                for k, v in {
                    "S3_ENDPOINT_URL": self.s3_endpoint_url,
                    "S3_ACCESS_KEY_ID": self.s3_access_key_id,
                    "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key,
                    "S3_BUCKET_NAME": self.s3_bucket_name,
                }.items()
                if not v
            ]
            if missing:
                issues.append(f"STORAGE_BACKEND=s3 but the following vars are not set: {', '.join(missing)}")

        # CORS origins must be comma-separated without spaces
        if " " in self.cors_origins:
            issues.append(
                "CORS_ORIGINS contains spaces — values must be comma-separated with no spaces "
                "(e.g. http://a.com,http://b.com)"
            )

        # Webhook secret required for Clerk user-sync
        if not self.clerk_webhook_secret or not self.clerk_webhook_secret.startswith("whsec_"):
            issues.append(
                "CLERK_WEBHOOK_SECRET is not set or does not start with 'whsec_' — "
                "user-sync webhooks (user.created / user.deleted) will not function"
            )

        return issues


@lru_cache
def get_settings() -> Settings:
    return Settings()
