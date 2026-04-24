# Project Status

This file tracks the build status of every feature area. Update it after each tested and committed milestone.

**Last updated:** 2026-04-25

---

## Next 10 Planned Tasks

1. Add Alembic migration smoke test to CI against real Postgres container
2. Add broken import smoke test to CI
3. Add API integration test suite hitting real FastAPI endpoints with test database
4. Activity creation — link project + loom version; enforce one active activity per loom
5. Pick counter — manual increment / decrement of current pick
6. Treadle tracking mode — treadle sequence recording for floor loom workflow
7. Lift tracking mode — per-shaft state for lever loom workflow
8. Session start / pause / resume
9. Activity progress view — current pick, completion %, weft remaining estimate
10. User settings UI — theme toggle, measurement system preference

---

## CI / Dev Process

| Capability | Status | Notes |
| --- | --- | --- |
| Git workflow (main/dev/feature/*) | ✅ | main protected; PRs required from dev |
| Gitea Actions runner | ✅ | Self-hosted ubuntu-latest runner |
| Sequential pipeline (7 stages) | ✅ | smoke → lint → tests → audit → docker → version bump |
| Runner smoke test | ✅ | Sanity check gates all subsequent stages |
| Backend lint (Ruff) | ✅ | Lint + format check; line length 120; alembic excluded |
| Frontend lint (ESLint) | ✅ | TypeScript + react-hooks rules |
| Backend unit tests (pytest) | ✅ | 160 tests; cross-platform font patch via conftest.py |
| Coverage gate (pytest-cov) | ✅ | Fails CI if coverage drops below 19%; configured in pytest.ini |
| Frontend type check (tsc) | ✅ | |
| Dependency vulnerability scan | ✅ | pip-audit (any CVE) + npm audit (high+) |
| Docker build verification | ✅ | Both frontend and backend Dockerfiles validated |
| Semantic version bump | ✅ | PATCH on dev, MINOR on main, MAJOR on breaking change |
| Pre-commit hooks | ✅ | Ruff lint, Ruff format, ESLint, tsc — all run on commit |
| [skip ci] support | ✅ | Docs-only commits skip pipeline |
| UI + API version display | ✅ | Version badge in authenticated UI; /health returns API version |
| Environment lock files | ✅ | environment.yml, requirements-lock.txt, .nvmrc committed and kept in sync |

---

## Legend

| Symbol | Meaning |
| --- | --- |
| ✅ | Built, tested, and committed |
| 🔨 | Partially built or in active development |
| ⏳ | Planned, not yet started |
| 🔮 | Phase 2 — deferred for future work |

---

## Platform Infrastructure

| Capability | Status | Notes |
| --- | --- | --- |
| Docker Compose stack | ✅ | frontend, backend, db, redis, celery worker, authentik |
| Public / internal network isolation | ✅ | db and redis not reachable from host or public net |
| OIDC authentication (Authentik) | ✅ | Full login/callback/logout flow |
| Invite-only registration | ✅ | Admin creates invite → email sent → user logs in via OIDC |
| Bootstrap admin (first user) | ✅ | First user to authenticate becomes admin |
| Session JWT cookie | ✅ | httpOnly, signed with APP_SECRET_KEY |
| User preferences — theme | ✅ | Model field; UI toggle not yet built |
| User preferences — measurement system | ✅ | Model field (metric/imperial/both); display logic not yet built |
| Swagger UI (debug mode only) | ✅ | Available at /api/docs when DEBUG=true |

---

## WIF Import

| Capability | Status | Notes |
| --- | --- | --- |
| WIF file upload | ✅ | Multipart form, stored to uploads volume |
| WIF linting (errors + warnings) | ✅ | Independent configparser-based linter |
| WIF metadata extraction | ✅ | Shafts, treadles, threads, feature flags |
| Design preview rendering | ✅ | PyWeaving → PNG via Pillow (Pillow 10 compat patch applied) |
| Project list view | ✅ | Card grid with metadata summary |
| Project detail view | ✅ | Lint results, feature table, preview image |
| Project soft delete | ✅ | |
| WIF compatibility tracking (admin) | ⏳ | Record which software/versions produce valid WIF files |

---

## Design Preview

| Capability | Status | Notes |
| --- | --- | --- |
| Drawdown preview image | ✅ | Served from backend, displayed on project detail |
| Liftplan alternative rendering | ⏳ | PyWeaving supports it; endpoint not wired up |
| Zoom / pan in browser | ⏳ | |
| Color simulation | ⏳ | |
| Repeat view | ⏳ | |
| Threading / tieup / treadling diagrams | ⏳ | Separate render views |

---

## Equipment Inventory

| Capability | Status | Notes |
| --- | --- | --- |
| Loom create | ✅ | Simple form; loom type selector |
| Loom list | ✅ | Card grid linking to detail |
| Loom detail view | ✅ | Identity, purchase info, activity tracking flags |
| Loom edit | ✅ | Edit modal — all fields including purchase info |
| Loom soft delete | ✅ | |
| Loom types | ✅ | floor_loom, table_loom, rigid_heddle, inkle, other |
| Loom profile photo | ✅ | Upload / replace / remove |
| Versioned configuration history | ✅ | Append-only versions with effective date |
| Configuration version — add | ✅ | Fields shown/hidden by loom type |
| Configuration version — shafts / treadles / heddles | ✅ | All nullable; 0 treadles valid |
| Configuration version — weaving width + warp waste | ✅ | Per-field unit (cm or in); mixed units supported |
| Configuration version — photos | ✅ | Multiple per version; upload / delete |
| Configuration version — receipts / documents | ✅ | Multiple per version (image or PDF); label + view inline |
| Measurement system display conversion | ⏳ | Store with unit; display in user's preferred unit |

---

## Activities (Core Feature)

| Capability | Status | Notes |
| --- | --- | --- |
| Activity creation | ⏳ | Links project + loom version; one active activity per loom |
| Pick counter (manual) | ⏳ | Increment / decrement current pick |
| Lift tracking mode | ⏳ | Per-shaft state; lever loom workflow |
| Treadle tracking mode | ⏳ | Treadle sequence recording; floor loom workflow |
| Bluetooth pedal input | ⏳ | Keyboard emulator; maps pedal presses to UI actions |
| Step correction / undo | ⏳ | |
| Session start / pause / resume | ⏳ | |
| Activity progress view | ⏳ | Current pick, completion %, weft remaining estimate |
| Jump to pick (manual) | ⏳ | |
| Multiple activities per project | ⏳ | Old activities retained when new WIF uploaded |
| Activity soft delete | ⏳ | |
| Tablet / mobile optimised UI | ⏳ | Portrait-first layout for loom-side use |

---

## Yarn Inventory

| Capability | Status | Notes |
| --- | --- | --- |
| Yarn / colorway record | ⏳ | |
| Skein-level tracking with unique IDs | ⏳ | |
| Consumption estimate from WIF data | ⏳ | |
| Inventory deduction as project progresses | ⏳ | |
| Low stock alerts | ⏳ | |

---

## Reports

| Capability | Status | Notes |
| --- | --- | --- |
| Warping plan | ⏳ | From WIF threading data |
| Tie-up sheet | ⏳ | |
| Session log | ⏳ | Picks per session, time on loom |
| Full activity report (PDF) | ⏳ | |

---

## Sharing & Profiles

| Capability | Status | Notes |
| --- | --- | --- |
| Project sharing via slug URL | ⏳ | No account required for viewers |
| Revocable share links | ⏳ | |
| Public project view (read-only) | ⏳ | |
| User profile page | ⏳ | |

---

## Admin

| Capability | Status | Notes |
| --- | --- | --- |
| Invite creation + email delivery | ✅ | SMTP2Go; configurable expiry |
| Invite list and revocation | ✅ | |
| WIF compatibility record tracking | ⏳ | Log software + version for each uploaded file |
| Platform health monitoring | ⏳ | |

---

## Phase 2 (Deferred)

| Capability | Notes |
| --- | --- |
| Third-party API access (API keys) | Personal named keys — `ws_<hex>` format, scoped, hashed, revocable; Bearer token on all `/api/*` routes. Full spec in phase2.md. |
| Offline session caching | Cache current activity for use without internet; sync on reconnect |
| Append-only event log for activity steps | Foundation for offline sync and audit history |
| S3 / object storage backend | `STORAGE_BACKEND` setting already planned in config |

---

## Build Order (Remaining Work)

The planned sequence for upcoming development:

1. **Activities** — core pick-tracking feature; the primary reason the platform exists
2. **User settings UI** — theme toggle, measurement system preference (model fields already exist)
3. **Yarn inventory** — track materials consumed by activities
4. **Reports** — warping plan and activity PDF export
5. **Sharing** — project slug sharing
6. **Admin tools** — WIF compatibility tracking, monitoring
7. **Design preview enhancements** — zoom, liftplan, threading diagrams
8. **Phase 2** — offline caching, event log, S3 storage
