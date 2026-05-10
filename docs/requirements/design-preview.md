# Design Preview and Rendering

## Rendering Engine

Design previews are generated server-side using the **PyWeaving** Python library. Rendered images are returned to the frontend for display.

Reference: https://pyweaving.readthedocs.io/en/latest/

Rendering jobs run as background tasks via Celery to avoid blocking API responses.

---

## Views

Each view is accessible individually or as a combined full draft view.

### Individual Views

| View | Description |
|---|---|
| Drawdown | Fabric simulation showing how warp and weft threads interlace |
| Threading diagram | Which warp threads pass through heddles on each shaft |
| Tie-up grid | Which shafts are connected to which treadles |

### Combined View

**Full draft view** — all three panels (threading diagram, tie-up grid, drawdown) displayed together in the traditional weaving draft layout. Selectable as an alternative to individual views.

---

## Display Controls

- Zoom in / out
- Pan and scroll (for large designs)
- Grid / thread count overlay toggle
- Rising vs sinking shed toggle (view fabric from either side)
- Repeat / tile view (design tiled as it would appear across full fabric width and length)

### Hide Unused Shafts/Treadles

When a draft uses fewer shafts or treadles than the loom supports, the rendered image includes blank rows/columns for the unused ones. This setting clips the rendering to the design's effective counts, reclaiming space and reducing visual noise.

**Behaviour:**

- When enabled: the renderer uses `effective_num_shafts` and `effective_num_treadles` (derived from actual treadling/threading data in the WIF) as the shaft/treadle bounds instead of the declared `num_shafts`/`num_treadles`
- When disabled (default): all declared shafts and treadles are shown, matching the raw WIF metadata
- Applies to the drawdown tile viewer and the full-draft preview

**Setting levels:**

| Level | Location | Scope |
| --- | --- | --- |
| User default | User Settings → Design Preferences | Applied to all new projects at creation |
| Project override | Project Settings panel | Per-project; overrides user default for that project only |

- New projects inherit the creating user's default at creation time
- Changing the project-level setting does not affect other projects or the user default
- The setting is stored on both `User` and `Project` models as `hide_unused_shafts_treadles` (boolean, default `false`)

**API:**

- `GET /api/drafts/{draft_id}/drawdown?hide_unused_shafts_treadles=true` — query param instructs the renderer to clip to effective counts
- Frontend reads the project (or user) setting and passes the param; the backend does not auto-resolve the project setting from the project ID
- `PATCH /api/users/me` and `PATCH /api/projects/{id}` accept `hide_unused_shafts_treadles`
- `POST /api/projects` inherits the value from the creating user's setting

**Edge cases:**

- If `effective_num_shafts` or `effective_num_treadles` is `null` (e.g. WIF has no treadling section), fall back to declared counts — never fail the render
- Setting has no effect when `effective_num_shafts == num_shafts` and `effective_num_treadles == num_treadles` (nothing to hide)

---

## Color Tools

- Color simulation using color data from the WIF `[COLOR TABLE]` and `[COLOR PALETTE]` sections
- Color substitution — swap colors to preview different colorways without modifying the WIF file
- Isolate warp colors or weft colors independently

---

## Information Overlays

- Thread count and sett display
- Pick count display
- Shaft and treadle labels

---

## Project Integration

When viewing a design within an active weaving project:

- Current pick is highlighted in the treadling or liftplan reference panel
- Completed picks are visually distinguished from remaining picks

*Note: The treadling sequence and liftplan are project/runtime features, not standalone preview views. They appear in context within the project interface.*

---

## Performance

- Large designs with many threads may take meaningful time to render
- The frontend shows a loading state while rendering jobs process
- Rendered images are cached to avoid re-rendering identical views
