# Test Coverage and Gaps

**Current overall coverage: 90.00%** (2692 tests, last measured 2026-05-25 — see History for recent versions)

> **Coverage regression note:** The 86% figure from v0.85.0 was measured against the `tests/` directory only. It has since been discovered that `app/weaving/tests/` (self-contained weaving unit tests) was not in `testpaths` and those test files were not being run. The 75.52% reflects all 1730 tests (including `app/weaving/tests/`) against the full `app/` source tree.

> **Note:** Prior measurements (~65%) were significantly undercounted. SQLAlchemy async sessions use greenlets internally; coverage.py lost `sys.settrace` after every `await db.scalar()/commit()` call, causing all post-await lines in every router to appear uncovered. Fixed in commit `47311ca` by adding `[coverage:run] concurrency = greenlet` in `backend/setup.cfg`.

---

## Coverage by Module

| Module | Coverage | Notes |
| --- | --- | --- |
| `app/config.py` | 98% | One branch in `database_url` construction |
| `app/database.py` | 100% | |
| `app/deps.py` | 79% | `get_db`, `get_current_user`, `require_admin` covered; soft-deleted user path missing |
| `app/main.py` | 90% | Lifespan OIDC call mocked |
| `app/models/project.py` | 100% | Includes `ProjectPhoto` model |
| `app/models/base.py` | 87% | `soft_delete()` line covered; `is_deleted` property line 23 |
| `app/models/invite.py` | 95% | |
| `app/models/loom.py` | 99% | |
| `app/models/draft.py` | 100% | |
| `app/models/user.py` | 100% | Defaults, soft delete, all fields covered |
| `app/models/yarn.py` | 100% | |
| `app/routers/projects.py` | 97% | 9 missing: error branches (treadle/lift validation, loom version), picks endpoint edge case |
| `app/routers/auth.py` | 81% | `/me`, logout, token validation, invite flow, webhook handlers covered; OIDC callback not tested |
| `app/routers/health.py` | 78% | `/health` covered; DB-down error branches not tested |
| `app/routers/admin.py` | 72% | Most admin CRUD covered; Clerk API integration paths missing |
| `app/routers/looms.py` | 97% | 9 missing: photo replace + file-size error branches |
| `app/routers/drafts.py` | 93% | 14 missing: `file_too_large`, preview happy path, liftplan edge case |
| `app/routers/yarn.py` | 99% | 3 missing: file-size error branches |
| `app/routers/users.py` | 98% | 3 missing: edge cases in account deletion |
| `app/services/email.py` | 84% | |
| `app/services/rendering.py` | 98% | |
| `app/services/storage.py` | 89% | |
| `app/routers/logs.py` | 100% | Client log relay — all paths covered |
| `app/services/storage_quota.py` | 100% | Quota check and exceeded branch covered |
| `app/services/wif_linter.py` | 96% | |
| `app/services/wif_modifier.py` | 100% | |
| `app/services/wif_parser.py` | 100% | |
| `app/version.py` | 86% | `__main__` block not tested |
| `app/cli.py` | 63% | Seeding CLI paths not tested |
| `app/services/clerk.py` | 23% | Clerk API calls not tested (no Clerk mock) |

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

All core router paths are now covered. Remaining gaps are edge cases and third-party integration paths.

### Medium priority — error branches

| Gap | Module | Lines | Notes |
| --- | --- | --- | --- |
| Clerk API integration | `services/clerk.py` | 77% missing | Would need Clerk mock; not worth the complexity |
| Admin OIDC callback + user sync | `routers/admin.py` | 28% missing | Requires Clerk webhook mock |
| Health endpoint DB-down branch | `routers/health.py` | `158-176`, `188-221` | Simulate DB unavailable → 500 |
| Draft file-too-large (25MB check) | `routers/drafts.py` | `85` | Monkeypatch MAX_WIF_SIZE |
| Loom photo replace path | `routers/looms.py` | `402`, `405-408` | Upload photo when one already exists |

### Low priority / deferred

| Gap | Notes |
| --- | --- |
| `app/cli.py` | Seeding CLI — not practical to unit test |
| `app/version.py` `__main__` block | Only runs via `python -m app.version` |
| `app/services/clerk_auth.py` | Clerk auth wrapper — would need Clerk mock |

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
- A new feature area is added (Projects, Yarn, Reports, Sharing, etc.)
- A router reaches ≥80% coverage (evaluate if remaining gaps matter)
- Before each Phase 2 feature begins
- After any significant refactor

---

## History

| Date | Version | Coverage | Event |
| --- | --- | --- | --- |
| 2026-04-25 | v0.2.x | 55% | Model imports provide baseline via `app.main` import in conftest |
| 2026-04-25 | v0.2.x | 68% | Added router tests (health) + model tests (User); DB integration test infrastructure in place |
| 2026-04-25 | v0.5.0 | 67% | 266 tests; project creation, restart, clone covered; auth `/me` + token validation added; loom CRUD partially covered |
| 2026-05-03 | v0.74.0 | — | First production deployment smoke test; 63 items tested end-to-end; 11 issues filed (#266–#275); 2 closed (see GitHub issue #277) |
| 2026-05-03 | v0.76.1 | 65% | 823 tests; full rename of Project→Draft model, router, API, and frontend completed (issues #296/#311) |
| 2026-05-05 | v0.85.0 | ~65.3% | 19 new tests added; new modules covered: `logs.py`, `storage_quota.py`, `wif_modifier.py`; 64.78%→65.3% to clear CI gate |
| 2026-05-05 | v0.85.0 | 85.93% | Fixed greenlet coverage tracking (`setup.cfg` `concurrency=greenlet`); prior ~65% numbers were systematic undercounts. 908 tests; 7 new auth webhook unit tests added. |
| 2026-05-15 | v0.145.0 | ~86% | Coverage stable; new features (color replacements, project landing page, reed inventory, tile pre-render) added without regression. |
| 2026-05-18 | v0.145.x | 75.52% | `itc 75` run: fixed testpaths to include `app/weaving/tests/`; added tests for rendering SVG/drawdown/clip functions, weaving Draft methods, `parse_threading`, `parse_tieup`, `task_history`, and `clerk_auth`. 1730 tests, 0 failures. |
| 2026-05-25 | v0.189.0 | 90.00% | `itc 90` run: +962 tests across tasks (preview, tiles, maintenance, s3_audit, feedback_dispatch, purge, reparse), services (wif_parser, wif_linter), and infra (setup.cfg concurrency=thread,greenlet to track asyncio.to_thread closures). 2692 tests, 0 failures. |
