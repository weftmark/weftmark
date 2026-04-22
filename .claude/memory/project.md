# Project Memory — Weaving Site

## What This Is

A multi-user, invite-only web platform for managing weaving (loom) projects. Primarily a personal project management tool for weavers, with optional sharing capabilities. All projects are private by default.

## Requirements Documentation

All formal requirements live in `docs/requirements/`. Start with `docs/requirements/README.md` for the index.

The WIF 1.1 specification is at `docs/standard/standard-wif1-1.txt`. Sample WIF files are in `docs/samples/`.

## Tech Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query + React Router |
| Backend | FastAPI (Python) + SQLAlchemy + Alembic |
| Database | PostgreSQL |
| Task queue | Celery + Redis |
| Rendering | PyWeaving (Python library) |
| Auth | Authentik (OIDC, self-hosted). Any OIDC-compliant provider supported via config. |
| Deployment | Docker + Docker Compose, monorepo |
| Artifact | Docker image + docker-compose.yml + .env.example |

## Key Architectural Decisions

**WIF Import:** Files always import with warnings. Unsupported features are disabled per file, not rejected. Problematic files prompt the user for source software/version, stored in admin records.

**Activities:** One step = one pick. Activity type (lift-tracking or treadle-tracking) is locked after the first pick — a new activity must be created to change type. Multiple activities per project are allowed and encouraged.

**Dwell threshold:** Distinguishes worked picks from review navigation. Learned per activity. Lift-tracking defaults higher than treadle-tracking. No explicit confirm-pick button — the system learns the user's rhythm.

**Loom versioning:** Loom records have a versioned state history. Activities reference a specific loom version, preserving historical accuracy after upgrades.

**Yarn inventory:** Tracks individual skeins with unique IDs (Spoolman-inspired). Both weight and yardage tracked. Consumption estimated from WIF data + warping plan, user-adjustable.

**Sharing:** Revocable slug URLs per project. Project-level only — individual activities cannot be shared independently. No social feed. No user discovery. Sharing is always intentional.

**Offline:** Internet required in Phase 1. Activity step log designed as append-only event log to make Phase 2 offline session caching straightforward.

**Liftplan/treadling auto-computation:** Phase 2 only. Phase 1 uses only what is explicitly present in the WIF file.

**Notifications:** Phase 2.

**Invites:** Admin sends a one-time signup email via SMTP2Go. Link expiry is admin-configurable. No self-registration.

**WIF versioning:** Uploading a new WIF for a project preserves the old WIF and all its activities. The user creates a new activity on the updated WIF and manually navigates to the current step. Old activities remain fully accessible.

**Keyboard navigation:** Phase 1. Bluetooth pedal works via keyboard emulation — no special Bluetooth handling needed.

**Activity sessions:** Auto-detected. Opening an activity starts a session; closing or going idle ends it. Idle timeout threshold is user-configurable.

**Soft delete:** Looms, projects, and activities use soft delete (archived, not destroyed). Soft-deleted looms retain their historical state and remain accessible from activities that reference them.

**Yarn consumption:** Automatically derived from activity steps and WIF data. User can manually adjust any value.

**PDF reports:** Generated on-demand — not stored. Each download re-generates the report.

**Dark mode:** Light mode is the default. Users can switch to dark mode via a preference setting.

**Reverse proxy:** SSL termination and routing are handled outside the Docker Compose stack.

## Phase 2 Features

Documented in `docs/requirements/phase2.md`:
- Offline session caching (append-only event log design makes this feasible)
- Liftplan / treadling auto-computation
- Notifications
- Spoolman integration for yarn import
