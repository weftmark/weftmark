# WeftMark — Backend

FastAPI backend service for the WeftMark weaving platform.

---

## Overview

The backend handles all API requests, authentication, draft processing, image rendering, and background task scheduling. It is written in Python 3.12 using FastAPI with async SQLAlchemy and Celery for background work.

**Key responsibilities:**

- WIF file parsing, validation, and storage
- Server-side draft rendering via PyWeaving (threading diagram, tie-up, drawdown)
- Project tracking (pick-by-pick weaving progress)
- Equipment and yarn inventory management
- Invitation-based user registration with admin approval (via Clerk)
- Celery background tasks for tile pre-rendering and periodic maintenance
- SMTP2Go transactional email (invitations, health alerts)
- OpenTelemetry traces, metrics, and logs

---

## Local Setup

### Prerequisites

- Python 3.12
- PostgreSQL 17 (or a Neon connection string)
- Redis 7

### Conda (recommended)

```bash
conda env create -f environment.yml
conda activate weaving_site
```

### pip

```bash
cd backend
pip install -r requirements-dev.txt
```

### Environment

```bash
cp .env.example .env
# Fill in: POSTGRES_PASSWORD, CLERK_SECRET_KEY, CLERK_PUBLISHABLE_KEY, CLERK_WEBHOOK_SECRET
# Set STORAGE_BACKEND=local for local file storage (no R2 needed in dev)
```

### Database

```bash
alembic upgrade head
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Celery worker (optional for dev)

```bash
celery -A app.celery_app worker --loglevel=info
```

Without the worker, draft tile pre-rendering and email dispatch will queue but not execute.

---

## Docker (via project root)

The backend is always rebuilt alongside the frontend and worker — they share one image:

```bash
# From the repo root
docker compose -f docker-compose.build.yml --env-file .env.local stop frontend backend worker
docker compose -f docker-compose.build.yml --env-file .env.local build frontend backend
docker compose -f docker-compose.build.yml --env-file .env.local up -d frontend backend worker
```

Do not rebuild backend without rebuilding frontend, and vice versa — version skew causes the health check to fail.

---

## Running Tests

Tests require a running PostgreSQL instance. With Docker, the `local-db` profile exposes it at `localhost:5433`.

```bash
cd backend
POSTGRES_PASSWORD=<your-password> pytest
```

Coverage report:

```bash
POSTGRES_PASSWORD=<your-password> pytest --cov=app --cov-report=term-missing
```

Test structure mirrors `app/`: `app/services/foo.py` → `tests/services/test_foo.py`.

See [`docs/testing.md`](../docs/testing.md) for the full coverage breakdown.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory, middleware, router registration
│   ├── config.py            # Pydantic settings (reads .env / environment variables)
│   ├── celery_app.py        # Celery instance and beat schedule
│   ├── dependencies.py      # Shared FastAPI dependencies (get_db, get_current_user)
│   ├── routers/
│   │   ├── admin.py         # Admin console: user management, maintenance, platform health
│   │   ├── auth.py          # Clerk webhook receiver, session bootstrap
│   │   ├── drafts.py        # WIF upload, library, rendering endpoints
│   │   ├── health.py        # /health liveness and /health/ready readiness probes
│   │   ├── looms.py         # Loom inventory, reed inventory, versioned loom history
│   │   ├── logs.py          # Audit log endpoints
│   │   ├── projects.py      # Project CRUD, tracking, color replacements, tile endpoints
│   │   ├── system.py        # Server-sent events, system status
│   │   ├── users.py         # User settings, EULA acceptance
│   │   └── yarn.py          # Yarn product and unit inventory
│   ├── models/              # SQLAlchemy ORM models (one file per entity)
│   ├── services/
│   │   ├── rendering.py     # PyWeaving integration: parse, render, apply color replacements
│   │   ├── storage.py       # R2 / local file storage, tile key management
│   │   ├── wif_parser.py    # WIF 1.1 parser
│   │   ├── wif_linter.py    # WIF validation: structural checks, linting report
│   │   ├── email.py         # SMTP2Go email dispatch
│   │   ├── clerk.py         # Clerk JWT verification helpers
│   │   └── audit.py         # Audit log write helpers
│   └── tasks/
│       └── tiles.py         # Celery tasks: prerender_drawdown_tiles, prerender_project_tiles
├── alembic/                 # Database migrations
│   └── versions/            # Migration scripts (auto-generated + hand-edited)
├── tests/
│   ├── conftest.py          # Fixtures: db_session, auth_client, admin_client, etc.
│   ├── routers/             # API endpoint tests
│   └── services/            # Service unit tests
├── scripts/                 # Admin utilities (dev_reset.py, seed scripts)
├── requirements.txt         # Production dependencies
├── requirements-dev.txt     # Dev + test dependencies
├── ruff.toml                # Linter and formatter config
└── pytest.ini               # Test configuration
```

---

## Key API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (DB, Redis, Clerk, SMTP, storage) |
| `GET` | `/api/drafts` | List user's WIF drafts |
| `POST` | `/api/drafts` | Upload a WIF file |
| `GET` | `/api/drafts/{id}/preview` | Full draft layout PNG (threading + tie-up + drawdown) |
| `GET` | `/api/projects` | List user's weaving projects |
| `POST` | `/api/projects` | Create a project from a draft |
| `PUT` | `/api/projects/{id}/color-replacements` | Save per-project color swaps (triggers tile re-render) |
| `GET` | `/api/projects/{id}/drawdown/preview` | Full draft PNG with project color replacements applied |
| `GET` | `/api/projects/{id}/drawdown` | Progressive drawdown tile endpoint |
| `GET` | `/api/looms` | List user's looms |
| `GET` | `/api/looms/{id}/reeds` | List reeds owned for a loom |
| `GET` | `/api/yarn` | List yarn inventory |
| `GET` | `/api/admin/users` | Admin: list all users |
| `POST` | `/api/admin/users/{id}/approve` | Admin: approve pending user |

All `/api/*` endpoints require `Authorization: Bearer <clerk_jwt>`. Admin endpoints additionally require `is_admin=True` on the authenticated user.

---

## Auth Rules

- JWT verification uses `Depends(get_current_user)` on every protected route
- Admin routes additionally use `Depends(require_admin)`
- Unauthenticated endpoints: `GET /health`, `POST /auth/clerk/webhook`
- The first registered user automatically becomes an admin (bootstrap rule)
- All other users require admin approval after Clerk sign-up

---

## Environment Variables

See [`../.env.example`](../.env.example) for the full annotated reference. The backend reads configuration via Pydantic Settings from environment variables or a `.env` file.

**Database:** `POSTGRES_DSN` overrides individual `POSTGRES_*` vars. For Neon, set both `POSTGRES_DSN` (pooled, for app traffic) and `POSTGRES_DSN_DIRECT` (direct, for Alembic migrations).

**Storage:** `STORAGE_BACKEND=local` stores uploads in `UPLOAD_DIR` (default `/app/uploads`). Set `STORAGE_BACKEND=s3` and fill `S3_*` vars for Cloudflare R2 in production.
