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

**Decided:** Backblaze B2 (not Cloudflare R2).
- S3-compatible API — works with existing `STORAGE_BACKEND=s3` / boto3 code; only endpoint URL and credentials change in `.env`
- B2 charges egress outside Cloudflare network — use Cloudflare CDN in front to keep most requests as cache hits and avoid egress costs

## Application hosting (VM)

**Decided:** Free hosting on an Ubuntu VM in a data center (not DigitalOcean).
- All services run in Docker containers on one host: frontend, backend, postgres, postgres-backup, workers, redis
- Same docker-compose structure as local dev, just deployed to the VM

## Postgres

**Decided:** Self-hosted Postgres container on the VM (with a separate postgres-backup service container).

## Platform name and domain

**Decided:** WeftMark / weftmark.com (resolved issue #55)

## Email addresses

admin@weftmark.com and feedback@weftmark.com are set up and should be used in SMTP config and email service sender.
