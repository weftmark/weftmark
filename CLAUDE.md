# WeftMark — Claude Code Instructions

## Project

WeftMark: multi-user web platform for managing weaving drafts. Private by default. Clerk-based self-registration; new accounts require admin approval. BSL 1.1 license — converts to MIT 2029-01-01. Do not ask about licensing.

| Layer | Choice |
| --- | --- |
| Frontend | React + Vite + TypeScript + Tailwind CSS + shadcn/ui + TanStack Query + React Router |
| Backend | FastAPI (Python) + SQLAlchemy + Alembic |
| Database | PostgreSQL (Neon in prod, local container in dev) |
| Task queue | Celery + Redis |
| Auth | Clerk (OIDC) |
| Rendering | PyWeaving (server-side, Celery background jobs) |

## Auth rules

- Backend validates `Authorization: Bearer` header — NOT cookies
- All API calls must go through `client.ts`'s `configureApiClient(getToken)` — never raw `fetch()` without a Bearer header
- Binary endpoints (photos, drawdown, preview) use `AuthedImage` component (fetch → blob URL) — `<img src>` cannot carry Bearer headers
- File downloads use `downloadAuthed()`
- All `/api/*` endpoints: `Depends(get_current_user)`; admin endpoints also: `Depends(require_admin)`
- Unauthenticated endpoints: `/health`, `/webhooks/clerk`
- First registered user auto-becomes admin with no approval required (bootstrap rule)

## Infrastructure

- **Cloudflare:** DNS/SSL — Full (strict) mode, Origin CA cert, no Certbot needed
- **R2:** object storage — `STORAGE_BACKEND=s3` / boto3, zero egress fees
- **nginx + CrowdSec** bouncer → containers; backend not port-exposed to host
- **Postgres:** `POSTGRES_DSN` in `.env` overrides individual `POSTGRES_*` vars (prod uses Neon DSN)
- **Registry:** `ghcr.io/weftmark/weftmark-backend` / `ghcr.io/weftmark/weftmark-frontend`
- **GitHub:** `github.com/weftmark/weftmark` (org: `weftmark`, owner: `gx1400`)
- **Email:** SMTP2Go — `admin@weftmark.com` / `feedback@weftmark.com`

## Git workflow

Branches: `main` (prod-ready), `dev` (integration), `feature/*`, `fix/*`, `hotfix/*`.

- Branch from `dev`; PR always targets `dev` — pass `--base dev` to `gh pr create`
- Never commit directly to `main` or `dev`
- Hotfix: branch from `main`, PR to `main`, then backport to `dev` as a follow-up PR
- After every push: `gh run list --repo weftmark/weftmark --limit 3` — surface failures immediately with `gh run view <id> --log-failed`

**Merge gate (feature → dev):** tests written + passing, `tsc` clean, golden path verified in browser, no regressions  
**Merge gate (dev → main):** all above + full smoke-test (auth login, core CRUD, projects), pytest passes, no known open bugs

**When to suggest a commit:** after each feature passes end-to-end testing + pytest. Never mid-feature.

## CI/CD

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `ci-feature.yml` | push `feature/*`, `fix/*` | lint + typecheck |
| `ci-dev-pr.yml` | PR to `dev` | **full suite — this is the merge gate**; tests don't re-run after merge |
| `ci-hotfix.yml` | push `hotfix/*` | full suite (lint, typecheck, pytest, migration, dep audit, docker build) |
| `ci-main-pr.yml` | PR to `main` | lint, typecheck, dep audit, docker build; **no file writes allowed** |
| `check-merge-source.yml` | PR to `main` | source branch must be `dev` or `hotfix/*` |
| `ci-dev-push.yml` | push to `dev` | SBOM update + semver version bump (bot commits) |

Bot actor: `weftmark-bot[bot]`. Post-merge jobs guard with `if: github.actor != 'weftmark-bot[bot]'` — do NOT use `[skip actions]` (that token suppresses PR CI on the target branch).

## Chat shorthand

When the user types one of these aliases, execute the corresponding action immediately without asking for confirmation:

| Alias | Intent | Action |
| --- | --- | --- |
| `rbd` | Rebuild and redeploy | Stop frontend + backend + worker → build frontend + backend → start all three → confirm health via `/health` response |
| `cap` | Commit and push | Stage all changed files → commit with a generated message based on the diff → push to current branch |
| `reb` | Rebase to dev | `git fetch origin` → `git checkout dev` → `git pull origin dev` — clean base for starting a new branch |
| `prd` | PR to dev | Check if current branch already has an open PR targeting `dev`; if yes, print the URL; if no, create one with `gh pr create --base dev` |
| `prm` | PR to main | Check if `dev` already has an open PR targeting `main`; if yes, print the URL; if no, create one with `gh pr create --head dev --base main` |
| `rrm` | Review run after merge | `gh run list --limit 5` to find runs triggered by the recent merge → watch for completion → report pass/fail and surface any blocking failures with `gh run view --log-failed` |
| `rtc` | Review and tidy issues | List all open issues → for each one worked in recent branches/PRs add a progress comment → close any that are completed, duplicate, or obsolete |

Scripts are also available at `scripts/rbd.ps1` for direct terminal use.

---

## Development rules

**Pull before starting:** `git pull origin <branch>` — CI bot commits version bumps directly to branches; skip this and pushes will conflict on `VERSION` / `frontend/package.json`.

**Rebuild — always all three services together (frontend, backend, worker):**

```bash
docker compose -f docker-compose.build.yml --env-file .env.local stop frontend backend worker
docker compose -f docker-compose.build.yml --env-file .env.local build frontend backend
docker compose -f docker-compose.build.yml --env-file .env.local up -d frontend backend worker
```

The worker shares the backend image — stopping and restarting all three ensures no version skew between the uvicorn and Celery processes.

The `frontend-1` container is nginx-only — never run `docker compose exec frontend npm ...`.

**Test-first for every new feature:**

1. Write tests → confirm they fail → implement until they pass → commit feature + tests together
2. Backend tests mirror `app/` structure: `app/services/foo.py` → `tests/services/test_foo.py`
3. After each feature update coverage estimate and gap table in `docs/testing.md`

**Test fixtures** (`backend/tests/conftest.py`):

| Fixture | Scope | Purpose |
| --- | --- | --- |
| `setup_database` | session | creates `test_weaving_site` DB + schema once |
| `db_session` | function | AsyncSession; truncates all tables after each test |
| `test_user` | function | regular user, `is_admin=False` |
| `admin_user` | function | `is_admin=True` |
| `client` | function | unauthenticated AsyncClient, `get_db` overridden |
| `auth_client` | function | authenticated as `test_user`, `get_current_user` overridden |
| `admin_client` | function | authenticated as `admin_user`, `get_current_user` overridden |

Local tests require `POSTGRES_PASSWORD` env var; docker-compose db exposed at `localhost:5433`. CI uses `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`.

**Package installs:** regenerate `environment.yml` (`conda run -n weaving_site conda env export --no-builds > environment.yml`) and `.nvmrc` (if Node version changed) in the same commit.

**Single bash commands:** issue each as a separate tool call — never chain with `&&` or `;`.

## PR workflow

1. Claude implements and opens PR (`gh pr create --base dev`)
2. Developer reviews on GitHub and merges
3. **Never run `gh pr merge`**
4. One PR = one topic. Incidental fixes noted and handled in a separate PR.

## Collaboration style

- Ask one question at a time — single most important question, wait for answer
- Give clear recommendations with reasoning, not balanced option lists
- Deferred/phase 2 features go in `docs/requirements/phase2.md`

## Design system

**Palette: Slate & Copper.** Two zones: public pages (always light mode, raw palette classes OK) vs authenticated app (CSS variable tokens only, dark mode handled automatically via `.dark` on `<html>`).

**Critical rule:** Inside any authenticated page or component, NEVER use raw palette classes (`stone-*`, `amber-*`, `zinc-*`). Use semantic CSS variable tokens exclusively. No `dark:` variants needed — the variables handle it.

| Tailwind class | Semantic role |
| --- | --- |
| `bg-background` | Page canvas |
| `bg-card` / `text-card-foreground` | Panel, modal, sidebar, card surfaces |
| `bg-muted` / `text-muted-foreground` | Subtle backgrounds / de-emphasized text |
| `text-subdued` | Secondary nav labels (less faint than `muted-foreground`) |
| `text-accent` / `bg-accent` | Amber highlight — active icons, focus rings, badges |
| `bg-primary` / `text-primary-foreground` | CTA buttons, logo area |
| `bg-secondary` / `text-secondary-foreground` | Secondary buttons, chips |
| `bg-copper-subtle` / `text-copper-on-subtle` | Active nav item chip |
| `border-border` | All borders |
| `bg-input` / `ring-ring` | Form inputs / focus rings |
| `bg-popover` / `text-popover-foreground` | Dropdowns, tooltips |

Public pages (landing, login, register): raw palette classes; no `dark:` variants.  
Dark mode is class-based (`darkMode: ["class"]` in `tailwind.config.ts`); applied by `AuthContext` from `user.theme`.

Full design reference (layout patterns, component snippets, palette previews): `docs/design-system.md`

## Feature requirements map

Read the listed spec **before** touching any of these feature areas:

| Feature area | Read first | Key source files |
| --- | --- | --- |
| WIF import / linting | `docs/requirements/wif-import.md` | `app/services/wif_parser.py`, `wif_linter.py` |
| Design preview / rendering | `docs/requirements/design-preview.md` | `app/services/rendering.py` |
| Projects (weaving tracking) | `docs/requirements/projects.md` | `app/routers/projects.py`, `app/models/project.py` |
| Equipment / loom inventory | `docs/requirements/equipment-inventory.md` | `app/routers/looms.py`, `app/models/loom.py` |
| Yarn inventory | `docs/requirements/yarn-inventory.md` | `app/routers/yarn.py`, `app/models/yarn.py` |
| Reports + session log | `docs/requirements/reports.md` | `app/routers/projects.py` |
| User sharing / profiles | `docs/requirements/sharing-profiles.md` | `app/routers/drafts.py` |
| Admin capabilities | `docs/requirements/admin.md` | `app/routers/admin.py` |
| User settings / EULA | `docs/features/user-settings-eula.md` | `app/routers/users.py` |
| Test coverage gaps | `docs/testing.md` | `backend/tests/` |
| Environments / staging | `docs/deployment/environments.md` | `docker-compose.build.yml` |
| Phase 2 ideas | `docs/requirements/phase2.md` | **Do not implement unless explicitly directed** |

## Allowed bash patterns

```text
Bash(docker compose *)
Bash(docker cp *)
Bash(conda run *)
Bash(git add *)
Bash(git commit *)
Bash(git push *)
Bash(git pull *)
Bash(git fetch *)
Bash(git checkout *)
Bash(git stash *)
Bash(npx tsc *)
Bash(npm run *)
Bash(gh run *)
Bash(gh pr *)
Bash(curl -s http://localhost:*)
Bash(python -c ' *)
```
