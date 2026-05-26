"""Persistent encrypted config file service.

Stores optional integration settings in a JSON file on a mounted volume.
Secret fields are Fernet-encrypted using CONFIG_ENCRYPTION_KEY from .env.
Non-secret fields are stored as plain JSON values.

Priority on startup: env vars > config file values > hardcoded defaults.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Fields whose values are Fernet-encrypted at rest.
SECRET_FIELDS = frozenset(
    {
        "smtp_password",
        "s3_secret_access_key",
        "cf_access_client_secret",
        "ravelry_read_access_key",
        "ravelry_oauth_client_secret",
        "github_feedback_token",
        "clerk_webhook_secret",
        "maxmind_license_key",
    }
)

# Fields managed by this service (all optional integrations).
# Ordered for display grouping — order within each group matters for the UI.
MANAGED_FIELDS: list[str] = [
    # SMTP
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "smtp_from_email",
    "smtp_from_name",
    # S3 / R2
    "s3_endpoint_url",
    "s3_access_key_id",
    "s3_secret_access_key",
    "s3_bucket_name",
    "s3_region",
    # Ravelry — read key
    "ravelry_read_access_username",
    "ravelry_read_access_key",
    # Ravelry — OAuth
    "ravelry_oauth_client_id",
    "ravelry_oauth_client_secret",
    "ravelry_oauth_redirect_uri",
    # GitHub feedback
    "github_feedback_token",
    "github_feedback_repo",
    # Cloudflare Zero Trust
    "cf_zero_trust_enabled",
    "cf_access_client_id",
    "cf_access_client_secret",
    # Clerk webhook
    "clerk_webhook_secret",
    "webhook_base_url",
    # GeoIP
    "maxmind_license_key",
    # Observability
    "otel_exporter_otlp_endpoint",
]


def _fernet(key: str):
    from cryptography.fernet import Fernet

    raw = key.encode() if isinstance(key, str) else key
    return Fernet(raw)


def encrypt(value: str, key: str) -> str:
    return _fernet(key).encrypt(value.encode()).decode()  # type: ignore[no-any-return]


def decrypt(token: str, key: str) -> str:
    return _fernet(key).decrypt(token.encode()).decode()  # type: ignore[no-any-return]


def _get_allowed_root() -> Path:
    """Return the trusted directory for config file I/O.

    Derived from CONFIG_FILE_PATH env var (same source as settings.config_file_path)
    so the root is always stable and independent of any argument passed at call time.
    Falls back to /data, the standard container mount point.
    """
    configured = os.environ.get("CONFIG_FILE_PATH", "")
    return Path(configured).resolve().parent if configured else Path("/data")


def _assert_safe_path(path: str) -> Path:
    """Resolve *path* and raise ValueError if it escapes the allowed root."""
    resolved = Path(path).resolve()
    allowed_root = _get_allowed_root()
    if not resolved.is_relative_to(allowed_root):
        raise ValueError(f"Config path outside allowed root '{allowed_root}': {resolved}")
    return resolved


def load(path: str, encryption_key: str) -> dict[str, Any]:  # NOSONAR: path validated by _assert_safe_path
    """Load config file, decrypting secret fields. Returns {} if file absent/corrupt."""
    p = _assert_safe_path(path)
    if not p.exists():
        return {}
    try:
        raw: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.warning("config_file_load_failed path=%s — file corrupt or unreadable", path)
        return {}

    result: dict[str, Any] = {}
    for k, v in raw.items():
        if k in SECRET_FIELDS and isinstance(v, str) and v:
            try:
                result[k] = decrypt(v, encryption_key)
            except Exception:
                log.warning("config_file_decrypt_failed field=%s — skipping", k)
        else:
            result[k] = v
    return result


def save(  # NOSONAR: path validated by _assert_safe_path
    path: str, encryption_key: str, values: dict[str, Any]
) -> None:
    """Merge values into the config file, encrypting secret fields."""
    p = _assert_safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Load existing to merge (don't wipe fields we're not touching)
    try:
        existing: dict[str, Any] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        existing = {}

    for k, v in values.items():
        if v is None or v == "":
            existing.pop(k, None)
        elif k in SECRET_FIELDS and isinstance(v, str):
            existing[k] = encrypt(v, encryption_key)
        else:
            existing[k] = v

    p.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    log.info("config_file_saved path=%s fields=%s", path, list(values.keys()))


def env_source_fields() -> dict[str, str]:
    """Return the subset of MANAGED_FIELDS that are currently set as env vars.

    Maps field name → env var name (upper-cased). Used to show badges in the UI
    and to write env var values back to the config file on startup.
    """
    result: dict[str, str] = {}
    for field in MANAGED_FIELDS:
        env_name = field.upper()
        if os.environ.get(env_name) is not None:
            result[field] = env_name
    return result


def sync_env_to_file(path: str, encryption_key: str) -> None:
    """On startup: write any env var values into the config file so they stay in sync."""
    env_fields = env_source_fields()
    if not env_fields:
        return
    values = {field: os.environ[env_name] for field, env_name in env_fields.items()}
    save(path, encryption_key, values)
    log.info("config_file_env_sync synced=%d fields", len(values))
