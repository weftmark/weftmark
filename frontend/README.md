# WeftMark — Frontend

React single-page application for the WeftMark weaving platform.

---

## Overview

The frontend is a React 19 + Vite + TypeScript application served via nginx in production. It is optimized for tablet and phone use in portrait orientation — the primary interface is the at-the-loom tracking view, which requires large tap targets and responsive layout.

**Key features:**

- Pick-by-pick weaving tracking (treadle-tracking and lift-tracking modes)
- Progressive drawdown canvas with pan and zoom
- Project landing page with color palette editor and design preview
- WIF draft library with threading, tie-up, and drawdown previews
- Equipment inventory (looms, reeds) and yarn inventory
- Project completion summary with photos and session metrics
- Admin console for user management and platform health
- Light and dark mode (class-based; driven by user preference in the backend)

---

## Local Setup

### Prerequisites

- Node.js 20+ (check `.nvmrc` for the pinned version)
- The backend API running at `http://localhost:8000` (or Docker stack)

### Install

```bash
cd frontend
npm install
```

### Environment

```bash
cp .env.example .env.local
# Fill in:
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
```

All other VITE_ vars have defaults suitable for local dev.

### Run

```bash
npm run dev
```

App at `http://localhost:3000`. Vite proxies `/api`, `/auth`, `/health`, and `/system` to `http://localhost:8000`.

---

## Build

```bash
npm run build
```

Output goes to `dist/`. The nginx Dockerfile copies this at build time — no runtime Node.js in production.

```bash
npm run preview    # preview the production build locally
```

---

## Type Checking

```bash
npm run typecheck
```

CI (`ci-feature.yml`, `ci-dev-pr.yml`) runs this on every push. A clean `tsc` is required to merge.

---

## Linting

```bash
npm run lint
```

Uses ESLint with the React and TypeScript rulesets.

---

## Docker (via project root)

```bash
# From the repo root — always rebuild frontend and backend together
docker compose -f docker-compose.build.yml --env-file .env.local stop frontend backend worker
docker compose -f docker-compose.build.yml --env-file .env.local build frontend backend
docker compose -f docker-compose.build.yml --env-file .env.local up -d frontend backend worker
```

The frontend Dockerfile is a two-stage build: Node for `npm run build`, then nginx to serve the output. The `CLERK_PUBLISHABLE_KEY` env var is injected at container runtime by nginx — it is **not** baked into the image.

---

## Project Structure

```
frontend/src/
├── pages/                   # Top-level route components (one per page)
│   ├── DashboardPage.tsx    # Draft library home
│   ├── DraftDetailPage.tsx  # Draft detail + preview
│   ├── ProjectLandingPage.tsx  # Pre-tracking setup (colors, warp config)
│   ├── ProjectDetailPage.tsx   # At-the-loom tracking + completed summary
│   ├── LoomsPage.tsx        # Loom inventory list
│   ├── LoomDetailPage.tsx   # Loom detail + reed inventory
│   ├── YarnPage.tsx         # Yarn inventory list
│   ├── YarnDetailPage.tsx   # Yarn product + unit detail
│   ├── SettingsPage.tsx     # User profile and preferences
│   └── AdminPage.tsx        # Admin console
├── components/
│   ├── drafts/              # WIF upload modal, draft detail sections
│   ├── projects/            # Tracking UI, drawdown canvas, color palette editor
│   ├── looms/               # Loom form, reed table
│   ├── yarn/                # Yarn form, unit management
│   ├── layout/              # Sidebar, top bar, page shell
│   └── ui/                  # shadcn/ui primitives (Button, Dialog, Table, etc.)
├── api/                     # API client functions
│   ├── drafts.ts            # Draft CRUD + preview URLs
│   ├── projects.ts          # Project CRUD + tile/preview URLs
│   ├── looms.ts             # Loom and reed endpoints
│   ├── yarn.ts              # Yarn endpoints
│   └── users.ts             # User settings endpoint
└── lib/
    ├── client.ts            # Axios instance; configureApiClient(getToken) sets Bearer auth
    └── utils.ts             # Shared helpers (cn, formatting)
```

---

## Auth Architecture

All API requests go through the Axios client in `lib/client.ts`, which attaches the Clerk JWT as a `Bearer` token. **Never use raw `fetch()` without a Bearer header** — all `/api/*` endpoints require authentication.

Binary resources (images, drawdown tiles, design previews) cannot carry `Authorization` headers via `<img src>`. Use:

- `AuthedImage` component — fetches the URL with a Bearer header, sets a blob URL on `<img>`
- `downloadAuthed()` — for file downloads

---

## Design System

The app uses a **Slate & Copper** palette with two zones:

- **Public pages** (landing, login, register) — raw Tailwind palette classes, always light mode
- **Authenticated app** — CSS variable tokens only (`bg-background`, `text-foreground`, `bg-card`, etc.); dark mode handled automatically via `.dark` on `<html>`

Inside any authenticated page or component, **never use raw palette classes** (`stone-*`, `amber-*`, `zinc-*`). Use semantic tokens exclusively — no `dark:` variants needed.

Full reference: [`docs/design-system.md`](../docs/design-system.md)

---

## Environment Variables

| Variable | Where used | Description |
| --- | --- | --- |
| `VITE_CLERK_PUBLISHABLE_KEY` | Dev only | Clerk publishable key for local Vite dev |
| `VITE_APP_ENV` | Build-time | `dev` or `production`; controls dev banner display |
| `VITE_DEV_BANNER_COLOR` | Build-time | Color of the dev environment banner (e.g. `indigo`) |
| `CLERK_PUBLISHABLE_KEY` | Runtime (Docker) | Injected into nginx container at start; overrides the baked-in value |

In Docker, `CLERK_PUBLISHABLE_KEY` is passed to the container at runtime — the same image can be deployed to dev and prod with different Clerk projects just by changing the env var.
