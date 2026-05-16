# Weaving Projects

## Overview

A project is a specific instance of weaving a design on a loom. It is the core feature of the platform. A single WIF draft can have multiple simultaneous projects — for example, the same design being woven on two different looms, or the same design tracked once as a lift-tracking project and once as a treadle-tracking project.

---

## Project Types

### Lift-Tracking Project

Used with direct-tie looms where individual shafts are raised or lowered using levers (e.g. Louet Jane). For each pick, the platform displays which levers (shafts) should be up and which should be down. Data source: `[LIFTPLAN]` section of the WIF file.

### Treadle-Tracking Project

Used with floor looms where treadle pedals raise or lower groups of shafts (e.g. Louet Spring II). For each pick, the platform displays which treadles to press. Data source: `[TREADLING]` section of the WIF file.

### Project Type Rules

- The project type is selected by the user when creating the project
- The loom selected from equipment inventory indicates which project types it supports, guiding the user's selection
- Once a project has started (at least one pick recorded), the project type cannot be changed without resetting all progress
- A new project of a different type can always be created for the same draft — there is no limit on the number of projects per draft

---

## Project Landing Page

When a project is created but has not yet had any picks recorded, it enters **pre-tracking state** and shows the Project Landing Page. This page is the staging area before weaving starts:

- **Design preview** — full draft layout (threading diagram, tie-up, drawdown) rendered with the project's current color replacements applied
- **Color palette editor** — swap warp and weft colors per-project without touching the source WIF file. Color changes flow through the drawdown preview, pick display at the loom, and the completed summary automatically
- **Warp setup** — configure finished length per item, number of items, waste between items; see calculated total warp length
- **Draft summary** — WIF metadata, EPI, reed recommendations

Once the user starts tracking (records the first pick), the project moves to active state and the landing page is replaced by the loom-side tracking interface.

---

## Color Replacements

Each project maintains a `color_replacements` map of hex→hex swaps applied on top of the WIF `[COLOR TABLE]` data.

- Color replacements are saved via `PUT /api/projects/{id}/color-replacements`
- Saving new replacements invalidates and re-renders the R2 drawdown tile cache (`prerender_project_tiles` Celery task)
- The design preview endpoint (`GET /api/projects/{id}/drawdown/preview`) applies replacements at render time
- The at-the-loom drawdown tile endpoint applies replacements from the cached tiles (or renders inline if not cached)

---

## Creating a Project

When creating a project, the user provides:

| Input | Notes |
| --- | --- |
| Project name | User-defined label |
| WIF draft | The design to weave |
| Project type | Lift-tracking or treadle-tracking (filtered by WIF availability and loom capability) |
| Loom | Selected from equipment inventory (optional but recommended) |
| Loom version | Which state/version of the loom is being used |
| Finished length per item | Used to calculate warp length |
| Number of items | e.g. 5 towels on one warp |
| Waste between items | Space between items on the warp |

Warp waste allowance is pulled as a default from the selected loom's inventory record and can be adjusted by the user.

---

## Step Tracking

### Definition

One step = one pick = one pass of the shuttle through the shed.

### Navigation

The user advances or reverses steps via:

- On-screen buttons (large tap targets for loom-side use)
- Keyboard shortcuts (Phase 1)
- Bluetooth pedal with keyboard emulation (works automatically via keyboard events — no special Bluetooth handling required)

### Correction Events

Reversing a step is logged as a correction event — it is never silently undone. The session history retains a full record of all step changes including reversals.

### Review Navigation vs Worked Picks

A user may step forward or backward quickly to preview upcoming or past steps without actually weaving them. The platform distinguishes review navigation from worked picks using a **learned dwell threshold**.

**How it works:**

- Every step change is logged with a timestamp
- Steps where the user dwells past the threshold before advancing are classified as **worked picks**
- Steps where the dwell time is below the threshold are classified as **review navigation**
- The threshold is learned per project based on the user's observed weaving rhythm
- Lift-tracking projects default to a longer threshold than treadle-tracking projects, as they require more physical setup time per pick
- Complex designs may naturally result in longer dwell times regardless of loom type
- No explicit "confirm pick" button is required — the system learns the user's natural pace

### Working Position

The **working position** is a separate concept from the navigation cursor. It represents the actual pick the weaver has completed in their physical weaving. It is maintained and updated automatically based on the dwell threshold, and is the basis for all progress metrics.

---

## Loom-Side Interface

The project screen is optimized for use at the loom:

- **Portrait orientation** preferred
- **Large tap targets** for step navigation buttons
- **Loom mode** — a simplified view showing only the current step information; toggled on/off quickly
- **Screen always-on** — prevents device sleep during a weaving session; toggled on/off quickly

---

## Metrics (Displayed During Weaving)

| Metric | Description |
| --- | --- |
| Current step | Pick number and total picks |
| Percentage complete | Based on working position |
| Cumulative session time | Total time in this project across all sessions |
| Elapsed time this session | Time since this session started |
| Estimated time remaining | Based on average time per worked pick |

---

## Weaving Sessions

Sessions are **auto-detected** — no explicit start/stop action is required from the user.

- Opening a project starts a session automatically
- Closing the project or remaining idle past a configurable threshold ends the session
- The idle timeout threshold is **user-configurable** per their preferences

Each session records:

- Start and end timestamps
- Picks worked during the session
- Corrections made
- Photos uploaded

The full session log is available to the user as a history of their weaving project.

---

## Progress Photos

At any point during a project, the user can attach a photo:

- **Camera capture** — if the device has a camera (uses browser native camera API)
- **File picker** — fallback for devices without a camera or user preference
- **Caption** — user-entered text
- **Tags** — user-defined tags
- **Automatic metadata** — step number, timestamp, percentage complete, and session reference are stamped automatically at upload time

---

## Warping Plan

Generated per project based on WIF data and user inputs. Provides the weaver with everything needed to prepare the warp.

### Inputs (from user at project creation)

- Finished length per item
- Number of items
- Waste space between items
- Loom warp waste allowance (defaulted from loom inventory, adjustable)

### Outputs (calculated)

- Total warp length = (finished length × items) + (waste between items × (items − 1)) + loom warp waste
- Number of warp threads per color (from WIF `[WARP COLORS]` and `[COLOR TABLE]`)
- Threading color order (from WIF `[THREADING]`)

---

## Tie-Up Sheet

A standard shaft-to-treadle reference grid derived directly from the WIF `[TIEUP]` section. Intended as a printed or on-screen reference when setting up the loom.

---

## Post-Project Notes

After a project is completed, the user can enter notes about:

- Actual warp waste observed (to improve future estimates for that loom)
- Yarn consumption vs estimate
- General observations about the draft, loom behavior, or design

These notes feed into the platform's learned defaults for the user's loom and weaving habits over time.

---

## Works in Progress (WIPs)

Projects that have been started but not completed are referred to as **WIPs** (works in progress). A user can have multiple simultaneous WIPs.

---

## Multi-Product Projects

A single project can produce multiple end products on one warp (e.g. five hand towels). The warping plan accounts for waste between products. All products in the project are tracked together under a single step sequence.

---

## Completed Project Summary

When a project is marked complete, the Completed Summary page is shown. It includes:

- **Design preview** — full draft layout PNG with the project's color replacements applied; image fills the summary card
- **Session metrics** — total picks, total sessions, total time, average picks per session
- **Warp setup details** — finished length per item, number of items, waste, total warp length
- **Photos** — all attached photos displayed in chronological order
- **Notes** — post-project observations entered by the user

The design preview uses the same `render_full_draft` rendering path as the project landing page, ensuring consistent appearance.
