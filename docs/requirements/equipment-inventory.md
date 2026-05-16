# Equipment Inventory

## Overview

Users can document the looms they own in the platform. Loom records are used by the project system to suggest compatible project types and provide default values such as warp waste allowance.

---

## Loom Record

Each loom record captures:

### Identity
- Manufacturer
- Model name / number
- Serial number (optional)

### Purchase Information
- Purchase date
- Purchase price
- Vendor / source

### Technical Specifications
- Weaving width (maximum)
- Number of shafts
- Number of treadles
- Supported project types (lift-tracking, treadle-tracking, or both)

### Notes
- General notes and observations about the loom

---

## Versioned Loom State

Looms can be upgraded over time (e.g. a Louet Jane 8 expanded to 16 shafts). Because projects must record the exact state of the loom at the time of weaving, loom records use a **versioned state history**.

### How Versioning Works

- The initial record is Version 1 with an effective date
- When an upgrade or modification occurs, the user creates a new version with an effective date and a description of the change
- All previous versions are retained and remain viewable
- The **current version** is always the latest
- When creating a project, the user selects which version of a loom was used — defaulting to the current version

### Version Record

Each version captures:
- Effective date
- Description of change (e.g. "Expanded from 8 to 16 shafts")
- Full snapshot of technical specifications at that point in time

### Impact on Activities

A project stores a reference to the specific loom version it was created with. This preserves historical accuracy — a project woven before an upgrade correctly reflects the loom's earlier configuration.

---

## Upgrades and Accessories

Users can document upgrades and accessories attached to a loom, such as:
- Shaft expansions
- New reeds or beaters
- Auto-advance mechanisms
- Additional treadles
- Any other modifications

Upgrades that change technical specifications (shaft count, treadle count, weaving width) should trigger creation of a new loom version.

---

## Reed Inventory

Each loom can have an associated collection of reeds. Reed records are stored on the loom (not versioned — reeds are accessories, not configuration).

### Reed Record

| Field | Description |
| --- | --- |
| Dent count | Threads per inch or per cm (the "sett" of the reed) |
| Unit | `imperial` (dents per inch) or `metric` (dents per 10 cm) |
| Width | Maximum weaving width this reed allows |
| Notes | Optional free-text notes |

### Reed Recommendations

When a user is about to create a project, the platform cross-references the draft's EPI (ends per inch, from the WIF) against the reeds recorded for the selected loom and presents a list of compatible reeds, ranked by how closely their dent count matches the draft's EPI. Incompatible reeds (wrong sett for the design) are shown separately with an explanation.

---

## Loom Photos

Users can attach photos to a loom record (e.g. full loom, control panel, specific accessories). Photos are stored in R2 and displayed on the loom detail page. Photo upload and display use the same `AuthedImage` + Bearer-fetch pattern as project progress photos.

---

## Compatibility with WIF Files

When a user creates a project, the platform uses the loom's technical specifications to determine compatibility:

- A loom with 8 shafts should not be used with a WIF file requiring more than 8 shafts
- Incompatible configurations are flagged with a warning; the user can override but the warning is noted in the project record
