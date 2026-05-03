# Hosting Decisions — WeftMark

**Decision date:** 2026-04-26

---

## 1. Object Storage — Cloudflare R2

**Decision:** Cloudflare R2

**Rationale:**

- S3-compatible API — works with the existing `STORAGE_BACKEND=s3` / boto3 code; only the endpoint URL and credentials change in `.env`
- Zero egress fees — R2 has no egress charges at all, unlike B2 which charges for downloads outside the Cloudflare network
- Already in the Cloudflare ecosystem (domain, DNS, CDN all managed there) — single dashboard, no inter-service egress

**Setup:** R2 bucket created in the Cloudflare dashboard. Set `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` in the production `.env`. R2 endpoint format: `https://<account-id>.r2.cloudflarestorage.com`.

**Estimated cost:** $0/mo within free tier (10 GB storage, 1M Class A ops, 10M Class B ops/mo); $0.015/GB storage thereafter.

---

## 2. Application Host — Ubuntu VM

**Decision:** Self-hosted Ubuntu VM (Ubuntu 24.04) in a data center, managed via Komodo

**Rationale:**

- Runs the full docker-compose stack on a single host: frontend (nginx), backend (FastAPI), worker (Celery), Redis
- Same docker-compose structure as local dev — no new tooling or deployment pipeline required
- Free allocation eliminates VM cost
- Komodo manages container lifecycle and pulls images from ghcr.io on deploy

**Instance sizing:** Minimum 2 vCPU / 4 GB RAM.

**Estimated cost:** $0/mo.

---

## 3. Reverse Proxy — nginx + CrowdSec

**Decision:** nginx as the outer reverse proxy on the VM host, with CrowdSec bouncer

**Rationale:**

- Caddy's automatic HTTPS advantage is irrelevant — Cloudflare terminates TLS at the edge; the origin only needs to accept Cloudflare-proxied traffic
- `crowdsec-nginx-bouncer` is significantly more mature than the Caddy module; nginx access log format is what CrowdSec's log processor expects by default with no extra configuration
- Consistent mental model — the frontend container already runs nginx internally

**Topology:** Cloudflare (TLS) → nginx on VM host (port 443, Cloudflare Origin CA cert, Full strict mode) → frontend container nginx (port 3000) / backend (port 8000)

**Estimated cost:** $0/mo.

---

## 3. Database — Neon (production) + Local container (dev)

**Decision:** Neon managed Postgres for production; local Postgres container for development.

**Rationale:**

- Neon free tier provides managed Postgres with automated backups and point-in-time recovery (PITR) at no cost, removing the operational burden of self-hosting WAL archiving and restore procedures
- Neon pauses after 5 minutes of inactivity — acceptable for production traffic patterns, but disruptive in dev sessions where the database is hit repeatedly
- Local Postgres container (existing docker-compose `db` service) is instant, offline-capable, and already working

**Wiring:** Set `POSTGRES_DSN` in the production `.env` to the Neon connection string. The individual `POSTGRES_*` vars are only used when `POSTGRES_DSN` is blank (i.e. local dev). See `backend/app/config.py`.

**Before going live:** Test a full restore from a Neon backup snapshot. Neon free tier retains 7 days of backups.

**Estimated cost:** $0/mo on free tier (0.5 GB storage, 191.9 compute hours/mo).

---

## 4. DNS / CDN / TLS — Cloudflare

**Decision:** Cloudflare for domain registration, DNS, CDN, and TLS.

**Rationale:**

- `weftmark.com` registered through Cloudflare Registrar
- Cloudflare proxies the domain (orange cloud on) — TLS termination at the edge, certificate handled automatically
- Origin server uses a Cloudflare Origin CA certificate with **Full (strict)** SSL mode — no Certbot/ACME renewal to manage
- Cloudflare CDN in front of R2 eliminates egress fees and improves global asset delivery

**Estimated cost:** $0/mo (free plan covers DNS, CDN, and DDoS protection); ~$11/yr for domain renewal.

---

## 5. Container Registry — GitHub Container Registry (ghcr.io)

**Decision:** `ghcr.io/weftmark` (GitHub org created 2026-04-26)

**Rationale:**

- Free for public images, generous storage on free org tier
- Komodo pulls from ghcr.io on deploy — needs a registry reachable from the production VM
- Keeps the `weftmark` namespace clean and separate from personal GitHub activity

**Image names:**

- `ghcr.io/weftmark/weftmark-backend:<version>`
- `ghcr.io/weftmark/weftmark-frontend:<version>`

**Source:** `https://github.com/weftmark/weftmark` (org: `weftmark`). GitHub Actions CI/CD builds and pushes images on merge to `dev` (`:dev` tag) and `main` (`:latest` + `:{version}`).

**Estimated cost:** $0/mo (public packages are free).

---

## 6. Authentication — Clerk

**Decision:** Clerk hosted authentication (replaced Authentik)

**Status:** Shipped.

**Why Clerk over Authentik:**

- Authentik required self-hosting (~2 GB RAM overhead), manual invite provisioning, and ongoing security maintenance. Clerk is fully managed.
- Clerk provides built-in social login, MFA, user management dashboard, and session handling out of the box.
- Removing Authentik from the docker-compose stack reduced the minimum VM RAM requirement.
- Free tier: unlimited MAU on development; 10,000 MAU on production (as of 2026).

**Architectural note:** The local `users` table is the source of truth for app-level data (projects, activities, preferences). Clerk manages identity only; a webhook handler at `POST /webhooks/clerk` keeps the two in sync. Backend validates Bearer tokens in the `Authorization` header — not cookies. Users can self-register via Clerk; new accounts require admin approval before access is granted.

**Estimated cost:** $0/mo on free tier.

---

## 7. Email — SMTP2Go

**Decision:** SMTP2Go for transactional email (invitations).

**Status:** Confirmed working in production (May 3, 2026). All transactional email flows validated — signup notifications, approval emails, and invite emails all delivered correctly.

**Sender:** `admin@weftmark.com` / display name `WeftMark`

**Estimated cost:** $0/mo on free tier (1,000 emails/mo).

---

## 8. Monthly Cost Summary

| Service | Cost |
| --- | --- |
| Ubuntu VM | $0 |
| Neon Postgres | $0 |
| Cloudflare R2 | $0 (within free tier) |
| Cloudflare DNS/CDN/TLS | $0 |
| Clerk | $0 (within free tier) |
| SMTP2Go | $0 (within free tier) |
| weftmark.com domain | ~$1/mo ($11/yr) |
| **Total** | **~$1/mo** |
