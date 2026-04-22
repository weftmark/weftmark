# Weaving Site — Platform Overview

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

### Docker Compose Services

- `frontend` — React app served via nginx
- `backend` — FastAPI application
- `worker` — Celery worker for background jobs (rendering, PDF export)
- `db` — PostgreSQL
- `redis` — Redis
- `authentik` — OIDC provider

---

## API

The frontend communicates with the backend exclusively via REST API. No server-rendered pages.

---

## Responsive Design

The platform must function well across:

- Desktop / laptop
- Tablet (primary loom-side device)
- Mobile phone

Portrait orientation is preferred for the activity (loom-side) interface.

---

## Theme

- Light mode is the default
- Users can switch to dark mode via a preference setting

---

## Data Lifecycle

- Looms, projects, and activities use **soft delete** — records are archived, not permanently destroyed
- Soft-deleted looms retain their full versioned state history and remain accessible from any activity that references them

---

## Email

- Transactional email (invite links) is delivered via **SMTP2Go**
- SMTP credentials are configured via environment variables
