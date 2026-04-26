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

Leading candidate: **Cloudflare R2** (already in the same Cloudflare dashboard, no separate account needed).
- No egress fees
- S3-compatible API — works with planned `STORAGE_BACKEND=s3`
- Custom domain for bucket via one-click DNS record (e.g. `assets.domain.com`)

## Application hosting (VM)

User is familiar with **DigitalOcean** Droplets. No decision made yet — see issue #50.

## Postgres

No decision made yet. Recommendation: use a managed Postgres service (not self-hosted) for automated backups and PITR. Options evaluated in issue #50: DigitalOcean Managed Postgres, Neon, Supabase.
