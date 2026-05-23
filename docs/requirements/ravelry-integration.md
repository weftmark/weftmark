# Ravelry Integration

**Issue:** #831  
**Related:** #48 (superseded), #776 (superseded)  
**Branch:** `feat/ravelry-integration`

## Summary

Integrate with the Ravelry API to make a user's Ravelry stash the primary yarn data source in weftmark. Users who connect their Ravelry account get a synced stash view; the existing local yarn model acts as the cache layer. Users without Ravelry continue to see a "connect" prompt where yarn would otherwise appear.

## Why Ravelry supersedes #48 and #776

- **#48** (yarn stash management) — Ravelry stash covers this entirely. weftmark's role shifts to providing a weaving-focused view of data Ravelry already owns.
- **#776** (manufacturer/colorway seed database) — Ravelry's yarn database already carries manufacturer, colorway, fiber, and yardage data with much greater coverage than we could seed manually.

## Architecture

### OAuth per user (authorization code flow)

- weftmark registers as a Ravelry Pro app and receives a `client_id` / `client_secret`
- Per-environment redirect URIs: `{FRONTEND_URL}/settings/connections/ravelry/callback`
- Required scope: `offline stash-read stash-write`
- Env vars (one set per environment):
  - `RAVELRY_OAUTH_CLIENT_ID`
  - `RAVELRY_OAUTH_CLIENT_SECRET`
  - `RAVELRY_OAUTH_REDIRECT_URI` — full callback URL, e.g. `https://app.weftmark.com/settings/connections/ravelry/callback`

### Backend

#### `ravelry_credentials` table (new)

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `user_id` | UUID FK → users | unique |
| `ravelry_username` | varchar(100) | needed for stash API calls |
| `access_token` | text | encrypted at rest (future) |
| `refresh_token` | text nullable | |
| `expires_at` | timestamptz nullable | |
| `stash_etag` | varchar(255) nullable | ETag from last stash sync |
| `stash_last_synced_at` | timestamptz nullable | |
| `created_at` / `updated_at` | timestamptz | |

#### `yarns` table — new columns

| Column | Type | Notes |
| --- | --- | --- |
| `ravelry_stash_id` | bigint nullable | Ravelry stash entry ID |
| `out_of_stash` | bool default false | Set by sync when Ravelry removes the entry from stash |
| `archived` | bool default false | User-managed or auto-set when `out_of_stash` becomes true; hidden from default list view |

**Removal policy:** yarns removed from the Ravelry stash are never deleted. They are marked `out_of_stash = True, archived = True` so project references and weaving history are preserved. If the user re-adds the yarn to their stash, both flags are cleared on the next sync.

**Delete guard:** before any hard deletion of a yarn, the backend must check for project references. If any exist, only archive is permitted — deletion is blocked.

#### API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/ravelry/authorize` | Returns Ravelry OAuth authorization URL with state |
| `GET` | `/api/ravelry/callback` | Exchanges code, stores tokens, redirects to `/settings/connections` |
| `DELETE` | `/api/ravelry/connection` | Revoke + delete stored credential |
| `GET` | `/api/ravelry/status` | Returns `{connected, ravelry_username, last_synced_at}` |
| `POST` | `/api/ravelry/sync` | Force-sync stash now (ETag-aware) |

#### Stash sync flow

1. Call `GET https://api.ravelry.com/people/{username}/stash/list.json` with `If-None-Match: <etag>`
2. If 304 — no changes, return early
3. If 200 — upsert `Yarn` records by `ravelry_stash_id`, update ETag and `stash_last_synced_at`
4. Map Ravelry fields → `Yarn` columns:
   - `yarn.yarn_company.name` → `brand`
   - `yarn.name` → `name`
   - `colorway_name` → `color_name`
   - `color_family_name` → `color_hex` (approximate, via built-in color family map; only written if `color_hex` is currently null — non-null is treated as a user override)
   - `yarn.yarn_weight.name` → `weight_category`
   - `yarn.fiber_content` → `fiber_content`
   - `total_skeins` count → reconcile `Skein` records (status `available`)
5. For yarns no longer in the API response: set `out_of_stash = True, archived = True` — never delete

**Color hex strategy:** Ravelry provides color family tags ("Red", "Blue", "Brown") but not hex values. The sync maps these to representative mid-tone hex values. Users can override per-yarn in the detail view; once overridden, sync will not overwrite the hex.

**ETags stored in Postgres** (`stash_etag` on `ravelry_credentials`). No Redis needed — the stash data itself is the cache, and the ETag is a single string tied to the credential record.

**Sync trigger:** on-demand only for the POC — on yarn page load and via "Sync now" button. Periodic background sync (Celery beat) deferred to a follow-on.

Token refresh: check `expires_at` before each API call; if expired or within 60 seconds, exchange refresh token and update the credential.

### Frontend

#### Settings → Connections (`/settings/connections`)

New settings section surfaced in the sidebar under Settings sub-nav. Shows:

- Ravelry connection card: username + last sync, or "Connect" CTA if not connected
- Connect flow: redirect to Ravelry authorization page
- Disconnect: confirmation prompt, then DELETE credential

#### Yarn page (`/yarn`)

- If **not connected**: full-page "connect Ravelry" empty state with CTA linking to `/settings/connections`
- If **connected**: existing list layout; sync runs on page mount (ETag-gated); sub-nav planned for phase 2 (search, link to project, etc.)

#### Sidebar

- Add `{ label: t("nav.yarn"), href: "/yarn", icon: AppIcons.yarn }` to `NAV_ITEMS` (visible to all non-superusers)

#### OAuth callback route

A new frontend route `/settings/connections/ravelry/callback` receives the `code` and `state` params from Ravelry, POSTs them to the backend, and redirects to `/settings/connections` with a success or error toast.

Actually: the OAuth callback is handled server-side by the backend (`GET /api/ravelry/callback`). The backend exchanges the code and redirects the browser to `/settings/connections?ravelry=connected` (or `?ravelry=error`). No frontend route needed — the redirect target is the settings page, which reads the query param to show a toast.

## State / PKCE

Use PKCE with `code_challenge_method=S256`. Generate `code_verifier` in the backend on `/authorize`, store in a short-lived `ravelry_oauth_states` table (or Redis key) keyed by the `state` param, expire after 10 minutes.

## Phase 2 (out of scope for initial PR)

- Sub-nav: stash search, project yarn linking, colorway hex extraction
- Background Celery sync (periodic, not just on-demand)
- Link draft color slots to Ravelry colorway IDs
- Token encryption at rest
