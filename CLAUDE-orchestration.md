# WeftMark Orchestration Repo — Claude Instructions

This repo contains Komodo stack definitions for the WeftMark platform. It follows a
**base + override** pattern: the app's `docker-compose.yml` is pulled from the
[weftmark/weftmark](https://github.com/weftmark/weftmark) repo and is infrastructure-agnostic.
This repo layers Traefik routing on top via `docker-compose.override.yml` files.

---

## How the override pattern works

Docker Compose automatically merges `docker-compose.yml` + `docker-compose.override.yml`
when both are present in the same directory (or when passed with `-f`). Keys in the
override are deep-merged on top of the base — the base file is never modified.

Komodo points each stack at a directory containing both files. The base compose is
fetched from the app repo (via Komodo's Git sync or a file reference); the override
lives here in the orchestration repo.

---

## Stack structure

Each stack gets a directory with two files:

```
stacks/
  prod/
    docker-compose.override.yml   ← Traefik labels + network for prod
    .env                          ← stack env vars (gitignored — set secrets in Komodo UI)
  dev/
    docker-compose.override.yml   ← Traefik labels + network for dev
    .env
```

---

## Override file anatomy

Every override file follows this template. Copy and adapt for a new stack:

```yaml
services:
  frontend:
    networks:
      - traefik_proxy
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.${STACK_NAME}.rule=${TRAEFIK_HOST_RULE}"
      - "traefik.http.routers.${STACK_NAME}.entrypoints=websecure"
      - "traefik.http.routers.${STACK_NAME}.tls.certresolver=cloudflare"
      - "traefik.http.services.${STACK_NAME}.loadbalancer.server.port=80"

networks:
  traefik_proxy:
    external: true
    name: traefik_proxy
```

**Required env vars** (set in Komodo stack environment or the stack's `.env`):

| Variable | Example (prod) | Example (dev) |
|---|---|---|
| `STACK_NAME` | `weftmark` | `weftmark-dev` |
| `TRAEFIK_HOST_RULE` | `Host(\`weftmark.com\`) \|\| Host(\`www.weftmark.com\`)` | `Host(\`dev.weftmark.com\`)` |
| `IMAGE_TAG` | `latest` | `dev` |

`STACK_NAME` is also used by the base compose for container names, network names, and
volume names — keep it unique per stack so prod and dev can coexist on the same host.

---

## Existing stacks

### prod (`stacks/prod/`)
- **URL:** `weftmark.com`, `www.weftmark.com`
- **Image tag:** `latest`
- **Stack name:** `weftmark`
- **Backend env:** managed via Komodo secrets (Neon Postgres, Cloudflare R2, Clerk live keys)

### dev (`stacks/dev/`)
- **URL:** `dev.weftmark.com`
- **Image tag:** `dev`
- **Stack name:** `weftmark-dev`
- **Backend env:** managed via Komodo secrets (Neon Postgres dev branch, R2 dev bucket, Clerk test keys)

---

## Adding a new stack

1. Create `stacks/<name>/docker-compose.override.yml` from the template above.
2. Set `STACK_NAME` to a unique value — it prefixes all container/network/volume names.
3. Set `TRAEFIK_HOST_RULE` to the full Traefik `Host()` expression for the domain.
4. Add the stack in Komodo pointing at this repo + the app repo's `docker-compose.yml`.
5. Configure secrets in the Komodo UI (never commit real `.env` files).

---

## Modifying Traefik routing

To change a hostname, add middleware, or adjust TLS config, edit the relevant
`docker-compose.override.yml`. All Traefik label changes take effect on the next
`docker compose up` / Komodo redeploy — Traefik watches for label changes via the
Docker provider and hot-reloads without downtime.

Common label additions:

```yaml
# Redirect www → apex
- "traefik.http.middlewares.www-redirect.redirectregex.regex=^https://www\\.(.+)"
- "traefik.http.middlewares.www-redirect.redirectregex.replacement=https://$${1}"
- "traefik.http.routers.weftmark.middlewares=www-redirect"

# Rate limiting
- "traefik.http.middlewares.ratelimit.ratelimit.average=100"
- "traefik.http.routers.weftmark.middlewares=ratelimit"
```

---

## What NOT to change here

- Application config (env vars for Postgres, Clerk, Redis, S3) — those belong in the
  Komodo stack environment or the app repo's `.env.example`.
- The Traefik daemon config (`traefik.yml`, `dynamic.yml`, ACME storage) — those live
  in the `traefik/` stack if one exists in this repo, or on the host directly.
- Image build definitions — those are in the app repo's `docker-compose.build.yml`.
