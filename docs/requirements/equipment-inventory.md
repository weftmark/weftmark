# Equipment Inventory

## Overview

Users can document the looms they own in the platform. Loom records are used by the activity system to suggest compatible activity types and provide default values such as warp waste allowance.

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
- Supported activity types (lift-tracking, treadle-tracking, or both)

### Notes
- General notes and observations about the loom

---

## Versioned Loom State

Looms can be upgraded over time (e.g. a Louet Jane 8 expanded to 16 shafts). Because activities must record the exact state of the loom at the time of weaving, loom records use a **versioned state history**.

### How Versioning Works

- The initial record is Version 1 with an effective date
- When an upgrade or modification occurs, the user creates a new version with an effective date and a description of the change
- All previous versions are retained and remain viewable
- The **current version** is always the latest
- When creating an activity, the user selects which version of a loom was used — defaulting to the current version

### Version Record

Each version captures:
- Effective date
- Description of change (e.g. "Expanded from 8 to 16 shafts")
- Full snapshot of technical specifications at that point in time

### Impact on Activities

An activity stores a reference to the specific loom version it was created with. This preserves historical accuracy — an activity woven before an upgrade correctly reflects the loom's earlier configuration.

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

## Compatibility with WIF Files

When a user creates an activity, the platform uses the loom's technical specifications to determine compatibility:

- A loom with 8 shafts should not be used with a WIF file requiring more than 8 shafts
- Incompatible configurations are flagged with a warning; the user can override but the warning is noted in the activity record
