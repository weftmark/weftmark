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

## Palette Exploration Previews

Standalone HTML previews (no build required) are in `docs/assets/preview-*.html`. Each loads Tailwind via CDN and references `hearts-treadle.mp4` from the same directory. Use these to test new palettes before touching the React source.

Available previews: `cream-copper`, `slate-copper`, `natural-indigo`, `sage-loom`, `clay`, `teal`, `rose`, `plum`.
