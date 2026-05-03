# Environment Strategy — WeftMark

**Decision date:** 2026-05-03

---

## Recommendation: Three Environments, Not Four

A four-stage pipeline (dev → test → staging → prod) is the right model for large teams where different people own different gates. For a solo developer with a small beta, it adds operational overhead without commensurate value. The recommendation here is **three standing environments** with the fourth slot reserved for ephemeral use when you actually need it.

| Environment | URL | Branch | Audience | Data policy |
|---|---|---|---|---|
| **dev** | `dev.weftmark.com` | `dev` | Developer only | Seeded synthetic data |
| **staging** | `staging.weftmark.com` | `main` (RC) | Developer + beta testers | Anonymized prod snapshot |
| **prod** | `weftmark.com` | `main` (released) | Real users | Real data |

The "test" slot becomes a **Neon branch + ephemeral deployment** — created on demand to validate a specific bug against real data, then destroyed. This costs nothing and doesn't require a standing VM or Clerk project.

---

## Infrastructure Per Environment

| Resource | Dev | Staging | Prod |
|---|---|---|---|
| Clerk project | `weftmark-dev` | `weftmark-staging` | `weftmark-prod` |
| R2 bucket | `weftmark-dev` | `weftmark-staging` | `weftmark-prod` |
| Neon database | `weftmark-dev` | branch of prod (see below) | `weftmark-prod` |
| Komodo stack | `weftmark-dev` | `weftmark-staging` | `weftmark-prod` |
| Image tag | `:dev` (ghcr.io) | `:staging` or `:{version}-rc` | `:latest` / `:{version}` |

**Neon database for staging:** Rather than a third standalone database, staging uses a Neon branch created from prod. A branch is a copy-on-write snapshot — it starts with all real prod data and diverges from there. Creating it takes seconds regardless of database size. This is covered in detail in the Data Migration section below.

---

## What Each Environment Is For

### Dev (`dev.weftmark.com`)

- **Owner:** Developer only — no beta testers.
- **Purpose:** Validate that merged features work together. The first place code runs after CI.
- **Data:** Synthetic seed data (`dev_reset.py`). Real email addresses never appear here. Reset freely.
- **Update cadence:** Automatic on every push to `dev` branch via CI (`publish-dev.yml` image + Komodo webhook).
- **Clerk:** Dev project, test mode. Use Clerk's test phone/email to avoid touching real inboxes.
- **Stability expectation:** May be broken mid-feature. That's fine.

### Staging (`staging.weftmark.com`)

- **Owner:** Developer + invited beta testers.
- **Purpose:** Pre-release validation against production-like data. The gate before prod deploy.
- **Data:** Anonymized snapshot of prod (see below). Refreshed before each beta cycle, not continuously.
- **Update cadence:** Manual deploy triggered by you when a release candidate is ready.
- **Clerk:** Staging project, production mode but separate domain. Beta testers get Clerk accounts here that are independent of their prod accounts.
- **Stability expectation:** Should work. If it doesn't, fix before promoting to prod.
- **Key rule:** Staging exists to validate — not to develop. Never use staging as a shortcut for "I need to test something quickly."

### Prod (`weftmark.com`)

- **Owner:** Real users.
- **Purpose:** The live service.
- **Data:** Real data, never read or modified outside normal app operations.
- **Update cadence:** Manual deploy after staging validation.
- **Clerk:** Prod project. This is the source of truth for user identities.
- **Status:** Live as of May 3, 2026 at v0.74.0. Full smoke test passed.

---

## Data Migration

### The Problem

Beta testers need to validate features against their real content — their actual looms, projects, threading sequences. Asking them to recreate weeks of work in a staging environment defeats the purpose.

### Primary Solution: Neon Database Branching

Neon's branching feature is a copy-on-write snapshot of your production database. Creating a branch takes seconds; the branch starts with all prod data and diverges from that point forward. There is no dump, no transfer, no restore.

**Workflow for a staging refresh:**

```
1. In Neon dashboard: create branch "staging-YYYY-MM-DD" from prod main branch
2. Run anonymization script against the new branch (see below)
3. Point staging POSTGRES_DSN to the new branch's connection string
4. Restart staging containers
```

The old staging branch can be deleted — it costs nothing while idle. A new branch before each release cycle ensures staging always reflects current prod state.

**Neon branch limits (free tier):** The free tier supports branching but caps compute hours shared across all branches. If staging branch goes idle frequently (Neon auto-pauses after 5 min), this is not an issue in practice. Monitor usage in the Neon dashboard.

### Clerk ID Remapping (Required)

Prod and staging are separate Clerk projects. The same email address gets a different `clerk_id` in each project. The `users.clerk_id` values in the Neon branch point to prod Clerk IDs — staging Clerk won't recognize them.

**Workflow per beta tester (one-time setup):**

1. Have the tester sign into `staging.weftmark.com` with their normal email. This creates a Clerk account in the staging project.
2. Copy their new staging `clerk_id` from the Clerk staging dashboard.
3. Update the staging database:

   ```sql
   UPDATE users SET clerk_id = '<staging-clerk-id>' WHERE email = 'tester@example.com';
   ```

Their real weaving data is now accessible under their normal login. This does not need to be repeated on every staging refresh — only when the Clerk staging project is wiped.

### Anonymization (When You Have Non-Beta Prod Users)

Anonymization is only necessary once prod contains users who are **not** beta testers. At that point, copying the full prod database to staging exposes those users' names and emails in a less-controlled environment they never consented to.

When that time comes, run an anonymization pass on the Neon branch before remapping beta tester Clerk IDs:

```sql
-- Scrub all non-beta users
UPDATE users SET
  email = 'user_' || id || '@example.com',
  first_name = 'User',
  last_name = id::text,
  clerk_id = 'anon_' || id
WHERE email NOT IN ('betatester1@example.com', 'betatester2@example.com');

UPDATE invitations SET email = 'invite_' || id || '@example.com'
WHERE inviter_id NOT IN (SELECT id FROM users WHERE email LIKE '%@example.com' IS FALSE);
```

Weaving data (looms, projects, tieups, colorways) is not PII and does not need to change.

### R2 Asset Migration

Looms and projects may have photos or preview images stored in R2. After branching the database:

```bash
# Sync prod assets to staging bucket (read-only on prod side)
aws s3 sync s3://weftmark-prod/ s3://weftmark-staging/ --endpoint-url <r2-endpoint>
```

This is a full copy — expensive if the bucket is large. An alternative is to skip asset migration and let staging render broken images; this is often acceptable for functional testing that isn't specifically about photos.

### Self-Service Option: WIF Export/Import

Beta testers who want to bring specific projects from prod to staging can do it themselves:
- Export the project from prod as a WIF file (already supported)
- Import that WIF into staging

This is friction-heavy for large amounts of data but works well for targeted validation ("test this new threading UI against my actual project").

---

## Ephemeral Test Slot (The Fourth Environment)

When you need to reproduce a specific prod bug without affecting staging:

1. Create a Neon branch from prod (seconds).
2. Spin up a test stack in Komodo using the same staging template, pointed at the branch.
3. Reproduce and fix the bug.
4. Destroy the stack and delete the Neon branch.

This is not a standing environment — there's no URL, no Clerk project reserved, no ongoing cost. It exists only while you're working the bug.

You can reserve a Komodo stack template called `weftmark-ephemeral` for this purpose so setup takes minutes, not an hour.

---

## Deployment Flow

### Feature Development

```
feature/* branch
    → CI: lint, typecheck (ci-feature.yml)
    → PR to dev (ci-dev-pr.yml: full suite)
    → merge to dev → auto-deploy to dev.weftmark.com
    → validate on dev (developer only)
```

### Releasing to Staging and Prod

```
dev validates cleanly
    → create Neon staging branch from prod
    → run anonymize_staging.py on branch
    → update staging POSTGRES_DSN
    → deploy :staging image to staging.weftmark.com
    → notify beta testers
    → beta feedback period (days)
    → merge dev → main
    → deploy :latest to weftmark.com
```

### Hotfixes

```
hotfix/* branch from main
    → fix
    → PR to main (ci-hotfix.yml: full suite)
    → validate directly in staging (no dev cycle needed)
    → merge to main → deploy to prod
    → backport PR to dev
```

---

## Beta Tester Experience

### What Beta Testers Get

- A staging account with their real data (looms, projects, colorways) already present — no manual recreation.
- A dedicated URL (`staging.weftmark.com`) that stays stable between release cycles.
- Clear communication about when staging is updated and what to test.

### What Beta Testers Don't Get

- Access to dev. Dev is for development, not feedback collection.
- Guarantee that staging data persists forever. Staging is refreshed before each release cycle; testers should treat it as temporary.

### Communicating Staging Refreshes

Before a staging refresh, warn beta testers that their staging data will reset. Any staging-only data they want to keep should be exported as WIF before the refresh.

---

## CI/CD Image Tags

Extend the existing CI to build a `:staging` image tag:

| Git event | Image tag | Destination |
|---|---|---|
| Push to `dev` | `:dev` | `dev.weftmark.com` via Komodo webhook |
| Manual dispatch | `:staging` or `:{version}-rc` | `staging.weftmark.com` via manual Komodo deploy |
| Push to `main` | `:latest`, `:{version}` | `weftmark.com` via Komodo deploy |

The staging deploy is intentionally manual — you control when beta testers see a new version.

---

## Environment Variables and Secrets

Each environment has a completely isolated `.env` / Komodo secret set:

```
POSTGRES_DSN=<neon-branch-url>
CLERK_PUBLISHABLE_KEY=<staging-clerk-key>
CLERK_SECRET_KEY=<staging-clerk-secret>
S3_BUCKET_NAME=weftmark-staging
ALLOWED_ORIGINS=https://staging.weftmark.com
ENVIRONMENT=staging
```

The `ENVIRONMENT` variable can be used to surface a visible banner in the UI ("Staging — data resets periodically") so beta testers are never confused about which environment they're on.

---

## Summary: What to Build

In priority order:

1. **`backend/scripts/anonymize_staging.py`** — idempotent PII scrub, configurable via env var.
2. **Komodo staging stack template** — clone of prod stack, pointing at staging secrets.
3. **Staging Clerk project + initial beta tester accounts.**
4. **Staging banner in the UI** — a one-line conditional on `ENVIRONMENT != production`.
5. **Komodo ephemeral template** — for on-demand bug reproduction (lower priority, do when you first need it).
6. **R2 asset sync script** — `aws s3 sync` wrapper, optional for initial staging deploys.
