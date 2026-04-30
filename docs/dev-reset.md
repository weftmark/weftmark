# Dev Reset Workflow

Procedures for resetting a WeftMark dev instance to a clean state.
All scripts live in `scripts/` and accept an `--env-file` argument (default: `.env.local`).

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python (project virtualenv active) | asyncpg + boto3 must be importable |
| Docker + Compose | Required for Postgres reset |
| Backend image built | `docker compose build backend` |
| `APP_ENV=dev` in your env file | Scripts abort before destructive ops if not set |

---

## Modes

Every script supports three modes:

| Flag | Behaviour | APP_ENV required |
|---|---|---|
| `--check` | Report current state (read-only) | No |
| `--dry-run` | Show what would be done (read-only) | No |
| *(none)* | Execute the operation | `APP_ENV=dev` |

---

## Quick reference

```bash
# Check state across all three systems
python scripts/dev_reset.py --env-file .env.local --check

# Preview what a full reset would do
python scripts/dev_reset.py --env-file .env.local --dry-run

# Full interactive reset (prompts for confirmation)
python scripts/dev_reset.py --env-file .env.local
```

---

## Workflow: reset from unknown state

Follow these steps when the dev instance is in an unknown or broken state.

### 1 — Check current state

```bash
python scripts/dev_reset.py --env-file .env.local --check
```

This runs the `--check` mode on Clerk, S3, and Postgres and prints a summary
of what each system contains. No changes are made.

### 2 — Stop running containers

```bash
docker compose --env-file .env.local -f docker-compose.build.yml down
```

Stop before clearing to prevent new data from being written mid-reset.

### 3 — Clear each system (or use the orchestrator)

#### Option A — orchestrator (clears all three, requires confirmation)

```bash
python scripts/dev_reset.py --env-file .env.local
```

Prints a state summary, prompts `Type RESET to continue`, then clears Clerk →
S3 → Postgres in that order. Aborts if Clerk fails before touching the others.

#### Option B — individual scripts

Clear each system separately if you only need to reset one:

```bash
# Clerk users
python scripts/clear_clerk.py --env-file .env.local

# S3 objects
python scripts/clear_s3.py --env-file .env.local

# Postgres (downgrade base → upgrade head via Docker)
python scripts/clear_postgres.py --env-file .env.local
```

### 4 — Verify clean state

```bash
python scripts/dev_reset.py --env-file .env.local --check
```

All three systems should report empty.

### 5 — Start containers

```bash
docker compose --env-file .env.local -f docker-compose.build.yml up -d backend redis
```

Start backend and redis. Add `--profile local-db` if using the local Postgres container.

### 6 — Seed (once implemented — see issue #140)

```bash
python -m app.cli seed --config seed.json
```

Creates users in Clerk (email + username + password), waits for webhook confirmation,
then applies roles. See `seed.example.json` for the config format.

---

## Individual script reference

### `clear_clerk.py`

Clears all users from the Clerk instance.

```
python scripts/clear_clerk.py --env-file .env.local [--check | --dry-run]
```

**Requires:** `CLERK_SECRET_KEY` in env file.  
**Rate-limit:** 100ms delay between deletes.

---

### `clear_s3.py`

Clears all objects from the configured S3 bucket.

```
python scripts/clear_s3.py --env-file .env.local [--check | --dry-run]
```

**Requires:** `STORAGE_BACKEND=s3` and S3 credentials in env file.  
**No-op** if `STORAGE_BACKEND=local`.  
**Batch size:** 1000 objects per S3 delete request.

---

### `clear_postgres.py`

Resets the database by running `alembic downgrade base` then `alembic upgrade head`
inside a one-shot backend container.

```
python scripts/clear_postgres.py --env-file .env.local [--check | --dry-run]
  [--db-port PORT]       # host port for local DB (default: 5435 for build.yml)
  [--compose-file FILE]  # override compose file (default: docker-compose.build.yml)
```

**Check mode** requires asyncpg and a reachable database.  
**Run mode** requires Docker and a built backend image.

#### Local DB port reference

| Compose file | Host port |
|---|---|
| `docker-compose.build.yml` | `5435` |
| `docker-compose.dev.yml` | `5434` |
| Neon / managed | set `POSTGRES_DSN_DIRECT` — port flag ignored |

---

### `dev_reset.py`

Orchestrates all three clear scripts in sequence.

```
python scripts/dev_reset.py --env-file .env.local [--check | --dry-run]
  [--db-port PORT]
  [--compose-file FILE]
```

Run mode prompts `Type RESET to continue` before any destructive action.  
Aborts if Clerk clear fails, then continues even if S3 fails (Postgres reset still runs).

---

## Troubleshooting

**`asyncpg` not found during --check**  
Activate the project virtualenv: `conda activate weaving_site`

**`STORAGE_BACKEND=local` and nothing to clear**  
Local file storage (`UPLOAD_DIR`) is not cleared by `clear_s3.py`. Delete the volume manually:
```bash
docker volume rm weaving_site_uploads
```

**Postgres `alembic downgrade base` fails**  
The backend image may be stale. Rebuild:
```bash
docker compose --env-file .env.local -f docker-compose.build.yml build backend
```

**Clerk delete returns 404 or 422**  
User may have been partially deleted already. Re-run `--check` — if the list is now empty, proceed.
