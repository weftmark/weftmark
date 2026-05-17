# WeftMark UI Design System

> **Status:** Active — current palette is **Slate & Copper**. This direction is not frozen; the palette and layout patterns may evolve, but this document defines the reference baseline for consistent UX work.

---

## Palette — Slate & Copper

Two-tone palette: a dark neutral primary paired with a warm amber accent. Backgrounds stay neutral; the accent color is reserved for focal points only.

| Role | Tailwind token | Hex approx |
|---|---|---|
| Primary action / logo fill | `zinc-800` | `#27272a` |
| Accent — headlines, icons, badges | `amber-600` | `#d97706` |
| Page background | `stone-50` | `#fafaf9` |
| Hero gradient start | `stone-100` | `#f5f5f4` |
| Card / surface background | `white` | `#ffffff` |
| Body text | `stone-900` | `#1c1917` |
| Secondary text | `stone-600` | `#57534e` |
| Muted text | `stone-500` | `#78716c` |
| Border / ring | `stone-200` / `stone-300` | |

### Do / Don't
- **Do** use `stone-50` as the page base — not white, not tinted.
- **Do** limit amber to: logo, h1 accent span, primary badge, icon badge bg/text.
- **Don't** tint the hero or feature section background with amber — keep it neutral warm gray.
- **Don't** use zinc-800 for decorative elements; reserve it for the primary CTA and logo only.

---

## Layout Depth Pattern

These techniques add visual hierarchy without busy decoration.

### Grain texture overlay
A fixed SVG `feTurbulence` filter at 4.5% opacity layered over the entire page. Applied once at the top-level layout wrapper.

```tsx
<svg
  className="pointer-events-none fixed inset-0 z-50 h-full w-full opacity-[0.045]"
  xmlns="http://www.w3.org/2000/svg"
  aria-hidden="true"
>
  <filter id="grain">
    <feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="4" stitchTiles="stitch" />
  </filter>
  <rect width="100%" height="100%" filter="url(#grain)" />
</svg>
```

### Angled section divider
Hero sections use a `clip-path` polygon to create a diagonal bottom edge. The next section floats over it with a negative top margin.

```tsx
// Hero section
<section
  className="relative bg-gradient-to-br from-stone-100 via-stone-50 to-white px-6 pt-16 pb-32 lg:pt-24 lg:pb-40"
  style={{ clipPath: "polygon(0 0, 100% 0, 100% 88%, 0 100%)" }}
>

// Floating section below
<section className="relative z-10 -mt-12 px-6 pb-20">
```

### Feature cards
Cards sit on white with a subtle shadow and ring. They lift on hover.

```tsx
<div className="rounded-2xl bg-white p-7 shadow-md ring-1 ring-stone-200/80 transition-all duration-200 hover:-translate-y-1 hover:shadow-xl">
  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
    <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
  </div>
  ...
</div>
```

---

## Header

Sticky, blurred, no visible border — separation comes from a soft shadow.

```tsx
<header className="sticky top-0 z-10 bg-stone-50/95 px-6 py-4 backdrop-blur shadow-sm shadow-stone-900/5">
```

Logo color: `text-zinc-800`. Sign-in link: `text-stone-600 hover:text-stone-900`.

---

## CTA Buttons

```tsx
// Primary
<Link className="rounded-lg bg-zinc-800 px-6 py-3 text-center text-sm font-semibold text-white shadow-md shadow-zinc-900/30 transition-colors hover:bg-zinc-900">

// Secondary
<Link className="rounded-lg border border-stone-300 bg-white/60 px-6 py-3 text-center text-sm font-semibold text-stone-700 transition-colors hover:bg-white">
```

Always `text-center` on both. Horizontal on `sm:` breakpoint, stacked below.

---

## Hero Layout

Two-column grid on large screens: text left (narrower), media right (wider).

```tsx
<div className="grid items-center gap-12 lg:grid-cols-[1fr_1.4fr]">
  <div className="order-2 lg:order-1">/* text */</div>
  <div className="order-1 lg:order-2">/* media */</div>
</div>
```

Media column gets `1.4fr` to give the video/screenshot more visual weight.

---

## Badge Pill

```tsx
<span className="mb-5 inline-block rounded-full bg-amber-100 px-3.5 py-1 text-xs font-medium tracking-wide text-amber-700">
  Weaving companion for handweavers
</span>
```

---

## Browser Chrome Frame (video/screenshot mockup)

```tsx
<div className="overflow-hidden rounded-2xl shadow-2xl shadow-stone-900/20 ring-1 ring-stone-300/60">
  <div className="flex items-center gap-1.5 border-b border-stone-200 bg-stone-200/80 px-4 py-3">
    <span className="h-3 w-3 rounded-full bg-red-400" />
    <span className="h-3 w-3 rounded-full bg-amber-400" />
    <span className="h-3 w-3 rounded-full bg-green-500" />
    <span className="ml-3 flex-1 rounded bg-stone-300/60 px-3 py-1 text-center text-xs text-stone-500">
      weftmark.com
    </span>
  </div>
  {/* content */}
</div>
```

---

## Authenticated App Theming (CSS Variables)

The authenticated app shell (sidebar, pages, modals) uses CSS custom properties defined in `frontend/src/index.css` and mapped to Tailwind tokens in `tailwind.config.ts`. This is the single source of truth for both light and dark mode — never use hard-coded palette classes (e.g. `stone-50`, `amber-600`) inside authenticated pages/components.

### Token Reference

| Tailwind class | CSS variable | Light value | Dark value |
| --- | --- | --- | --- |
| `bg-background` | `--background` | stone-50 | stone-900 |
| `text-foreground` | `--foreground` | stone-900 | stone-50 |
| `bg-card` / `text-card-foreground` | `--card` | white | stone-800 |
| `bg-popover` / `text-popover-foreground` | `--popover` | white | stone-800 |
| `bg-primary` / `text-primary-foreground` | `--primary` | amber-900 | amber-500 |
| `bg-secondary` / `text-secondary-foreground` | `--secondary` | stone-100 | stone-700 |
| `bg-muted` / `text-muted-foreground` | `--muted` | stone-100 | stone-700 |
| `text-accent` / `bg-accent` | `--accent` | amber-600 | amber-500 |
| `border-border` | `--border` | stone-200 | stone-700 |
| `bg-input` | `--input` | stone-200 | stone-700 |
| `ring-ring` | `--ring` | amber-600 | amber-500 |
| `text-subdued` | `--subdued` | stone-600 | stone-400 |
| `bg-copper-subtle` | `--copper-subtle` | amber-50 | amber-950 |
| `text-copper-on-subtle` | `--copper-on-subtle` | amber-700 | amber-300 |

### Semantic Intent

- **`background`** — Page canvas
- **`card`** — Surface for panels, sidebars, dialogs, cards
- **`muted`** — Subtle backgrounds (hover states, inactive sections); `muted-foreground` for de-emphasized text
- **`subdued`** — Text that's secondary but not as faint as `muted-foreground` (e.g. nav link labels when inactive)
- **`accent`** — Amber highlight: active icons, focus rings, badges
- **`copper-subtle` / `copper-on-subtle`** — Active nav item background and text (amber-tinted chip)

### Dark Mode

Dark mode is class-based (`darkMode: ["class"]` in `tailwind.config.ts`). The `.dark` class is applied to `<html>` by `AuthContext` from `user.theme` (stored in the backend DB). Unauthenticated pages (landing, login, register) are always light — do not add `dark:` variants there.

All authenticated UI adapts automatically when the CSS variables change under `.dark` — no `dark:` variant classes are needed in component markup.

### Rules

- **Do** use semantic tokens for all authenticated pages and components.
- **Do** use `bg-card` for panel/modal surfaces, `bg-background` for page canvas.
- **Don't** use raw palette classes (`stone-*`, `amber-*`, `zinc-*`) inside authenticated components — changes to the palette would then require hunting down every hard-coded class.
- **Don't** add dark mode overrides to public pages (landing, login, register, about, privacy, terms).

---

## Button Conventions (Authenticated App)

Use `<Button>` from `frontend/src/components/ui/button.tsx`. Match intent to variant — do not choose a variant based on aesthetics alone.

| Intent | Variant | When to use |
| --- | --- | --- |
| Confirm / save / submit | `default` (no `variant` prop) | The primary positive action in a form or dialog — "Save", "Add", "Submit" |
| Cancel / dismiss / close | `variant="outline"` | The secondary escape action alongside a confirm button |
| Delete / ban / irreversible | `variant="destructive"` | Any action that cannot be undone |
| Secondary neutral | `variant="secondary"` | Second-tier actions that aren't destructive and aren't the primary CTA |
| Positive outcome / advance | `variant="success"` | Marking a step complete, advancing a project, green-light actions |
| Toolbar / icon-only | `variant="ghost"` | Icon buttons in toolbars, inline row actions with no border needed |

### Common patterns

```tsx
// Save / Cancel pair in a form
<Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
<Button type="button" variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>

// Confirm / Cancel in a destructive dialog
<Button variant="destructive" onClick={handleDelete}>Delete</Button>
<Button variant="outline" onClick={() => setConfirm(false)}>Cancel</Button>

// Inline "Add" mini-form (submit = primary action, no cancel present)
<Button type="submit" size="sm" disabled={saving || !input.trim()}>Add</Button>
```

### What changed (v0.145+)

- `--primary` in light mode shifted from zinc-800 (cool gray) to amber-900 (dark copper `#78350f`), consistent with the amber-500 copper primary already used in dark mode. All `bg-primary` surfaces — buttons, progress bars, toggles — now read as copper in light mode.
- `variant="outline"` border changed from `border-input` to `border-foreground/25`, which has better contrast in dark mode where the previous stone-700 border was nearly invisible against the stone-800 card surface.

---

## Palette Exploration Previews

Standalone HTML previews (no build required) are in `docs/assets/preview-*.html`. Each loads Tailwind via CDN and references `hearts-treadle.mp4` from the same directory. Use these to test new palettes before touching the React source.

Available previews: `cream-copper`, `slate-copper`, `natural-indigo`, `sage-loom`, `clay`, `teal`, `rose`, `plum`.
