# weftmark — Configuration Reference

This document covers all optional and advanced configuration variables.
The `.env.example` at the repo root contains only the variables required to boot the stack.
Everything listed here either has a safe default or enables an optional integration.

Most of these values can be set and tested live through the **Superuser Console → Configuration** page
without editing files or restarting the server (a restart is required to apply changes — a system-wide
banner will appear until the stack is restarted).

---

## Config encryption key

The superuser console stores optional secrets in an encrypted config file on a persistent volume mount.
A single key is required to encrypt and decrypt this file. It must live in `.env` permanently — it is
the one secret that cannot be managed through the UI.

Generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add to `.env`:

```
CONFIG_ENCRYPTION_KEY=<output from above>
```

The config file is written to the path defined by `CONFIG_FILE_PATH` (default `/data/weftmark_config.json`).
Mount this path as a Docker volume so it survives container restarts:

```yaml
volumes:
  - weftmark_config:/data
```

---

## Application

| Variable | Default | Notes |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. Invalid values prevent startup. |
| `DEBUG` | `false` | Enables FastAPI `/api/docs`, `/api/redoc`, and verbose output. Never set in production. |
| `APP_BASE_URL` | *(empty)* | Public-facing URL used in alert email links. Falls back to `FRONTEND_URL` when blank. |
| `SEED_ENABLED` | `false` | Allows the CLI seed command. Dev only — never set in production. |
| `STACK_ALERT_EMAILS_ENABLED` | `true` | Set to `false` in dev/staging to suppress startup and shutdown alert emails. |
| `EMAIL_TTL_HOURS` | `6` | Discard queued emails older than this many hours. |
| `EMAIL_STALENESS_WARNING_MINUTES` | `60` | Inject a staleness banner into emails that have been queued longer than this. |
| `INVITE_EXPIRY_DAYS_DEFAULT` | `7` | Default invite link lifetime in days. Admins can override per invite. |
| `SOFT_DELETE_RETENTION_DAYS` | `365` | Days before soft-deleted records are permanently purged. |

---

## File storage

| Variable | Default | Notes |
|---|---|---|
| `STORAGE_BACKEND` | `local` | `local` (filesystem) or `s3` (S3-compatible object storage). |
| `UPLOAD_DIR` | `/app/uploads` | Local upload directory. Mount as a Docker volume for persistence. |
| `MAX_UPLOAD_SIZE` | `52428800` | Maximum upload size in bytes (default 50 MB). |

### S3 / Cloudflare R2 (required when `STORAGE_BACKEND=s3`)

All five variables must be set together. Missing any one causes `/health/ready` to report degraded,
and file uploads and downloads will fail at runtime.

| Variable | Notes |
|---|---|
| `S3_ENDPOINT_URL` | Full URL of the S3-compatible endpoint, e.g. `https://<account>.r2.cloudflarestorage.com` |
| `S3_ACCESS_KEY_ID` | R2 / S3 access key ID |
| `S3_SECRET_ACCESS_KEY` | R2 / S3 secret access key |
| `S3_BUCKET_NAME` | Target bucket name |
| `S3_REGION` | Region string. Leave blank for Cloudflare R2 (region-agnostic). |

Test: the superuser console will attempt a `HeadBucket` call against the configured endpoint and key
before saving. A failure blocks the save and shows the error response.

---

## Email — SMTP

Used for invitation emails, alert notifications, and data export links.
Missing any of the three required fields causes the SMTP probe to show `failed` on `/health/ready`.
The stack starts and users can log in — only email sending is affected.

| Variable | Default | Notes |
|---|---|---|
| `SMTP_HOST` | `mail.smtp2go.com` | SMTP server hostname. |
| `SMTP_PORT` | `587` | SMTP port. |
| `SMTP_USER` | *(empty)* | **Required.** SMTP account username. |
| `SMTP_PASSWORD` | *(empty)* | **Required.** SMTP account password. Stored encrypted in the config file. |
| `SMTP_FROM_EMAIL` | *(empty)* | **Required.** Sender address, e.g. `admin@weftmark.com`. |
| `SMTP_FROM_NAME` | `weftmark` | Display name shown in the From field. |

Test: the superuser console will send a test email to the logged-in superuser's address before saving.

---

## Authentication — Clerk webhooks

| Variable | Default | Notes |
|---|---|---|
| `CLERK_WEBHOOK_SECRET` | *(empty)* | Signing secret from Clerk Dashboard → Webhooks → your endpoint. Starts with `whsec_`. Missing or invalid causes `/health/ready` to show `degraded`; `user.created` / `user.deleted` events are rejected and user records are not synced. |
| `WEBHOOK_BASE_URL` | *(empty)* | Public URL for webhook delivery. Falls back to `API_URL`. Set when `API_URL` goes through an auth-gated proxy (e.g. Cloudflare Access) that would block the backend's outbound probe. |

### Cloudflare Zero Trust (optional)

Only relevant when the app is behind Cloudflare Access.

| Variable | Default | Notes |
|---|---|---|
| `CF_ZERO_TRUST_ENABLED` | `false` | When `true`, the webhook probe includes CF Access service token headers. |
| `CF_ACCESS_CLIENT_ID` | *(empty)* | CF Access service token client ID. |
| `CF_ACCESS_CLIENT_SECRET` | *(empty)* | CF Access service token client secret. Stored encrypted in the config file. |

---

## Ravelry integration

Enables yarn search and per-user stash sync. The stack starts and users can log in without these values — only the Ravelry features are unavailable.

### Read-only developer key (yarn/company search)

Obtain from [ravelry.com/pro/developer](https://www.ravelry.com/pro/developer) → Personal API keys.

| Variable | Notes |
|---|---|
| `RAVELRY_READ_ACCESS_USERNAME` | Developer key username, e.g. `read-abc123` |
| `RAVELRY_READ_ACCESS_KEY` | Developer key secret. Stored encrypted in the config file. |

Test: the superuser console will call `GET /yarn_weights.json` with the supplied credentials before saving.

### OAuth app credentials (per-user stash sync)

Register a Ravelry Pro app. The redirect URI must match exactly.

| Variable | Notes |
|---|---|
| `RAVELRY_OAUTH_CLIENT_ID` | OAuth app client ID |
| `RAVELRY_OAUTH_CLIENT_SECRET` | OAuth app client secret. Stored encrypted in the config file. |
| `RAVELRY_OAUTH_REDIRECT_URI` | Callback URL, e.g. `https://app.weftmark.com/api/ravelry/callback` |

---

## GitHub Discussions feedback integration

When configured, user feedback submitted in the app is posted as a GitHub Discussion.
Without it, feedback is stored locally only — no error is surfaced to users.

| Variable | Default | Notes |
|---|---|---|
| `GITHUB_FEEDBACK_TOKEN` | *(empty)* | Personal access token with `write:discussion` and `read:discussion` scopes. Stored encrypted in the config file. |
| `GITHUB_FEEDBACK_REPO` | `weftmark/weftmark` | Target repository in `owner/repo` format. |

Test: the superuser console will call the GitHub API to verify the token has the required scopes before saving.

---

## OpenTelemetry — observability

| Variable | Default | Notes |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(empty)* | Base URL of the OTLP HTTP receiver (port 4318), e.g. `http://otel-collector:4318`. Leave blank to disable — the SDK no-ops gracefully. |

When enabled, the backend, worker, and beat containers must be attached to the same Docker network
as the OTLP collector. See `docker-compose.yml` → `networks` → `observability_receiver`.

---

## GeoIP — MaxMind GeoLite2-City

When configured, client IP addresses are resolved to a city/country and included in metrics and audit logs.
Without it, geo fields are absent — no error is surfaced.

| Variable | Default | Notes |
|---|---|---|
| `MAXMIND_LICENSE_KEY` | *(empty)* | Free license key from [maxmind.com/en/geolite2/signup](https://www.maxmind.com/en/geolite2/signup). When set, the weekly refresh task downloads and updates the MMDB automatically. |
| `GEOIP_DB_PATH` | `/app/data/GeoLite2-City.mmdb` | Path to the MMDB file inside the container. |

---

## Rendering

Controls image generation for design previews and drawdowns.

| Variable | Default | Notes |
|---|---|---|
| `RENDER_MAX_WIDTH` | `4000` | Maximum rendered image width in pixels. |
| `RENDER_MAX_HEIGHT` | `4000` | Maximum rendered image height in pixels. |
| `RENDER_DEFAULT_ZOOM` | `10` | Default zoom level for rendered previews. |
| `DRAWDOWN_PREVIEW_MAX_PX` | `800` | Maximum dimension for the in-app drawdown preview thumbnail. |
| `TILE_ROW_COUNT` | `100` | Rows per tile for tiled rendering. |
| `TILE_COL_COUNT` | `200` | Columns per tile for tiled rendering. |
| `TILE_PRUNE_INACTIVE_DAYS` | `10` | Days before inactive tile cache entries are pruned. |

---

## Celery workers

| Variable | Default | Notes |
|---|---|---|
| `CELERY_CONCURRENCY` | `2` | Concurrent worker processes per container. I/O-bound tasks tolerate higher values; CPU-bound rendering tasks should stay at or below the host core count. |

Enable a second worker container by adding `worker02` to `COMPOSE_PROFILES`.

---

## Config file format

The config file at `CONFIG_FILE_PATH` is a JSON object. Secret fields are stored as Fernet-encrypted
base64 strings. Non-secret fields are stored as plaintext JSON values.

```json
{
  "smtp_user": "admin@weftmark.com",
  "smtp_password": "<fernet-encrypted>",
  "s3_endpoint_url": "https://account.r2.cloudflarestorage.com",
  "s3_access_key_id": "abc123",
  "s3_secret_access_key": "<fernet-encrypted>",
  ...
}
```

On startup, values are loaded in this priority order (highest wins):

1. Environment variables (`.env` / shell)
2. Config file values
3. Hardcoded defaults

If an env var is present and differs from the config file, the env var value is written back to the
config file on startup so the file stays in sync.
