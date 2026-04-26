# WeftMark — Platform Overview

## Vision

A multi-user, invite-only web platform for managing weaving projects. Users can upload weaving draft files, preview designs, track weaving progress at the loom, manage equipment and yarn inventory, and share their work. The platform is primarily a personal project management tool with optional sharing capabilities.

## Users

- **End users** — weavers managing their own projects, equipment, and inventory
- **Administrators** — manage invites, monitor platform health, review WIF compatibility records

## Core Principles

- All projects are private by default
- The platform respects user data — no social feed, no discovery, no unsolicited visibility
- The loom-side experience is a first-class concern — the UI must work well on tablets and phones in portrait orientation
- The WIF file is the source of truth for design data; the platform does not modify or reinterpret it beyond what the file provides
- Internet connection is required; offline session caching is a Phase 2 feature

---

## Architecture

### Deployment

- Monorepo containing both frontend and backend
- Delivered as Docker images
- Orchestrated via Docker Compose
- Configuration via `.env` / `.env.example`

### Authentication

- OIDC-based authentication (any OIDC-compliant provider supported via configuration)
- Reference implementation: **Authentik** (self-hosted)
- Invite-only registration — users cannot self-register
- Session stored as a signed JWT in an httpOnly cookie; signed with `APP_SECRET_KEY`
- Bootstrap rule: the first user to authenticate becomes admin with no invite required

### Frontend

| Component | Choice |
| --- | --- |
| Framework | React 18+ |
| Build tool | Vite |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Component library | shadcn/ui |
| Data fetching | TanStack Query |
| Routing | React Router |

### Backend

| Component | Choice |
| --- | --- |
| Framework | FastAPI |
| Language | Python |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Database | PostgreSQL |
| Task queue | Celery |
| Broker / cache | Redis |
| Rendering | PyWeaving |

---

## API Security

- All `/api/*` endpoints require authentication via `Depends(get_current_user)`
- Authentication is enforced by validating the signed session JWT from the httpOnly cookie
- Admin-only endpoints additionally use `Depends(require_admin)`
- Unauthenticated endpoints: `/health`, `/auth/login`, `/auth/callback`, `/auth/logout`
- Swagger UI (`/api/docs`) is only available when `DEBUG=true`; disabled in production

---

## Docker Compose Services and Network Isolation

Two networks are defined to limit the blast radius of any compromised service:

| Network | Purpose |
| --- | --- |
| `public` | Services that nginx or the browser must reach |
| `internal` | Data tier — db, redis, and service-to-service traffic only |

### Service exposure

| Service | Exposed to host | Networks | Notes |
| --- | --- | --- | --- |
| `frontend` (nginx) | **Yes** — port 3000 | public | Single user entry point; proxies `/api/`, `/auth/`, `/health` to backend |
| `authentik-server` | **Yes** — port 9000 | public + internal | Browser redirects directly to it for OIDC authorization; admin UI |
| `backend` | **No** | public + internal | Reached only through nginx; on internal to access db and redis |
| `worker` | No | internal | Background jobs only; no inbound connections needed |
| `db` | No | internal | Never reachable from host or public network |
| `redis` | No | internal | Never reachable from host or public network |
| `authentik-worker` | No | internal | Background jobs for Authentik only |

### Rationale

- `db` and `redis` are on `internal` only — a compromise of the frontend or nginx container cannot directly reach the data tier
- `backend` is not port-bound to the host — all traffic must pass through nginx, which enforces routing rules
- `authentik-server` must be host-exposed because the browser is redirected to it directly during the OIDC authorization flow; this cannot be proxied through nginx without breaking the OIDC redirect URI

---

## Responsive Design

The platform must function well across:

- Desktop / laptop
- Tablet (primary loom-side device)
- Mobile phone

Portrait orientation is preferred for the activity (loom-side) interface.

---

## Theme and Localization

- Light mode is the default
- Users can switch to dark mode via a preference setting
- Users can configure their preferred measurement system: `metric`, `imperial`, or `both`
- Measurement values are stored with their unit on each record (mixed units are supported per field)
- All calculations normalize to a common unit internally and convert to the user's display preference for presentation

---

## Equipment (Loom) Model

### Loom types

| Type | Shafts | Treadles | Heddles | Notes |
| --- | --- | --- | --- | --- |
| `floor_loom` | required | required (≥0) | — | Treadle count 0 valid for dobby/computer-controlled |
| `table_loom` | required | — | — | Uses levers; treadle count not applicable |
| `rigid_heddle` | — | — | optional | Primary spec is weaving width and heddle count |
| `inkle` | — | — | — | No shaft/treadle/heddle spec |
| `other` | optional | optional | optional | Catch-all for non-standard equipment |

### Loom versioning

- Loom specifications are tracked as an append-only version history (`LoomVersion`)
- Each version captures a dated spec snapshot: shafts, treadles, heddles, weaving width, warp waste allowance
- Activities reference a specific loom version, so historical accuracy is preserved after equipment upgrades

---

## Data Lifecycle

- Looms, projects, and activities use **soft delete** — records are archived, not permanently destroyed
- Soft-deleted looms retain their full versioned state history and remain accessible from any activity that references them

---

## Email

- Transactional email (invite links) is delivered via **SMTP2Go**
- SMTP credentials are configured via environment variables
- Invite links are single-use, time-limited (administrator-configurable expiry), and sent to the invitee's email address
