# User Profiles and Sharing

## User Profiles

Every user has a profile visible to themselves. Profiles include:

- Display name
- Personal metrics (projects created, activities completed, total picks woven, total weaving time, etc.)
- Project list
- Equipment inventory (summary)
- Yarn inventory (summary)

Users control what portions of their profile are visible when sharing.

---

## Privacy Model

All projects and profile data are **private by default**. Nothing is publicly visible unless the user explicitly chooses to share it.

There is no social feed, no user discovery, and no ability to browse other users' content. Sharing is always intentional and directed.

---

## Project Sharing

A user can generate a **shareable link** for any project. The link:

- Is a unique slug URL (e.g. `/share/abc123xyz`)
- Displays a read-only view of the project including design preview, activity summary, and any information the user has chosen to include
- Does not require the viewer to have an account
- Can be **revoked** by the user at any time — after revocation the link returns a not-found response
- A new link can be generated after revocation

### What a Shared Project Shows

The user controls what is included in the shared view. Options include:

- Design preview / rendering
- Project description and metadata
- Activity progress and metrics
- Progress photos
- Warping plan and tie-up sheet

---

## Metric Sharing

Users can optionally make their personal metrics visible on their profile if they choose to share their profile link. Metric sharing is independent of project sharing.
