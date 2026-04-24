# Phase 2 Features

Features deferred from the initial build. Noted here to ensure architectural decisions in Phase 1 do not foreclose these options.

---

## Third-Party API Access (API Keys)

**Description:** Allow authenticated access to the backend API from third-party applications — Android companion apps, Home Assistant integrations, scripts, and other tooling — without requiring the OIDC browser flow.

### Recommendation: Personal API keys (not OAuth)

OAuth 2.0 authorization code flow solves the problem of *App A acting on behalf of User B with User B's consent*. That is not this use case. Here, the user is likely also the developer of their own Android app or automation script. API keys solve the problem directly and are simpler for developers to consume.

If a public third-party app ecosystem develops (someone else building a commercial app that accesses user data), OAuth PKCE should be evaluated at that point. That is effectively Phase 3.

**Key design:**

| Property | Behaviour |
| --- | --- |
| Format | `ws_<64 hex chars>` — prefix makes keys machine-identifiable and scannable by secret-leak detection tools |
| Creation | User creates a named key in account settings with an optional expiry date and scope |
| Scopes | `read` (GET only) and `read-write` (all methods); additional granularity can be added later |
| Storage | Only the SHA-256 hash is stored; the raw key is shown exactly once at creation and is not recoverable |
| Transmission | `Authorization: Bearer ws_...` header |
| Endpoint compatibility | All existing `/api/*` routes accept either session cookie (web) or Bearer token (API key) — no parallel API surface needed |
| Revocation | User can list, revoke, and re-create keys at any time from account settings |
| Expiry | Optional per-key expiry date; expired keys are rejected with 401 |
| Rate limiting | Per-key rate limiting enforced at the nginx or backend layer |

**Security practices:**

- Keys are never logged, returned in responses (after initial creation), or stored in plaintext
- HTTPS enforced end-to-end (nginx terminates TLS; no plain HTTP in production)
- Failed authentication attempts are logged with key prefix only (never full key)
- Keys should be treated as secrets equivalent to passwords — users should be informed not to commit them to version control

**Architectural note for Phase 1:** The `get_current_user` dependency in `app/deps.py` already extracts the session from a cookie. Phase 2 extends this to also accept a Bearer token, checks the SHA-256 hash against the `api_keys` table, and validates expiry and scope. No other route logic changes.

**Android app guidance:** Android companion apps should store the API key in Android Keystore (encrypted credential storage), not in SharedPreferences or hardcoded in the APK. The key should be entered by the user on first launch via a settings screen, not embedded at build time.

---

## Offline Session Caching

**Description:** Allow the activity step tracker to continue functioning when the user loses internet connectivity at the loom. Unsynced picks are queued locally and replayed to the server when connectivity is restored.

**Architectural note:** The activity step log should be designed as an append-only event log (not mutable state) in Phase 1. This makes adding a sync queue in Phase 2 straightforward.

**UI requirement:** A persistent sync status indicator showing online/offline state, unsynced pick count, and last successful sync timestamp.

**Scope:** Active session caching only. The rest of the platform (browsing projects, inventory, etc.) continues to require internet.

---

## Notifications

**Description:** Platform notifications for user-relevant events.

**Potential notification types:**

- Invitation accepted / account created
- Shared link viewed (optional — user may not want this)
- Activity milestone reached (e.g. 50% complete)
- Admin alerts for platform health events

**Delivery channels to evaluate:** In-app, email.

---

## Project Picker — Preview and Summary

**Description:** When selecting a WIF project in the Create Activity modal, show a preview image and basic summary (shaft count, treadle count, warp/weft thread counts, available activity types) alongside the project name dropdown. Helps the weaver confirm they've selected the right design before starting.

**Scope:** Read from data already stored on the `Project` record at upload time — no additional parsing required. Preview image served from the existing `/api/projects/{id}/preview` endpoint.

---

## Yarn Inventory — Spoolman Integration

**Description:** Optional integration with an external Spoolman instance, allowing users who already run Spoolman to import their yarn inventory rather than re-entering it.

**Note:** The built-in yarn inventory (Phase 1) should use a data model compatible with Spoolman's structure to make this integration feasible.

---

## End User License Agreement (EULA)

**Description:** Generate and display a platform EULA that users must accept before using the platform. The EULA should cover:

- Ownership of uploaded content (user retains ownership of their WIF files and project data)
- Platform's permitted uses of user data
- Data retention and deletion policy
- Limitation of liability
- AI/ML data use disclosure (see below)

**Implementation notes:**

- Store EULA version and user acceptance timestamp on the `User` record
- On login, if the current EULA version is newer than the user's accepted version, redirect to an acceptance screen before proceeding
- Admin users should be able to update the EULA text and bump the version without a code deploy (stored in the database, not hardcoded)

---

## AI Training Data Disclosure and Opt-Out

**Description:** Disclose to users that uploaded files (WIF files, project data, activity data) may be used for AI/ML training and development purposes. Provide a meaningful opt-out that is enforced at the data pipeline level.

**User-facing requirements:**

- Disclosure shown during registration and in account settings
- Per-user opt-out toggle: "Do not use my projects or activities for AI/ML training"
- Opt-out is retroactive — previously uploaded data is excluded if the user later opts out
- Opted-out users receive a confirmation and can opt back in at any time

**Data access controls:**

- Admin, worker, and internal service accounts are excluded from contributing to training datasets regardless of their opt-in status — only end-user data from opted-in accounts may be used
- The training data export pipeline must filter by: `User.ai_training_consent = True AND User.is_admin = False AND User.is_system = False`
- Data used for training must be anonymised or pseudonymised before leaving the platform database

**Architectural note for Phase 1:** Add `ai_training_consent: bool = False` to the `User` model now, defaulting to opt-out. This costs nothing and avoids a migration later. The actual data pipeline is Phase 2.

---

## Project Tagging

**Description:** Allow users to tag projects with descriptive labels such as "houndstooth", "twill", "plain weave", "floats", "overshot", etc. Tags help with search, filtering, and feed into the automatic tag suggestion system (see below).

**Data model:**

- `Tag` table: `id`, `name` (unique, normalised lowercase), `created_at`
- `ProjectTag` join table: `project_id`, `tag_id`, `created_by` (user or system), `confidence` (null for manual, 0–1 float for AI-suggested)
- Tags are global across all users (one canonical "twill" tag, not per-user)

**UI:**

- Tag input on the project detail page — typeahead from existing tags, free-entry to create new ones
- Tags displayed as chips/badges on project list and detail views
- Filter projects by tag in the project list

**Moderation:** Admins can merge, rename, or delete tags. Deleted tags are removed from all projects.

---

## Automatic Tag Suggestion (ML)

**Description:** Use the corpus of manually tagged projects and their WIF files to train a model that proposes tags for newly uploaded designs. Proposed tags are shown to the user for acceptance or rejection before being applied.

**Inputs to the model:**

- WIF structural data: shaft count, treadle count, threading sequence, tieup matrix, treadling sequence
- Derived features: drawdown bitmap, float lengths, repeat period, symmetry metrics

**Training data pipeline:**

- Only includes projects from users who have opted in to AI training (see AI Training Data Disclosure above)
- Tagged by the owning user or confirmed by an admin
- Minimum confidence threshold before a tag is shown as a suggestion (e.g. 0.7)

**User experience:**

- After upload, if the model has sufficient confidence, show suggested tags with a "Accept / Reject" UI
- User-rejected suggestions are fed back as negative training examples
- Accepted suggestions are stored with `confidence` set to the model score and `created_by = system`

**Architectural notes:**

- Model training runs offline (not on the application server); a versioned model artifact is deployed separately
- Inference can run synchronously at upload time (WIF parsing is already synchronous) or as a Celery task if latency becomes a concern
- The Celery worker infrastructure from Phase 1 is the natural home for inference tasks
