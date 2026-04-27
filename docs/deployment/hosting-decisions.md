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

**Decision:** Self-hosted Ubuntu VM in a data center

**Rationale:**

- Runs the full docker-compose stack on a single host: frontend (nginx), backend (FastAPI), worker (Celery), Redis, Authentik
- Same docker-compose structure as local dev — no new tooling or deployment pipeline required
- Free allocation eliminates VM cost

**Instance sizing:** Minimum 2 vCPU / 4 GB RAM (8 GB recommended) to accommodate Authentik's footprint alongside the application stack. See [Proxmox VM sizing note in infrastructure memory](../../.claude/memory/infrastructure.md).

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

## 5. Email — SMTP2Go

**Decision:** SMTP2Go for transactional email (invitations).

**Status:** Account creation pending — weftmark.com domain must be active for 3 days before SMTP2Go will approve. Tracked in issue #62, due 2026-05-01.

**Sender:** `admin@weftmark.com` / display name `WeftMark`

**Estimated cost:** $0/mo on free tier (1,000 emails/mo).

---

## Monthly Cost Summary

| Service | Cost |
| --- | --- |
| Ubuntu VM | $0 |
| Neon Postgres | $0 |
| Cloudflare R2 | $0 (within free tier) |
| Cloudflare DNS/CDN/TLS | $0 |
| SMTP2Go | $0 (within free tier) |
| weftmark.com domain | ~$1/mo ($11/yr) |
| **Total** | **~$1/mo** |
