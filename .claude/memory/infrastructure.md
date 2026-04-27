---
name: Infrastructure and hosting preferences
description: User's hosting, DNS, and infrastructure choices and preferences
type: project
---

## DNS and domain registrar

User registers all domains through **Cloudflare** (dash.cloudflare.com -> Registrar).

**Implications:**

- Check domain availability and register directly in Cloudflare dashboard
- No need to transfer from a third-party registrar

## SSL / TLS

Cloudflare proxies the domain (orange cloud enabled) — Cloudflare handles TLS termination at the edge and provides the cert automatically. No Certbot/ACME needed on the origin server.

Use **Cloudflare Origin CA certificate** (free, generated in Cloudflare dashboard) on the origin server with **Full (strict)** SSL mode. This eliminates cert renewal as an operational concern.

## Object storage

**Decided:** Cloudflare R2 (not Backblaze B2).

- S3-compatible API — works with existing `STORAGE_BACKEND=s3` / boto3 code; only endpoint URL and credentials change in `.env`
- Zero egress fees — R2 has no egress charges, unlike B2

## Application hosting (VM)

**Decided:** Free hosting on an Ubuntu VM in a data center (not DigitalOcean).

- All services run in Docker containers on one host: frontend, backend, workers, redis, authentik
- Same docker-compose structure as local dev, just deployed to the VM

## Postgres

**Decided:** Neon managed Postgres for production (free tier — backups + PITR included). Local Postgres container for development only.

- Production: set `POSTGRES_DSN` in `.env` to the Neon connection string; individual `POSTGRES_*` vars are ignored when DSN is set
- Dev: leave `POSTGRES_DSN` blank, use the `db` service in docker-compose as before
- Neon pauses after 5 min inactivity — fine for prod, not for dev

## Container registry

**Decided:** GitHub Container Registry (ghcr.io) under the `weftmark` GitHub org.

- Org: <https://github.com/weftmark>
- Images: `ghcr.io/weftmark/weaving_site_backend`, `ghcr.io/weftmark/weaving_site_frontend`
- Code is NOT mirrored to GitHub — Gitea remains the source of truth; ghcr.io is registry only
- CD pipeline (Gitea Actions → build → push to ghcr.io → Komodo pulls) is a pending milestone ticket

## Platform name and domain

**Decided:** WeftMark / weftmark.com (resolved issue #55)

## Email addresses

`admin@weftmark.com` and `feedback@weftmark.com` are set up and should be used in SMTP config and email service sender.
