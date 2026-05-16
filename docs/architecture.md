# WeftMark — Architecture

Technical reference for the stack, repo layout, services, API security model, and local development setup.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| **Frontend** | React 18 + Vite + TypeScript + Tailwind CSS |
| **UI components** | shadcn/ui (Radix primitives) |
| **Data fetching** | TanStack Query v5 + React Router v6 |
| **Backend** | FastAPI (Python 3.12) |
| **ORM / migrations** | SQLAlchemy 2 (async) + Alembic |
| **Database** | PostgreSQL 17 (Neon in prod; local container in dev) |
| **Task queue** | Celery 5 + Redis 7 |
| **Authentication** | Clerk (OIDC / JWT) |
| **Draft rendering** | PyWeaving (server-side; PIL image generation) |
| **Object storage** | Cloudflare R2 (S3-compatible; boto3) |
| **Observability** | OpenTelemetry → OTLP collector → Grafana / Loki / Tempo |
| **GeoIP** | MaxMind GeoLite2-City (auto-refreshed weekly) |
| **Email** | SMTP2Go |
| **DNS / SSL** | Cloudflare — Full (strict) mode, Origin CA cert |
| **Container registry** | `ghcr.io/weftmark/weftmark-backend` / `weftmark-frontend` |
| **Deployment** | Komodo (container orchestration) |

---

## Repository Structure

```
weaving_site/
├── backend/
│   ├── app/
│   │   ├── routers/          # FastAPI route handlers
│   │   │   ├── admin.py      # Admin-only endpoints
│   │   │   ├── auth.py       # Clerk webhook + auth utilities
│   │   │   ├── drafts.py     # WIF upload, library, preview
│   │   │   ├── looms.py      # Equipment inventory
│   │   │   ├── projects.py   # Weaving project tracking
│   │   │   ├── users.py      # User settings, EULA
│   │   │   ├── yarn.py       # Yarn inventory
│   │   │   └── health.py     # Health / readiness probes
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── services/
│   │   │   ├── rendering.py  # PyWeaving draft rendering
│   │   │   ├── storage.py    # R2 / local file storage
│   │   │   ├── wif_parser.py # WIF 1.1 parser
│   │   │   ├── wif_linter.py # WIF validation / linting
│   │   │   └── email.py      # SMTP2Go dispatch
│   │   ├── tasks/
│   │   │   └── tiles.py      # Celery: pre-render drawdown tiles to R2
│   │   ├── config.py         # Pydantic settings (reads .env)
│   │   └── celery_app.py     # Celery application instance
│   ├── alembic/              # Database migrations
│   ├── tests/                # pytest test suite
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/            # Top-level route components
│   │   ├── components/       # Reusable UI components
│   │   │   ├── drafts/
│   │   │   ├── projects/
│   │   │   ├── looms/
│   │   │   ├── yarn/
│   │   │   └── ui/           # shadcn/ui primitives
│   │   ├── api/              # API client functions (all use authed client)
│   │   └── lib/
│   │       └── client.ts     # Axios instance configured with Bearer auth
│   └── Dockerfile
├── docs/
│   ├── architecture.md       # This file
│   ├── design-system.md      # UI palette, tokens, component conventions
│   ├── testing.md            # Test coverage and gap analysis
│   ├── requirements/         # Feature specifications
│   └── deployment/           # Environment strategy, CI/CD reference
├── e2e/                      # Playwright end-to-end tests
├── scripts/                  # Dev utilities (rbd.ps1, benchmark, etc.)
├── docker-compose.build.yml  # Container orchestration (build mode)
├── .env.example              # Environment variable reference
└── CLAUDE.md                 # Claude Code instructions
```

---

## Docker Compose Services

| Service | Container | Network | Port exposed | Role |
| --- | --- | --- | --- | --- |
| `frontend` | `weaving_site_frontend` | public | `3000→80` | nginx serving React SPA; proxies `/api/`, `/health` to backend |
| `backend` | `weaving_site_backend` | public + internal | none (host) | FastAPI — API and business logic |
| `worker` | `weaving_site_worker` | internal | none | Celery worker — image rendering, email, maintenance tasks |
| `worker2` | `weaving_site_worker2` | internal | none | Second Celery worker (profile: `worker02`) |
| `beat` | `weaving_site_beat` | internal | none | Celery Beat — periodic task scheduler (60 s tick) |
| `redis` | `weaving_site_redis` | internal | `127.0.0.1:6379` | Celery broker and result backend |
| `db` | `weaving_site_db` | internal | `127.0.0.1:5435` | Local PostgreSQL (profile: `local-db`; omit when using Neon) |

**Networks:**

- `public` — frontend + backend; nginx proxies inbound traffic to backend
- `internal` — backend + workers + redis + db; not reachable from host

The backend is never port-exposed to the host in production. nginx (the frontend container) is the only entry point. CrowdSec bouncer sits in front of nginx for threat detection and IP banning.

---

## API Security

### Authentication

- All API endpoints require `Authorization: Bearer <clerk_jwt>` header validation via `Depends(get_current_user)`.
- Admin-only endpoints additionally require `Depends(require_admin)`.
- Unauthenticated endpoints: `GET /health`, `POST /webhooks/clerk`.
- **Never use cookies** for API auth — all requests go through `configureApiClient(getToken)` in `frontend/src/lib/client.ts`, which attaches the Bearer token automatically.

### Binary endpoints

Images, drawdown tiles, and design previews cannot carry `Authorization` headers via `<img src>`. These endpoints use the `AuthedImage` component (fetch → blob URL) and `downloadAuthed()` for file downloads.

### First-user bootstrap

The first registered user automatically becomes an admin with no approval required. Every subsequent user requires admin approval (invitation-only registration).

---

## Rendering Architecture

Draft rendering is handled server-side by PyWeaving (Python):

1. **On-demand** — `GET /api/drafts/{id}/preview` renders the full draft layout (threading diagram, tie-up, drawdown) synchronously for immediate display.
2. **Tile pre-render (Celery)** — `prerender_project_tiles` task slices the drawdown into row-tiles and stores them in R2. The weaving view loads tiles progressively as the user scrolls through picks.
3. **Color replacements** — per-project hex→hex color swaps are applied to the PyWeaving draft before rendering. Saving new color replacements triggers a tile re-render task to keep R2 cache in sync.

Tile key format: `tiles/{entity_type}/{entity_id}/{scale}/{row_start}.png`

---

## Environment Variables

Full reference in [`.env.example`](../.env.example). Key variables:

| Variable | Description |
| --- | --- |
| `APP_SECRET_KEY` | Signing key — required in production |
| `APP_ENV` | `dev` or `production` — controls HSTS, CSP, security headers |
| `POSTGRES_DSN` | Pooled connection string (Neon) — overrides individual `POSTGRES_*` vars |
| `POSTGRES_DSN_DIRECT` | Direct (non-pooled) connection for Alembic migrations |
| `CLERK_PUBLISHABLE_KEY` | Frontend Clerk key — injected at runtime, never baked into image |
| `CLERK_SECRET_KEY` | Backend JWT verification key |
| `CLERK_WEBHOOK_SECRET` | Svix webhook signing secret (`whsec_...`) |
| `STORAGE_BACKEND` | `local` (dev) or `s3` (production / R2) |
| `S3_ENDPOINT_URL` | Cloudflare R2 endpoint when `STORAGE_BACKEND=s3` |
| `REDIS_URL` | Celery broker — `redis://redis:6379/0` in Docker |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP receiver; leave empty to disable telemetry |
| `RENDER_MAX_WIDTH` | Maximum pixel width for rendered images (default `4000`) |
| `MAXMIND_LICENSE_KEY` | GeoLite2 license — leave empty to disable geo lookups |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP2Go credentials for transactional email |
| `STACK_ALERT_EMAILS_ENABLED` | Set `false` in dev/staging to suppress health-alert emails |

---

## Local Development

### With Docker (recommended)

```bash
git clone https://github.com/weftmark/weftmark.git
cd weftmark
cp .env.example .env.local
# Fill in: CLERK keys, POSTGRES_PASSWORD, APP_SECRET_KEY
# Set COMPOSE_PROFILES=local-db to start a local PostgreSQL container

docker compose -f docker-compose.build.yml --env-file .env.local build frontend backend
docker compose -f docker-compose.build.yml --env-file .env.local up -d
```

App: `http://localhost:3000` · API: `http://localhost:8000`

**Always rebuild frontend and backend together** — the worker shares the backend image; rebuilding only one creates version skew between uvicorn and Celery processes.

### Frontend only (Vite dev server)

```bash
cd frontend
npm install
cp .env.example .env.local
# Set VITE_CLERK_PUBLISHABLE_KEY in .env.local
npm run dev
```

Vite proxies `/api` to `http://localhost:8000` — the backend container must be running.

### Backend only (without Docker)

Requires Python 3.12 and a running PostgreSQL instance.

```bash
cd backend
conda env create -f environment.yml   # or: pip install -r requirements.txt
conda activate weaving_site
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

---

## Running Tests

Backend tests require a running PostgreSQL instance (exposed at `localhost:5433` via the `local-db` profile):

```bash
cd backend
POSTGRES_PASSWORD=<your-password> pytest
```

Test structure mirrors `app/`: `app/services/foo.py` → `tests/services/test_foo.py`.

See [`docs/testing.md`](testing.md) for coverage breakdown and gap analysis.

---

## CI/CD Overview

See [`docs/deployment/ci-cd.md`](deployment/ci-cd.md) for the full pipeline reference.

| Workflow | Trigger | Gate |
| --- | --- | --- |
| `ci-feature.yml` | push `feature/*`, `fix/*` | lint + typecheck |
| `ci-dev-pr.yml` | PR to `dev` | full suite — lint, typecheck, pytest, migration check |
| `ci-hotfix.yml` | push `hotfix/*` | full suite + dep audit + docker build |
| `ci-main-pr.yml` | PR to `main` | lint, typecheck, dep audit, docker build |
| `ci-dev-push.yml` | push to `dev` | SBOM update + semver version bump (bot commits) |
| `publish-dev.yml` | manual dispatch | build + push `:dev` image → Komodo deploy to `dev.weftmark.com` |

Bot actor: `weftmark-bot[bot]`. Post-merge jobs guard with `if: github.actor != 'weftmark-bot[bot]'`.

---

## Deployment Topology

```
Internet
    │
    ▼
Cloudflare (DNS/SSL — Full strict, Origin CA)
    │
    ▼
CrowdSec bouncer
    │
    ▼
nginx (frontend container — port 3000)
    │  proxies /api/, /health
    ▼
FastAPI (backend container — internal network only)
    │              │
    ▼              ▼
Neon Postgres    Redis ← Celery workers (render, email, tasks)
                          Celery Beat (scheduler)

Object storage: Cloudflare R2 (boto3, S3-compatible)
Registry:       ghcr.io/weftmark/weftmark-{backend,frontend}
Orchestration:  Komodo (per-environment stacks)
```

See [`docs/deployment/environments.md`](deployment/environments.md) for the dev / staging / prod environment strategy.
