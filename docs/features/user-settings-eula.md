# User Settings & EULA — Implementation Plan

**Issues:** #9 (user settings UI), #46 (EULA / Terms of Service)
**Branch:** `feature/user-settings-eula`
**Status:** In progress

---

## Overview

Two related features shipped together because EULA acceptance state is surfaced in user settings, and account deletion is required for the EULA decline flow.

1. **EULA acceptance gate** — every authenticated user must accept the current EULA version before using the platform. If the EULA changes, they are prompted again on next login.
2. **User settings page** — `/settings` route covering appearance, privacy, account management, and terms info.

---

## Architecture decisions

### EULA versioning

EULA version is a string constant (`CURRENT_EULA_VERSION = "1.0"`) in `backend/app/routers/users.py`. Updating the EULA means:
1. Edit `docs/eula.md` and the embedded content in `EulaContent.tsx`
2. Bump the constant (e.g. `"1.0"` → `"1.1"`)
3. Deploy — all users are prompted to re-accept on next request

The current version is included in the `/auth/me` response as `current_eula_version`. The accepted version is stored per-user as `eula_accepted_version`. The frontend compares them.

**Why not a DB table for EULA versions?** Overkill for a hobby platform. The code constant is the source of truth; the git history records what each version said.

### EULA gate placement

`EulaGate` wraps the entire `ProtectedRoute` tree in `App.tsx`. When the user is authenticated but `user.eula_accepted_version !== user.current_eula_version`, the gate replaces all page content with the EULA acceptance screen. The EULA screen shows:
- Full EULA text (scrollable)
- Accept button
- "I do not accept" section with account deletion warning and delete button

### Account deletion

Synchronous hard-delete on the backend endpoint `DELETE /api/users/me`. Steps:
1. Collect all S3 file paths for the user (activity photos, loom photos, version photos, version receipts, yarn photos, project WIF + preview)
2. Delete each from S3/local storage (best-effort — storage errors are logged but do not abort)
3. Delete DB rows in FK-safe order using bulk `DELETE ... WHERE owner_id = :user_id` statements
4. Hard-delete the user row
5. Clear session cookie in response

**Why synchronous?** User data is unlikely to be large enough to exceed a request timeout, and immediate deletion is better for user trust than a queued job. If a future user has an unusually large dataset, we can revisit with a background worker then.

### Data export (Phase 2)

`GET /api/users/me/data-export` returns `{"status": "not_implemented", "milestone": "2"}`. Building a data archive requires async work (zip WIF files, photos, activity history) that warrants a Celery task. Stub is present so the frontend can show the option with a Phase 2 note.

### Data sharing / privacy

The existing `ai_training_consent` field (default `False`) is repurposed in the UI as the "Allow platform to use my data" toggle. When `False`:
- Data is NOT used for AI training or platform analytics
- Sharing slugs and public profile pages are disabled (enforced server-side at sharing endpoints)

Users are warned with an explicit confirmation dialog when toggling this off, explaining that their shared project links will stop working.

### User preference fields (new)

| Field | Type | Default | Notes |
|---|---|---|---|
| `eula_accepted_version` | `str \| None` | `null` | Version string last accepted |
| `eula_accepted_at` | `datetime \| None` | `null` | Timestamp of last acceptance |
| `activity_theme` | `str \| None` | `null` | Activity tracker visual theme |

Existing fields now surfaced in settings UI:
- `theme` (light / dark)
- `measurement_system` (metric / imperial)
- `idle_timeout_minutes`
- `ai_training_consent`

---

## File map

### Backend

| File | Change |
|---|---|
| `app/models/user.py` | Add `eula_accepted_version`, `eula_accepted_at`, `activity_theme` |
| `alembic/versions/0016_user_settings_eula.py` | Migration for new columns |
| `app/routers/users.py` | **New** — settings PATCH, EULA accept, account delete, data export stub |
| `app/routers/auth.py` | Add new fields to `UserResponse` |
| `app/main.py` | Register users router |

### Frontend

| File | Change |
|---|---|
| `src/api/users.ts` | **New** — settings update, EULA accept, account delete API calls |
| `src/context/AuthContext.tsx` | Extend `User` type with new fields |
| `src/components/EulaGate.tsx` | **New** — gate component wrapping authenticated routes |
| `src/components/EulaContent.tsx` | **New** — EULA text as JSX |
| `src/pages/SettingsPage.tsx` | **New** — full settings page |
| `src/App.tsx` | Add `/settings` route; wrap protected routes with `EulaGate` |

### Docs

| File | Notes |
|---|---|
| `docs/eula.md` | Canonical EULA text (v1.0) — plain language |
| `docs/features/user-settings-eula.md` | This document |

---

## Settings page layout

```
/settings

  Appearance
    Theme                [Light / Dark] toggle
    Activity tracker     [Default / Compact / High contrast] select

  Account preferences
    Display name         text input
    Measurement system   [Metric / Imperial] toggle
    Session idle timeout [15 / 30 / 60 / 120 min] select

  Privacy & data
    Data use consent     toggle (default off)
    * warning: turning off also disables all shared project links

  Terms
    WeftMark Terms of Service v1.0 — Accepted [date] / Not yet accepted
    [Read Terms] button

  Account management
    [Download my data]   button (Phase 2 — shows note)
    [Delete my account]  danger zone — requires typed confirmation
```

---

## API contracts

### `PATCH /api/users/me`
```json
{
  "display_name": "string | null",
  "theme": "light | dark | null",
  "activity_theme": "string | null",
  "idle_timeout_minutes": "integer | null",
  "measurement_system": "metric | imperial | null",
  "ai_training_consent": "boolean | null"
}
```
Returns updated `UserResponse` (same shape as `/auth/me`).

### `POST /api/users/me/eula`
```json
{ "version": "1.0" }
```
Returns updated `UserResponse` with `eula_accepted_version` set.

### `DELETE /api/users/me`
Body: `{ "confirm": "DELETE MY ACCOUNT" }` — exact string required as safety check.
Response: `204 No Content` + clears session cookie.

### `GET /api/users/me/data-export`
Response: `{ "status": "not_implemented", "milestone": "2" }` (Phase 2 stub).

---

## `UserResponse` additions

```python
class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    theme: str
    activity_theme: str | None
    idle_timeout_minutes: int
    measurement_system: str
    ai_training_consent: bool
    eula_accepted_version: str | None
    current_eula_version: str        # constant from users router
```

---

## Migration notes (0016)

```sql
ALTER TABLE users ADD COLUMN eula_accepted_version VARCHAR(20);
ALTER TABLE users ADD COLUMN eula_accepted_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN activity_theme VARCHAR(50);
```

All nullable — existing users simply haven't accepted the new EULA yet and will be prompted on next login.

---

## Phase 2 notes

- **Data export**: `GET /api/users/me/data-export` should enqueue a Celery task that packages WIF files, preview images, activity photos, and a JSON data dump into a zip, then emails a download link or stores it for 24 hours. Requires Celery worker infrastructure (#48 CD pipeline work).
- **Apple Sign In**: OIDC infrastructure is already in place. Requires paid Apple Developer account. See #65.
- **Sharing slug enforcement**: When `ai_training_consent = False`, the draft sharing endpoint (`/api/drafts/{id}/share`) should return 403. Currently a frontend-only gate — needs server-side enforcement in the drafts router.
