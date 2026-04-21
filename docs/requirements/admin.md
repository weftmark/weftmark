# Admin Capabilities

## Overview

Administrators manage platform access, monitor health, and maintain records of WIF compatibility issues reported by users.

---

## User Management

- **Invite management** — create, send, and revoke user invitations
- **User list** — view all registered users and their account status
- **User detail** — view a user's profile, activity count, and account metadata
- **Account suspension** — ability to disable a user account

---

## Platform Monitoring

- **Platform-wide activity** — overview of recent uploads, activities created, active WIPs
- **System health** — service status for backend, worker, database, and Redis
- **Background job status** — monitor Celery job queue (rendering jobs, PDF exports)
- **Storage usage** — uploaded WIF files, rendered images, photos, PDF reports

---

## User Metrics

- Total users (active, inactive, invited)
- New registrations over time
- Activity creation rate
- Most active users (by picks woven, activities completed, etc.)

---

## WIF Compatibility Records

When a user uploads a WIF file that produces warnings or errors and reports which software generated it:

- The diagnostic report is stored alongside the user's response
- Admins can browse and search compatibility records by software name, version, or error type
- Records help identify patterns of non-standard WIF output from specific tools or versions
- Admins can add notes to compatibility records (e.g. workarounds, known issues, whether a fix was applied)

This data informs platform documentation about third-party software compatibility (see `wif-import.md`).
