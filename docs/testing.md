# Test Coverage and Gaps

**Current overall coverage: 65%** (823 tests, last measured 2026-05-03 v0.76.1)

---

## Coverage by Module

| Module | Coverage | Notes |
| --- | --- | --- |
| `app/config.py` | 98% | One branch in `database_url` construction |
| `app/database.py` | 100% | |
| `app/deps.py` | 79% | `get_db`, `get_current_user`, `require_admin` covered; soft-deleted user path missing |
| `app/main.py` | 90% | Lifespan OIDC call mocked |
| `app/models/activity.py` | 100% | Includes `ActivityPhoto` model |
| `app/models/base.py` | 87% | `soft_delete()` line covered; `is_deleted` property line 23 |
| `app/models/invite.py` | 95% | |
| `app/models/loom.py` | 99% | |
| `app/models/draft.py` | 100% | |
| `app/models/user.py` | 100% | Defaults, soft delete, all fields covered |
| `app/models/yarn.py` | 100% | |
| `app/routers/activities.py` | 41% | Create, restart, clone covered; detail, update, pick step, photos endpoints not tested |
| `app/routers/auth.py` | 40% | `/me`, logout, token validation covered; OIDC callback, invite flow not tested |
| `app/routers/health.py` | 90% | `/health` covered; error branch (DB down) not tested |
| `app/routers/looms.py` | 58% | Create, list, get covered; versions, photos, documents not tested |
| `app/routers/drafts.py` | 52% | WIF upload, list, detail — gap |
| `app/routers/yarn.py` | 64% | |
| `app/services/email.py` | 100% | |
| `app/services/rendering.py` | 100% | |
| `app/services/storage.py` | 90% | Activity photo helpers (`save_activity_photo`, `delete_activity_photo`) not tested |
| `app/services/wif_linter.py` | 100% | |
| `app/services/wif_parser.py` | 100% | |
| `app/version.py` | 86% | `__main__` block not tested |
| `app/worker.py` | 0% | Celery worker — not tested, low priority |

---

## Test Infrastructure

| Fixture | Location | Purpose |
| --- | --- | --- |
| `setup_database` | `conftest.py` | Session-scoped; creates `test_weaving_site` DB and schema once |
| `db_session` | `conftest.py` | Function-scoped; yields AsyncSession, truncates all tables after each test |
| `test_user` | `conftest.py` | Regular user, `is_admin=False` |
| `admin_user` | `conftest.py` | Admin user, `is_admin=True` |
| `client` | `conftest.py` | Unauthenticated AsyncClient with `get_db` overridden |
| `auth_client` | `conftest.py` | Authenticated as `test_user`; `get_current_user` overridden |
| `admin_client` | `conftest.py` | Authenticated as `admin_user`; `get_current_user` overridden |

**Local DB**: Requires `POSTGRES_PASSWORD` env var; uses docker-compose db exposed at `localhost:5433`.
**CI**: Postgres service in `backend-tests` job; `POSTGRES_HOST=postgres`, `POSTGRES_PORT=5432`.

---

## Coverage Gaps by Priority

### High priority — core application paths

| Gap | Module | Tests needed |
| --- | --- | --- |
| Auth `get_current_user` / `require_admin` | `deps.py` | Request with valid session cookie, expired token, missing token, inactive user |
| Auth `/auth/me` endpoint | `routers/auth.py` | Authenticated request returns user info |
| Auth session cookie set/clear | `routers/auth.py` | Login callback sets cookie; logout clears it |
| Auth invite creation + email | `routers/auth.py` | Admin creates invite; non-admin rejected |
| Draft upload (WIF) | `routers/drafts.py` | Upload valid WIF; upload invalid WIF; access control |
| Draft list + detail | `routers/drafts.py` | List returns user's drafts; detail returns correct data |
| Loom CRUD | `routers/looms.py` | Create, read, update, delete loom; access control |
| Loom version create | `routers/looms.py` | Add version with fields; shaft/treadle validation |

### Medium priority — secondary flows

| Gap | Module | Tests needed |
| --- | --- | --- |
| Activity detail, update, pick step | `routers/activities.py` | Create/restart/clone covered; remaining endpoints need tests |
| Activity photo endpoints | `routers/activities.py` | Upload, list, delete photos — no tests yet |
| Yarn CRUD | `routers/yarn.py` | Basic CRUD coverage |
| Health endpoint — DB error | `routers/health.py` | Simulate DB unavailable → 500 |
| `deps.py` full coverage | `deps.py` | Invalid JWT, user not found, soft-deleted user |

### Low priority / deferred

| Gap | Notes |
| --- | --- |
| `app/worker.py` | Celery setup; not worth unit testing |
| `app/version.py` `__main__` block | Only runs via `python -m app.version` |
| OIDC full flow | Requires mocking httpx calls to Authentik; deferrable |

---

## Test-First Process

Before implementing any new feature:

1. **Scope tests** — identify what endpoints/models/behaviours the feature adds
2. **Write tests** — add to `tests/routers/` or `tests/models/` as appropriate
3. **Run tests** — confirm they fail (they should, feature not built yet)
4. **Implement feature** — write code until all tests pass
5. **Commit** — feature + tests together; update coverage estimate in this file

---

## Coverage Reassessment Triggers

Reassess coverage completeness when:

- Overall coverage drops below the CI gate (currently 65%)
- A new feature area is added (Activities, Yarn, Reports, Sharing, etc.)
- A router reaches ≥80% coverage (evaluate if remaining gaps matter)
- Before each Phase 2 feature begins
- After any significant refactor

---

## History

| Date | Version | Coverage | Event |
| --- | --- | --- | --- |
| 2026-04-25 | v0.2.x | 55% | Model imports provide baseline via `app.main` import in conftest |
| 2026-04-25 | v0.2.x | 68% | Added router tests (health) + model tests (User); DB integration test infrastructure in place |
| 2026-04-25 | v0.5.0 | 67% | 266 tests; activity creation, restart, clone covered; auth `/me` + token validation added; loom CRUD partially covered |
| 2026-05-03 | v0.74.0 | — | First production deployment smoke test; 63 items tested end-to-end; 11 issues filed (#266–#275); 2 closed (see GitHub issue #277) |
| 2026-05-03 | v0.76.1 | 65% | 823 tests; full rename of Project→Draft model, router, API, and frontend completed (issues #296/#311) |
