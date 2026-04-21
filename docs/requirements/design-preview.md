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

## Activity Integration

When viewing a design within an active weaving activity:

- Current pick is highlighted in the treadling or liftplan reference panel
- Completed picks are visually distinguished from remaining picks

*Note: The treadling sequence and liftplan are activity/runtime features, not standalone preview views. They appear in context within the activity interface.*

---

## Performance

- Large designs with many threads may take meaningful time to render
- The frontend shows a loading state while rendering jobs process
- Rendered images are cached to avoid re-rendering identical views
