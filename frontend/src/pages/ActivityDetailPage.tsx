import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getActivity, getActivityPicks, stepActivity, jumpActivity, completeActivity, abandonActivity,
  restartActivity, cloneActivity, listActivities, deleteActivity,
  renameActivity, uploadActivityPhoto, deleteActivityPhoto, activityPhotoUrl,
  ApiError, ACTIVITY_TYPE_LABELS, ACTIVITY_STATUS_LABELS,
  type ActivitySummary, type ActivityPhoto, type PickRow,
} from "@/api/activities";
import { previewUrl } from "@/api/projects";
import { getAuthToken } from "@/api/client";
import { AssignLoomModal } from "@/components/activities/AssignLoomModal";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { Button } from "@/components/ui/button";

// ---------------------------------------------------------------------------
// Color utilities
// ---------------------------------------------------------------------------

function contrastColor(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const lin = (c: number) => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  const L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return L > 0.179 ? "#000000" : "#ffffff";
}

type ColorMode = "theme" | "strip" | "filled";

// ---------------------------------------------------------------------------
// Collapsible section
// ---------------------------------------------------------------------------

function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="border-t">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between py-3 text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
      >
        {title}
        <span className="text-base leading-none">{open ? "▾" : "▸"}</span>
      </button>
      {open && <div className="pb-5">{children}</div>}
    </section>
  );
}

// ---------------------------------------------------------------------------
// WIF design preview modal
// ---------------------------------------------------------------------------

function DesignPreviewModal({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div className="relative max-w-3xl w-full" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute -top-9 right-0 text-white/70 hover:text-white text-sm"
        >
          Close ✕
        </button>
        <AuthedImage
          src={previewUrl(projectId)}
          alt="WIF design preview"
          className="w-full rounded-lg shadow-2xl"
          style={{ imageRendering: "pixelated" }}
        />
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Pick display — current pick instructions
// ---------------------------------------------------------------------------

function PickDisplay({
  pick,
  totalCount,
  activityType,
  colorMode,
  showWeftColor,
}: {
  pick: PickRow;
  totalCount: number;
  activityType: string;
  colorMode: ColorMode;
  showWeftColor: boolean;
}) {
  const label = activityType === "lift" ? "Raise shafts" : "Press treadles";
  const count = Math.max(totalCount, pick.active.length > 0 ? Math.max(...pick.active) : 0, 1);
  const weftHex = pick.color ?? null;

  const boxCls =
    count <= 4  ? "h-14 w-14 text-base"
    : count <= 8  ? "h-10 w-10 text-sm"
    : count <= 16 ? "h-8 w-8 text-xs"
    : "h-6 w-6 text-xs";

  return (
    <div className="rounded-xl border-2 border-primary/30 bg-primary/5 dark:bg-primary/10 px-6 py-5 space-y-4">
      <p className="text-center text-xs font-medium text-primary/80 uppercase tracking-wider">
        {label} · pick {pick.pick}
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {Array.from({ length: count }, (_, i) => i + 1).map((n) => {
          const active = pick.active.includes(n);
          if (colorMode !== "theme" && active && weftHex) {
            if (colorMode === "filled") {
              const fg = contrastColor(weftHex);
              return (
                <div key={n} style={{ backgroundColor: weftHex, borderColor: fg }}
                  className={`${boxCls} rounded-md border-2 flex items-center justify-center font-bold`}>
                  <span style={{ color: fg }}>{n}</span>
                </div>
              );
            }
            if (colorMode === "strip") {
              return (
                <div key={n}
                  className={`${boxCls} rounded-md border-2 relative overflow-hidden border-primary bg-primary flex items-center justify-center font-bold`}>
                  <span className="absolute bottom-0 left-0 right-0 h-[20%]"
                    style={{ backgroundColor: weftHex }} />
                  <span className="relative text-primary-foreground">{n}</span>
                </div>
              );
            }
          }
          return (
            <div key={n}
              className={`${boxCls} rounded-md border-2 flex items-center justify-center font-bold ${
                active
                  ? "bg-primary border-primary text-primary-foreground"
                  : "border-muted bg-muted/30 text-muted-foreground"
              }`}>
              {n}
            </div>
          );
        })}
      </div>
      {showWeftColor && weftHex && (
        <div
          className="h-7 w-full rounded-md flex items-center justify-center text-xs font-semibold uppercase tracking-wider"
          style={{ backgroundColor: weftHex, color: contrastColor(weftHex) }}
        >
          Weft Color
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Weaving pattern view — drawdown image windowed to current pick
// ---------------------------------------------------------------------------

// Overhead accounts for: app header, activity header, progress bar,
// controls bar, pick instruction card, step controls, and padding.
const PATTERN_OVERHEAD_PX = 560;
const PATTERN_MIN_H = 200;
const STEP_PANEL_W = 128;
const COLOR_COL_W = 24;
const BLEED = 12;

function useAdaptivePatternHeight(): number {
  const compute = () => Math.max(PATTERN_MIN_H, window.innerHeight - PATTERN_OVERHEAD_PX);
  const [height, setHeight] = useState(compute);
  useEffect(() => {
    const onResize = () => setHeight(compute());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return height;
}

function WeavingPatternView({
  projectId,
  currentPickIndex,
  totalPicks,
  picks,
  maxActive,
}: {
  projectId: string;
  currentPickIndex: number;
  totalPicks: number;
  picks: PickRow[];
  maxActive: number;
}) {
  const containerH = useAdaptivePatternHeight();
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [pixelsPerRow, setPixelsPerRow] = useState(20);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const token = await getAuthToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`/api/projects/${projectId}/drawdown`, { credentials: "include", headers });
      const ppr = parseInt(res.headers.get("X-Pixels-Per-Row") ?? "20", 10);
      if (!cancelled) setPixelsPerRow(ppr);
      const blob = await res.blob();
      if (cancelled) return;
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setImgSrc(url);
    }
    load().catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [projectId]);

  if (!imgSrc) return null;

  // Image is flipped: last pick at y=0 (top), pick 1 at bottom.
  const flippedIndex = totalPicks - 1 - currentPickIndex;
  const translateY = containerH / 2 - pixelsPerRow / 2 - flippedIndex * pixelsPerRow;
  const futureRegionH = Math.max(0, containerH / 2 - pixelsPerRow / 2);
  const highlightTop = containerH / 2 - pixelsPerRow / 2 - 1;
  const highlightH = pixelsPerRow + 2;
  const boxH = Math.max(4, pixelsPerRow - 6);

  // Picks reversed so the last pick renders first (topmost) — matches drawdown orientation.
  const reversedPicks = [...picks].reverse();

  const washoutOverlay = (
    <>
      <div
        className="absolute left-0 right-0 pointer-events-none"
        style={{
          top: 0,
          height: futureRegionH,
          backdropFilter: "saturate(0) brightness(1.6)",
          WebkitBackdropFilter: "saturate(0) brightness(1.6)",
        }}
      />
      <div
        className="absolute left-0 right-0 pointer-events-none bg-white/50 dark:bg-zinc-900/55"
        style={{ top: 0, height: futureRegionH }}
      />
    </>
  );

  return (
    // Outer wrapper: no overflow-hidden so highlight bars bleed left/right.
    <div className="relative flex gap-2" style={{ height: containerH }}>

      {/* Drawdown image — horizontally scrollable to view wide designs */}
      <div className="flex-1 rounded-lg border overflow-x-auto overflow-y-hidden relative bg-white dark:bg-zinc-900">
        <img
          src={imgSrc}
          alt="Woven pattern"
          className="block"
          style={{
            transform: `translateY(${translateY}px)`,
            imageRendering: "pixelated",
            transition: "transform 0.15s ease",
            maxWidth: "none",
          }}
        />
        {washoutOverlay}
      </div>

      {/* Lift/treadle step panel */}
      <div
        className="rounded-lg border overflow-hidden relative bg-background shrink-0"
        style={{ width: STEP_PANEL_W }}
      >
        <div
          style={{ transform: `translateY(${translateY}px)`, transition: "transform 0.15s ease" }}
        >
          {reversedPicks.map((pick) => (
            <div
              key={pick.pick}
              className="flex items-center px-1 gap-[2px]"
              style={{ height: pixelsPerRow }}
            >
              {Array.from({ length: maxActive }, (_, j) => j + 1).map((n) => (
                <div
                  key={n}
                  className={`rounded-[2px] flex-1 min-w-0 ${
                    pick.active.includes(n) ? "bg-primary" : "bg-muted/40"
                  }`}
                  style={{ height: boxH }}
                />
              ))}
            </div>
          ))}
        </div>
        {washoutOverlay}
      </div>

      {/* Weft color history column */}
      <div
        className="rounded-lg border overflow-hidden relative shrink-0"
        style={{ width: COLOR_COL_W }}
      >
        <div
          style={{ transform: `translateY(${translateY}px)`, transition: "transform 0.15s ease" }}
        >
          {reversedPicks.map((pick) => (
            <div
              key={pick.pick}
              style={{
                height: pixelsPerRow,
                backgroundColor: pick.color ?? "hsl(var(--muted))",
              }}
            />
          ))}
        </div>
        {washoutOverlay}
      </div>

      {/* Highlight bars — span all panels + bleed on each side */}
      <div
        className="absolute pointer-events-none bg-primary/20"
        style={{ left: -BLEED, right: -BLEED, top: highlightTop, height: highlightH }}
      />
      <div
        className="absolute pointer-events-none h-[3px] bg-primary"
        style={{ left: -BLEED, right: -BLEED, top: highlightTop }}
      />
      <div
        className="absolute pointer-events-none h-[3px] bg-primary"
        style={{ left: -BLEED, right: -BLEED, top: highlightTop + highlightH - 3 }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Abandoned drawdown preview — full design, unweaved portion desaturated
// ---------------------------------------------------------------------------

function AbandonedDrawdownView({
  projectId,
  currentPick,
  totalPicks,
}: {
  projectId: string;
  currentPick: number;
  totalPicks: number;
}) {
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const token = await getAuthToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`/api/projects/${projectId}/drawdown`, { credentials: "include", headers });
      const blob = await res.blob();
      if (cancelled) return;
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setImgSrc(url);
    }
    load().catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [projectId]);

  if (!imgSrc) return null;

  // Image is flipped: row 0 (top) = last pick, row N-1 (bottom) = pick 1.
  // currentPick is the next pick to weave — abandoned here without weaving it.
  // Unweaved: picks currentPick..totalPicks → top (totalPicks - currentPick + 1) rows.
  const unweavedFraction = (totalPicks - currentPick + 1) / totalPicks;
  const abandonPct = `${unweavedFraction * 100}%`;

  return (
    <div className="rounded-lg border overflow-x-auto relative bg-white dark:bg-zinc-900">
      <div className="relative">
        <img
          src={imgSrc}
          alt="Abandoned weaving pattern"
          className="block w-full"
          style={{ imageRendering: "pixelated" }}
        />
        {/* Desaturate unweaved portion — top of image */}
        <div
          className="absolute left-0 top-0 right-0 pointer-events-none"
          style={{
            height: abandonPct,
            backdropFilter: "saturate(0) brightness(1.6)",
            WebkitBackdropFilter: "saturate(0) brightness(1.6)",
          }}
        />
        <div
          className="absolute left-0 top-0 right-0 pointer-events-none bg-white/50 dark:bg-zinc-900/55"
          style={{ height: abandonPct }}
        />
        {/* Amber line at the abandon point */}
        <div
          className="absolute left-0 right-0 pointer-events-none h-[2px] bg-amber-500"
          style={{ top: abandonPct }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step controls
// ---------------------------------------------------------------------------

function StepControls({
  currentPick,
  total,
  onStep,
  onJump,
  stepping,
}: {
  currentPick: number;
  total: number;
  onStep: (dir: "advance" | "reverse") => void;
  onJump: (pick: number) => void;
  stepping: boolean;
}) {
  const atStart = currentPick <= 1;
  const pastEnd = currentPick > total;
  const disabled = stepping;

  return (
    <div className="flex items-center justify-center gap-2 sm:gap-3">
      {/* ‹‹ back 10 — visible on sm+ */}
      <button
        onClick={() => onJump(Math.max(1, currentPick - 10))}
        disabled={atStart || disabled}
        className="hidden sm:flex h-12 w-12 items-center justify-center rounded-full border-2 border-input text-lg font-medium transition-colors hover:border-ring hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Back 10 picks"
        title="Back 10"
      >
        ‹‹
      </button>

      <button
        onClick={() => onStep("reverse")}
        disabled={atStart || disabled}
        className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-input text-3xl font-light transition-colors hover:border-ring hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Previous pick"
      >
        ‹
      </button>

      <div className="text-center min-w-28">
        <p className="text-5xl font-bold tabular-nums">
          {Math.min(currentPick, total)}
        </p>
        <p className="text-sm text-muted-foreground">of {total}</p>
      </div>

      <button
        onClick={() => onStep("advance")}
        disabled={pastEnd || disabled}
        className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-input text-3xl font-light transition-colors hover:border-ring hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Next pick"
      >
        ›
      </button>

      {/* ›› forward 10 — visible on sm+ */}
      <button
        onClick={() => onJump(Math.min(total + 1, currentPick + 10))}
        disabled={pastEnd || disabled}
        className="hidden sm:flex h-12 w-12 items-center justify-center rounded-full border-2 border-input text-lg font-medium transition-colors hover:border-ring hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Forward 10 picks"
        title="Forward 10"
      >
        ››
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Jump-to-pick input
// ---------------------------------------------------------------------------

function JumpToPick({
  total,
  onJump,
  disabled,
}: {
  total: number;
  onJump: (pick: number) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const n = parseInt(value, 10);
    if (!isNaN(n)) {
      onJump(Math.max(1, Math.min(n, total + 1)));
      setValue("");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex items-center justify-center gap-2">
      <label className="text-xs text-muted-foreground">Go to pick</label>
      <input
        type="number"
        min={1}
        max={total}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        className="w-20 rounded border border-input bg-background px-2 py-1 text-sm text-center focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
        placeholder="—"
      />
      <button
        type="submit"
        disabled={disabled || !value}
        className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-30"
      >
        Go
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Progress bar
// ---------------------------------------------------------------------------

function ProgressBar({ current, total }: { current: number; total: number }) {
  const pct = total > 0 ? Math.round((Math.min(current - 1, total) / total) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
        <span>{pct}% complete</span>
        <span>{Math.max(0, total - current + 1)} picks remaining</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full bg-primary transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Completed summary
// ---------------------------------------------------------------------------

function PhotoGrid({
  activityId,
  photos,
  onUploaded,
  onDeleted,
}: {
  activityId: string;
  photos: ActivityPhoto[];
  onUploaded: (p: ActivityPhoto) => void;
  onDeleted: (id: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setError(null);
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        if (photos.length >= 20) { setError("Maximum 20 photos reached."); break; }
        const photo = await uploadActivityPhoto(activityId, file);
        onUploaded(photo);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (photoId: string) => {
    await deleteActivityPhoto(activityId, photoId);
    onDeleted(photoId);
    setConfirmDeleteId(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium">Photos <span className="text-muted-foreground font-normal">({photos.length}/20)</span></p>
        {photos.length < 20 && (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "+ Add photo"}
          </button>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      {error && <p className="mb-2 text-xs text-destructive">{error}</p>}
      {photos.length === 0 ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="w-full rounded-lg border border-dashed p-8 text-sm text-muted-foreground hover:border-ring hover:text-foreground transition-colors disabled:opacity-50"
        >
          Add photos to document your work
        </button>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
          {photos.map((p) => (
            <div key={p.id} className="group relative aspect-square">
              <AuthedImage
                src={activityPhotoUrl(activityId, p.id)}
                alt={p.filename}
                className="w-full h-full object-cover rounded-md border cursor-pointer"
                onClick={() => setLightbox(p.id)}
              />
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(p.id); }}
                className="absolute top-1 right-1 hidden group-hover:flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white text-xs hover:bg-black/80"
                aria-label="Delete photo"
              >
                ✕
              </button>
            </div>
          ))}
          {photos.length < 20 && (
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
              className="aspect-square rounded-md border border-dashed flex items-center justify-center text-muted-foreground hover:border-ring hover:text-foreground transition-colors disabled:opacity-50 text-2xl"
            >
              +
            </button>
          )}
        </div>
      )}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightbox(null)}
        >
          <AuthedImage
            src={activityPhotoUrl(activityId, lightbox)}
            alt=""
            className="max-h-full max-w-full rounded-lg shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            onClick={() => setLightbox(null)}
            className="absolute top-4 right-4 text-white/70 hover:text-white text-sm"
          >
            Close ✕
          </button>
        </div>
      )}
      {confirmDeleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-background rounded-lg border p-6 max-w-sm w-full space-y-4">
            <p className="text-sm">Delete this photo? This cannot be undone.</p>
            <div className="flex gap-2">
              <Button size="sm" variant="destructive" onClick={() => handleDelete(confirmDeleteId)}>Delete</Button>
              <Button size="sm" variant="outline" onClick={() => setConfirmDeleteId(null)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CompletedSummary({
  activity,
  siblings,
  onPhotosChange,
}: {
  activity: import("@/api/activities").ActivityDetail;
  siblings: ActivitySummary[];
  onPhotosChange: (photos: ActivityPhoto[]) => void;
}) {
  const [photos, setPhotos] = useState<ActivityPhoto[]>(activity.photos);

  const pct = activity.total_picks > 0
    ? Math.round(((activity.current_pick - 1) / activity.total_picks) * 100)
    : 100;
  const completedDate = activity.completed_at
    ? new Date(activity.completed_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })
    : null;

  const handleUploaded = (p: ActivityPhoto) => {
    const next = [...photos, p];
    setPhotos(next);
    onPhotosChange(next);
  };

  const handleDeleted = (id: string) => {
    const next = photos.filter((p) => p.id !== id);
    setPhotos(next);
    onPhotosChange(next);
  };

  return (
    <div className="mx-auto max-w-2xl px-6 py-6 space-y-6">
      {/* Metrics */}
      <div className="rounded-lg border p-5 space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Summary</h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          {completedDate && (
            <><dt className="text-muted-foreground">Completed</dt><dd>{completedDate}</dd></>
          )}
          <dt className="text-muted-foreground">Picks woven</dt>
          <dd>{activity.total_picks} picks ({pct}%)</dd>
          {activity.num_items > 1 && (
            <><dt className="text-muted-foreground">Items</dt><dd>{activity.num_items}</dd></>
          )}
          {activity.finished_length_per_item && (
            <><dt className="text-muted-foreground">Length / item</dt>
            <dd>{activity.finished_length_per_item} {activity.length_unit}</dd></>
          )}
          {activity.warp_waste_allowance && (
            <><dt className="text-muted-foreground">Warp waste</dt>
            <dd>{activity.warp_waste_allowance} {activity.length_unit}</dd></>
          )}
          <dt className="text-muted-foreground">Type</dt>
          <dd>{ACTIVITY_TYPE_LABELS[activity.activity_type]}</dd>
        </dl>
      </div>

      {/* Design preview */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-2">Design Preview</h2>
        <div className="overflow-auto rounded-lg border bg-white p-2">
          <AuthedImage
            src={previewUrl(activity.project_id)}
            alt={`Design for ${activity.project_name}`}
            className="max-w-full mx-auto block"
            style={{ imageRendering: "pixelated" }}
          />
        </div>
      </div>

      {/* Links */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Link
          to={`/projects/${activity.project_id}`}
          className="rounded-lg border p-4 hover:border-ring transition-colors block"
        >
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Project</p>
          <p className="font-medium text-sm">{activity.project_name}</p>
        </Link>
        {activity.loom_id && activity.loom_name && (
          <Link
            to={`/looms/${activity.loom_id}`}
            className="rounded-lg border p-4 hover:border-ring transition-colors block"
          >
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Loom</p>
            <p className="font-medium text-sm">{activity.loom_name}</p>
          </Link>
        )}
      </div>

      {/* Sibling activities */}
      {siblings.length > 0 && (
        <div>
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-2">Other activities on this project</h2>
          <div className="space-y-1">
            {siblings.map((s) => {
              const isPlanning = s.status === "active" && !s.loom_id;
              const label = isPlanning ? "Plan" : ACTIVITY_STATUS_LABELS[s.status];
              const badgeCls = isPlanning
                ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                : s.status === "active"
                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                  : "bg-muted text-muted-foreground";
              return (
                <Link
                  key={s.id}
                  to={`/activities/${s.id}`}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm hover:border-ring transition-colors"
                >
                  <span>{s.name}</span>
                  <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${badgeCls}`}>{label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Photos */}
      <PhotoGrid
        activityId={activity.id}
        photos={photos}
        onUploaded={handleUploaded}
        onDeleted={handleDeleted}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function ActivityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [stepping, setStepping] = useState(false);
  const [colorMode, setColorMode] = useState<ColorMode>("strip");
  const [showWeftColor, setShowWeftColor] = useState(true);
  const [showDesignPreview, setShowDesignPreview] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [showAssignLoom, setShowAssignLoom] = useState(false);
  const [confirmComplete, setConfirmComplete] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmClone, setConfirmClone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [cloneConflict, setCloneConflict] = useState<ActivitySummary | null>(null);
  const [restartConflict, setRestartConflict] = useState<ActivitySummary | null>(null);
  const [localPick, setLocalPick] = useState(1);

  const { data: activity, isLoading, error } = useQuery({
    queryKey: ["activity", id],
    queryFn: () => getActivity(id!),
    enabled: !!id,
  });

  const { data: picksData } = useQuery({
    queryKey: ["activity-picks", id],
    queryFn: () => getActivityPicks(id!),
    enabled: !!id,
    staleTime: Infinity,
  });

  const isPlanning = activity?.status === "active" && !activity?.loom_id;
  const isCompleted = activity?.status === "completed";

  const { data: allActivities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities(),
    enabled: isPlanning || showAssignLoom,
  });

  const { data: siblingActivities = [] } = useQuery({
    queryKey: ["activities", { projectId: activity?.project_id }],
    queryFn: () => listActivities({ projectId: activity!.project_id }),
    enabled: isCompleted && !!activity?.project_id,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["activity", id] });

  const handleJump = useCallback(async (pick: number) => {
    if (!id || stepping) return;
    setStepping(true);
    try {
      const updated = await jumpActivity(id, pick);
      queryClient.setQueryData<typeof activity>(["activity", id], (old) =>
        old ? { ...updated, photos: old.photos } : updated
      );
    } finally {
      setStepping(false);
    }
  }, [id, stepping, queryClient]);

  const handleStep = useCallback(async (direction: "advance" | "reverse") => {
    if (!id || stepping) return;
    setStepping(true);
    try {
      const updated = await stepActivity(id, direction);
      queryClient.setQueryData<typeof activity>(["activity", id], (old) =>
        old ? { ...updated, photos: old.photos } : updated
      );
    } finally {
      setStepping(false);
    }
  }, [id, stepping, queryClient]);

  const handleLocalStep = useCallback((direction: "advance" | "reverse") => {
    setLocalPick((prev) => {
      const total = activity?.total_picks ?? 1;
      if (direction === "advance") return Math.min(prev + 1, total + 1);
      return Math.max(1, prev - 1);
    });
  }, [activity?.total_picks]);

  const handleLocalJump = useCallback((pick: number) => {
    const total = activity?.total_picks ?? 1;
    setLocalPick(Math.max(1, Math.min(pick, total + 1)));
  }, [activity?.total_picks]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (isPlanning) {
        if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); handleLocalStep("advance"); }
        if (e.key === "ArrowLeft") { e.preventDefault(); handleLocalStep("reverse"); }
        return;
      }
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); handleStep("advance"); }
      if (e.key === "ArrowLeft") { e.preventDefault(); handleStep("reverse"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleStep, handleLocalStep, isPlanning]);

  const handleComplete = async () => {
    if (!id) return;
    setActionLoading(true);
    try { await completeActivity(id); invalidate(); setConfirmComplete(false); }
    finally { setActionLoading(false); }
  };

  const handleAbandon = async () => {
    if (!id) return;
    setActionLoading(true);
    try { await abandonActivity(id); invalidate(); setConfirmAbandon(false); }
    finally { setActionLoading(false); }
  };

  const handleRestart = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await restartActivity(id);
      invalidate();
      setConfirmRestart(false);
      setRestartConflict(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && activity?.loom_id) {
        const activities = await listActivities().catch(() => []);
        setRestartConflict(activities.find((a) => a.loom_id === activity.loom_id && a.status === "active") ?? null);
        setConfirmRestart(false);
      }
    } finally { setActionLoading(false); }
  };

  const handleResolveAndRestart = async (resolve: "complete" | "abandon") => {
    if (!restartConflict || !id) return;
    setActionLoading(true);
    try {
      if (resolve === "complete") await completeActivity(restartConflict.id);
      else await abandonActivity(restartConflict.id);
      await restartActivity(id);
      invalidate();
      setRestartConflict(null);
    } finally { setActionLoading(false); }
  };

  const handleClone = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      const cloned = await cloneActivity(id);
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      setConfirmClone(false);
      navigate(`/activities/${cloned.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && activity?.loom_id) {
        const activities = await listActivities().catch(() => []);
        setCloneConflict(activities.find((a) => a.loom_id === activity.loom_id && a.status === "active") ?? null);
        setConfirmClone(false);
      }
    } finally { setActionLoading(false); }
  };

  const handleResolveAndClone = async (resolve: "complete" | "abandon") => {
    if (!cloneConflict || !id) return;
    setActionLoading(true);
    try {
      if (resolve === "complete") await completeActivity(cloneConflict.id);
      else await abandonActivity(cloneConflict.id);
      const cloned = await cloneActivity(id);
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      setCloneConflict(null);
      navigate(`/activities/${cloned.id}`);
    } finally { setActionLoading(false); }
  };

  const handleDelete = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await deleteActivity(id);
      queryClient.invalidateQueries({ queryKey: ["activities"] });
      navigate("/activities", { replace: true });
    } finally { setActionLoading(false); }
  };

  if (isLoading) return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  );
  if (error || !activity) return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-destructive">Activity not found.</p>
    </div>
  );

  const displayPick = isPlanning ? localPick : activity.current_pick;
  const currentPickIndex = displayPick - 1;
  const declaredCount = activity.activity_type === "lift"
    ? (activity.project_num_shafts ?? 0)
    : (activity.project_num_treadles ?? 0);
  const maxFromPicks = picksData ? Math.max(0, ...picksData.picks.flatMap((p) => p.active)) : 0;
  const maxActive = declaredCount > 0 ? declaredCount : maxFromPicks;

  const isFinished = displayPick > activity.total_picks;
  const isActiveTracking = activity.status === "active" && !isPlanning;
  const isAbandoned = activity.status === "abandoned";

  // Badge for planning vs active
  const badgeClasses = isPlanning
    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
    : activity.status === "active"
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : "bg-muted text-muted-foreground";
  const badgeLabel = isPlanning ? "Plan" : ACTIVITY_STATUS_LABELS[activity.status];

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="shrink-0 border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/activities" className="text-sm text-muted-foreground hover:text-foreground">
            ← Activities
          </Link>
          <div className="flex items-center gap-2">
            {editingName ? (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const trimmed = nameInput.trim();
                  if (!trimmed) { setEditingName(false); return; }
                  const updated = await renameActivity(id!, trimmed);
                  queryClient.setQueryData<typeof activity>(["activity", id], (old) =>
                    old ? { ...updated, photos: old.photos } : updated
                  );
                  queryClient.invalidateQueries({ queryKey: ["activities"] });
                  setEditingName(false);
                }}
                className="flex items-center gap-2"
              >
                <input
                  autoFocus
                  className="rounded border border-input bg-background px-2 py-0.5 text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-ring"
                  value={nameInput}
                  onChange={(e) => setNameInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Escape") setEditingName(false); }}
                  onBlur={async () => {
                    const trimmed = nameInput.trim();
                    if (trimmed && trimmed !== activity.name) {
                      const updated = await renameActivity(id!, trimmed);
                      queryClient.setQueryData<typeof activity>(["activity", id], (old) =>
                        old ? { ...updated, photos: old.photos } : updated
                      );
                      queryClient.invalidateQueries({ queryKey: ["activities"] });
                    }
                    setEditingName(false);
                  }}
                />
              </form>
            ) : (
              <button
                onClick={() => { setNameInput(activity.name); setEditingName(true); }}
                className="font-semibold hover:underline decoration-dashed underline-offset-2 cursor-text"
                title="Click to rename"
              >
                {activity.name}
              </button>
            )}
            <span className="text-sm text-muted-foreground">{activity.project_name}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDesignPreview(true)}
            className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
            title="View WIF design preview"
          >
            View design
          </button>
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${badgeClasses}`}>
            {badgeLabel}
          </span>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        {/* Completed summary */}
        {isCompleted && (
          <CompletedSummary
            activity={activity}
            siblings={siblingActivities.filter((s) => s.id !== id)}
            onPhotosChange={(photos) =>
              queryClient.setQueryData(["activity", id], { ...activity, photos })
            }
          />
        )}

        {/* Planning banner */}
        {isPlanning && (
          <div className="mx-auto max-w-2xl px-8 pt-6">
            <div className="rounded-md border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/30 text-sm overflow-hidden">
              <div className="px-4 py-3">
                <p className="font-medium text-blue-900 dark:text-blue-200">Planning mode — design preview only</p>
                <p className="mt-0.5 text-xs text-blue-800 dark:text-blue-300">Assign a loom to start tracking picks.</p>
              </div>
              <div className="border-t border-blue-200 dark:border-blue-800 px-3 pb-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAssignLoom(true)}
                  className="w-full rounded-md border border-dashed border-blue-300 dark:border-blue-700 px-3 py-1.5 text-xs font-medium text-blue-800 dark:text-blue-300 transition-colors hover:border-blue-500 dark:hover:border-blue-500 hover:bg-blue-100 dark:hover:bg-blue-900/40 hover:text-blue-900 dark:hover:text-blue-200"
                >
                  Assign to loom…
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Abandoned banner */}
        {isAbandoned && (
          <div className="mx-auto max-w-2xl px-8 pt-6">
            <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 px-4 py-3 text-sm">
              <p className="font-medium text-amber-900 dark:text-amber-200">This activity was not completed</p>
              <p className="mt-0.5 text-xs text-amber-800 dark:text-amber-300">
                Abandoned at pick {activity.current_pick} of {activity.total_picks}
                {" "}({Math.round((activity.current_pick - 1) / activity.total_picks * 100)}% woven)
                {activity.abandoned_at && ` · ${new Date(activity.abandoned_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}`}
              </p>
            </div>
          </div>
        )}

        {/* Progress + color mode */}
        <div className="mx-auto max-w-2xl px-8 pt-6 space-y-3">
          {!isPlanning && !isCompleted && <ProgressBar current={activity.current_pick} total={activity.total_picks} />}
          {picksData?.has_weft_colors && !isFinished && !isCompleted && (
            <div className="flex items-center justify-end gap-4">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <span className="text-xs text-muted-foreground">Weft color</span>
                <button
                  role="switch"
                  aria-checked={showWeftColor}
                  onClick={() => setShowWeftColor((v) => !v)}
                  className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 ${showWeftColor ? "bg-primary" : "bg-muted"}`}
                >
                  <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${showWeftColor ? "translate-x-4" : "translate-x-1"}`} />
                </button>
              </label>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Color mode</span>
                <div className="inline-flex rounded-md border border-input overflow-hidden text-xs">
                  {(["theme", "strip", "filled"] as ColorMode[]).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setColorMode(mode)}
                      className={`px-2.5 py-1 capitalize transition-colors ${
                        colorMode === mode
                          ? "bg-primary text-primary-foreground"
                          : "bg-background text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Pick instruction — stays compact */}
        {!isCompleted && <div className="mx-auto max-w-2xl px-8 pt-4">
          {isFinished ? (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-lg font-medium">All {activity.total_picks} picks complete!</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Mark the activity as completed when you're done.
              </p>
              {isActiveTracking && (
                <div className="mt-6">
                  {!confirmComplete ? (
                    <Button onClick={() => setConfirmComplete(true)}>Mark complete</Button>
                  ) : (
                    <div className="flex items-center justify-center gap-2">
                      <span className="text-sm">Mark this activity as completed?</span>
                      <Button size="sm" onClick={handleComplete} disabled={actionLoading}>Confirm</Button>
                      <Button size="sm" variant="outline" onClick={() => setConfirmComplete(false)} disabled={actionLoading}>Cancel</Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : picksData ? (
            <PickDisplay
              pick={picksData.picks[currentPickIndex]}
              totalCount={maxActive}
              activityType={activity.activity_type}
              colorMode={colorMode}
              showWeftColor={showWeftColor}
            />
          ) : (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-sm text-muted-foreground">Pick data loading…</p>
            </div>
          )}
        </div>}

        {/* Pattern view — wider on large screens to show more warp threads */}
        {picksData && !isFinished && !isCompleted && !isAbandoned && (
          <div className="mx-auto w-full max-w-2xl lg:max-w-5xl xl:max-w-7xl px-8 pb-4 pt-4">
            <WeavingPatternView
              projectId={activity.project_id}
              currentPickIndex={currentPickIndex}
              totalPicks={activity.total_picks}
              picks={picksData.picks}
              maxActive={maxActive}
            />
          </div>
        )}

        {/* Abandoned design preview — full drawdown with unweaved portion desaturated */}
        {isAbandoned && (
          <div className="mx-auto w-full max-w-2xl lg:max-w-5xl xl:max-w-7xl px-8 pb-4 pt-4">
            <AbandonedDrawdownView
              projectId={activity.project_id}
              currentPick={activity.current_pick}
              totalPicks={activity.total_picks}
            />
          </div>
        )}

        {/* Step controls — active tracking and planning */}
        <div className="mx-auto max-w-lg px-8 pb-6 space-y-6">
          {(isActiveTracking || isPlanning) && !isFinished && (
            <StepControls
              currentPick={displayPick}
              total={activity.total_picks}
              onStep={isPlanning ? handleLocalStep : handleStep}
              onJump={isPlanning ? handleLocalJump : handleJump}
              stepping={stepping}
            />
          )}

          {(isActiveTracking || isPlanning) && !isFinished && (
            <JumpToPick
              total={activity.total_picks}
              onJump={isPlanning ? handleLocalJump : handleJump}
              disabled={stepping}
            />
          )}

          {(isActiveTracking || isPlanning) && (
            <p className="text-center text-xs text-muted-foreground">
              ← → arrow keys or spacebar to navigate picks
            </p>
          )}
        </div>

        {/* Collapsible sections */}
        <div className="mx-auto max-w-2xl px-8 pb-10 space-y-0 border-t">
          {!isCompleted && (
            <CollapsibleSection title={`Photos (${activity.photos.length}/20)`} defaultOpen={isAbandoned}>
              <PhotoGrid
                activityId={activity.id}
                photos={activity.photos}
                onUploaded={(p) =>
                  queryClient.setQueryData<typeof activity>(["activity", id], (old) =>
                    old ? { ...old, photos: [...old.photos, p] } : old
                  )
                }
                onDeleted={(photoId) =>
                  queryClient.setQueryData<typeof activity>(["activity", id], (old) =>
                    old ? { ...old, photos: old.photos.filter((ph) => ph.id !== photoId) } : old
                  )
                }
              />
            </CollapsibleSection>
          )}

          <CollapsibleSection title="Details">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Type</dt>
              <dd>{ACTIVITY_TYPE_LABELS[activity.activity_type]}</dd>
              {activity.loom_name && (
                <><dt className="text-muted-foreground">Loom</dt><dd>{activity.loom_name}</dd></>
              )}
              {activity.num_items > 1 && (
                <><dt className="text-muted-foreground">Items</dt><dd>{activity.num_items}</dd></>
              )}
              {activity.finished_length_per_item && (
                <><dt className="text-muted-foreground">Length / item</dt>
                <dd>{activity.finished_length_per_item} {activity.length_unit}</dd></>
              )}
              {activity.warp_waste_allowance && (
                <><dt className="text-muted-foreground">Warp waste</dt>
                <dd>{activity.warp_waste_allowance} {activity.length_unit}</dd></>
              )}
              {activity.completed_at && (
                <><dt className="text-muted-foreground">Completed</dt>
                <dd>{new Date(activity.completed_at).toLocaleDateString()}</dd></>
              )}
            </dl>
          </CollapsibleSection>

          {/* Active tracking: complete / abandon */}
          {isActiveTracking && (
            <CollapsibleSection title="Actions">
              <div className="flex flex-wrap gap-2">
                {!confirmComplete && !confirmAbandon && (
                  <>
                    <Button variant="outline" size="sm" onClick={() => setConfirmComplete(true)}>
                      Mark complete
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setConfirmAbandon(true)}>
                      Abandon
                    </Button>
                  </>
                )}
                {confirmComplete && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Mark this activity as completed?</span>
                    <Button size="sm" onClick={handleComplete} disabled={actionLoading}>Confirm</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmComplete(false)} disabled={actionLoading}>Cancel</Button>
                  </div>
                )}
                {confirmAbandon && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-destructive">Abandon this activity?</span>
                    <Button size="sm" onClick={handleAbandon} disabled={actionLoading}>Confirm</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmAbandon(false)} disabled={actionLoading}>Cancel</Button>
                  </div>
                )}
              </div>
            </CollapsibleSection>
          )}

          {activity.status === "abandoned" && (
            <CollapsibleSection title="Actions">
              <div className="space-y-3">
                {!confirmRestart && !restartConflict && (
                  <Button variant="outline" size="sm" onClick={() => setConfirmRestart(true)}>
                    Restart activity
                  </Button>
                )}
                {confirmRestart && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Resume from pick {activity.current_pick}?</span>
                    <Button size="sm" onClick={handleRestart} disabled={actionLoading}>Confirm</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmRestart(false)} disabled={actionLoading}>Cancel</Button>
                  </div>
                )}
                {restartConflict && (
                  <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700 px-3 py-3 text-sm space-y-2">
                    <p className="font-medium text-amber-900 dark:text-amber-200">
                      This loom has an active activity: <span className="font-semibold">{restartConflict.name}</span>
                    </p>
                    <p className="text-amber-800 dark:text-amber-300 text-xs">Resolve it to restart this one.</p>
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button type="button" size="sm" onClick={() => handleResolveAndRestart("complete")} disabled={actionLoading}>
                        {actionLoading ? "Working…" : "Mark completed & restart"}
                      </Button>
                      <Button type="button" size="sm" variant="outline" onClick={() => handleResolveAndRestart("abandon")} disabled={actionLoading}>
                        {actionLoading ? "Working…" : "Abandon & restart"}
                      </Button>
                      <Button type="button" size="sm" variant="ghost" onClick={() => setRestartConflict(null)} disabled={actionLoading}>
                        Dismiss
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </CollapsibleSection>
          )}

          <CollapsibleSection title="Clone activity">
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Create a new activity with the same configuration, starting at pick 1.</p>
              {!confirmClone && !cloneConflict && (
                <Button variant="outline" size="sm" onClick={() => setConfirmClone(true)}>
                  Clone activity
                </Button>
              )}
              {confirmClone && (
                <div className="flex items-center gap-2">
                  <span className="text-sm">Start a new activity with the same settings?</span>
                  <Button size="sm" onClick={handleClone} disabled={actionLoading}>{actionLoading ? "Cloning…" : "Confirm"}</Button>
                  <Button size="sm" variant="outline" onClick={() => setConfirmClone(false)} disabled={actionLoading}>Cancel</Button>
                </div>
              )}
              {cloneConflict && (
                <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700 px-3 py-3 text-sm space-y-2">
                  <p className="font-medium text-amber-900 dark:text-amber-200">
                    This loom has an active activity: <span className="font-semibold">{cloneConflict.name}</span>
                  </p>
                  <p className="text-amber-800 dark:text-amber-300 text-xs">Resolve it to start the clone.</p>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button type="button" size="sm" onClick={() => handleResolveAndClone("complete")} disabled={actionLoading}>
                      {actionLoading ? "Working…" : "Mark completed & clone"}
                    </Button>
                    <Button type="button" size="sm" variant="outline" onClick={() => handleResolveAndClone("abandon")} disabled={actionLoading}>
                      {actionLoading ? "Working…" : "Abandon & clone"}
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => setCloneConflict(null)} disabled={actionLoading}>
                      Dismiss
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </CollapsibleSection>

          <CollapsibleSection title="Danger zone">
            {!confirmDelete ? (
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>
                Delete activity
              </Button>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-destructive">
                  Delete this activity and all step history? This cannot be undone.
                </p>
                <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)} disabled={actionLoading}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleDelete}
                  disabled={actionLoading}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {actionLoading ? "Deleting…" : "Confirm delete"}
                </Button>
              </div>
            )}
          </CollapsibleSection>
        </div>
      </main>

      {showDesignPreview && (
        <DesignPreviewModal
          projectId={activity.project_id}
          onClose={() => setShowDesignPreview(false)}
        />
      )}

      {showAssignLoom && (
        <AssignLoomModal
          activityId={activity.id}
          activeActivities={allActivities.filter((a) => a.status === "active")}
          onSuccess={() => {
            setShowAssignLoom(false);
            invalidate();
            queryClient.invalidateQueries({ queryKey: ["activities"] });
          }}
          onClose={() => setShowAssignLoom(false)}
        />
      )}
    </div>
  );
}
