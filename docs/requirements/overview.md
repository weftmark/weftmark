# WeftMark — Platform Overview

## Vision

A multi-user, invite-only web platform for managing weaving drafts. Users can upload weaving draft files, preview designs, track weaving progress at the loom, manage equipment and yarn inventory, and share their work. The platform is primarily a personal draft management tool with optional sharing capabilities.

## Users

- **End users** — weavers managing their own drafts, equipment, and inventory
- **Administrators** — manage invites, monitor platform health, review WIF compatibility records

## Core Principles

- All drafts are private by default
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

- Clerk hosted authentication
- Users can self-register; new accounts require admin approval before access is granted
- Backend validates Bearer tokens in the `Authorization` header
- Bootstrap rule: the first user to register becomes admin with no approval required

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
- Authentication is enforced by validating the Clerk Bearer token from the `Authorization` header
- Admin-only endpoints additionally use `Depends(require_admin)`
- Unauthenticated endpoints: `/health`, `/webhooks/clerk`
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
| `frontend` (nginx) | **Yes** — port 3000 | public | Single user entry point; proxies `/api/` and `/health` to backend |
| `backend` | **No** | public + internal | Reached only through nginx; on internal to access db and redis |
| `worker` | No | internal | Background jobs only; no inbound connections needed |
| `db` | No | internal | Never reachable from host or public network |
| `redis` | No | internal | Never reachable from host or public network |

### Rationale

- `db` and `redis` are on `internal` only — a compromise of the frontend or nginx container cannot directly reach the data tier
- `backend` is not port-bound to the host — all traffic must pass through nginx, which enforces routing rules
- `backend` handles auth by validating Bearer tokens inline — no separate auth service needs host exposure

---

## Responsive Design

The platform must function well across:

- Desktop / laptop
- Tablet (primary loom-side device)
- Mobile phone

Portrait orientation is preferred for the project (loom-side) interface.

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
- Projects reference a specific loom version, so historical accuracy is preserved after equipment upgrades

---

## Data Lifecycle

- Looms, drafts, and projects use **soft delete** — records are archived, not permanently destroyed
- Soft-deleted looms retain their full versioned state history and remain accessible from any project that references them
- Configurable retention period (`SOFT_DELETE_RETENTION_DAYS`); permanent purge triggered from Admin → Maintenance

---

## Email

- Transactional email (invite links, health alerts) is delivered via **SMTP2Go**
- SMTP credentials are configured via environment variables
- Invite links are single-use, time-limited (administrator-configurable expiry), and sent to the invitee's email address
- Stack health alerts (startup, degraded, recovery) are sent to superuser accounts when `STACK_ALERT_EMAILS_ENABLED=true`

---

## Rendering

- Draft previews and drawdown images are generated server-side by **PyWeaving** (Python)
- The full draft layout (threading diagram, tie-up, drawdown) is rendered as a single PNG image
- Tile pre-rendering runs as a Celery background task — drawdown tiles are sliced into row strips and stored in R2 for progressive loading during the weaving session
- Per-project color replacements are applied to the rendered output; saving new colors triggers a tile re-render

---

## Feature Highlights (Current)

The following features are implemented and live as of v0.145.0:

- WIF 1.1 import with detailed lint report
- Draft library with threading, tie-up, drawdown preview, and color palette display
- Treadle-tracking and lift-tracking project modes
- Project landing page — set color replacements, review design, configure warp before tracking starts
- Color palette editor with per-project hex→hex color swaps flowing through drawdown, pick display, and completed summary
- Progressive drawdown tile viewer (canvas-based, pan + zoom)
- Pick-by-pick tracking with worked-pick dwell detection, session auto-detection, and Bluetooth pedal support
- Warp thread count per palette color; filtered unused colors
- Reed inventory with EPI-based recommendations
- Loom versioned history; projects reference exact loom configuration
- Photo documentation with captions, auto-stamped step/session metadata
- Project completion summary with design preview, session metrics, and warp setup details
- Yarn inventory (products + physical units)
- Admin console: user management, approval queue, platform health, audit log, maintenance
- OpenTelemetry observability (traces, metrics, structured logs)
- GeoIP geolocation for audit logs and metrics (MaxMind GeoLite2)
- EULA acceptance gate with versioned EULA content
- Light and dark mode; metric and imperial measurement support
