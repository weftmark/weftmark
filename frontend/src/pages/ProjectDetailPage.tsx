import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { AppIcons } from "@/lib/icons";
import { usePresentMode } from "@/hooks/usePresentMode";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, displayLength } from "@/lib/units";
import {
  getProject, getProjectPicks, getProjectMetrics, stepProject, jumpProject, completeProject, abandonProject,
  restartProject, cloneProject, listProjects, deleteProject, startProject,
  renameProject, updateProjectNotes, uploadProjectPhoto, deleteProjectPhoto, projectPhotoUrl,
  advanceItem, jumpItem,
  ApiError, PROJECT_TYPE_LABELS, PROJECT_STATUS_LABELS,
  type ProjectSummary, type ProjectPhoto, type PickRow, type ProjectMetrics,
} from "@/api/projects";
import { drawdownPreviewUrl, projectDrawdownPreviewUrl } from "@/api/projects";
import { getAuthToken } from "@/api/client";
import { AssignLoomModal } from "@/components/projects/AssignLoomModal";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { Button } from "@/components/ui/button";
import { SuperuserInspectionBanner } from "@/components/ui/SuperuserInspectionBanner";

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
// Metrics helpers
// ---------------------------------------------------------------------------

function fmtDuration(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${totalSec}s`;
}

function SessionMetricsPanel({ metrics }: { metrics: ProjectMetrics }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!metrics.current_session_started_at) return;
    const tick = () =>
      setElapsed(Date.now() - new Date(metrics.current_session_started_at!).getTime());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [metrics.current_session_started_at]);

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      <dt className="text-muted-foreground">Total woven picks</dt>
      <dd>{metrics.total_worked_picks}</dd>
      <dt className="text-muted-foreground">Total advances</dt>
      <dd>{metrics.total_advance_steps}</dd>
      <dt className="text-muted-foreground">Reverses</dt>
      <dd>{metrics.total_reverse_steps}</dd>
      <dt className="text-muted-foreground">Sessions</dt>
      <dd>{metrics.total_sessions}</dd>
      <dt className="text-muted-foreground">Total weaving time</dt>
      <dd>{fmtDuration(metrics.total_session_time_ms)}</dd>
      {metrics.current_session_started_at && (
        <>
          <dt className="text-muted-foreground">Current session</dt>
          <dd className="text-accent font-medium">{fmtDuration(elapsed)}</dd>
        </>
      )}
    </dl>
  );
}

// ---------------------------------------------------------------------------
// WIF design preview modal
// ---------------------------------------------------------------------------

function DesignPreviewModal({
  projectId,
  hasDrawdownPreview,
  colorReplacements,
  onClose,
}: {
  projectId: string;
  hasDrawdownPreview: boolean;
  colorReplacements: Record<string, string> | null;
  onClose: () => void;
}) {
  const src = hasDrawdownPreview
    ? projectDrawdownPreviewUrl(projectId)
    : drawdownPreviewUrl(projectId, colorReplacements ?? undefined);
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
          src={src}
          alt="WIF design preview"
          className="max-h-[80vh] mx-auto block rounded-lg shadow-2xl"
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
  projectType,
  colorMode,
  showWeftColor,
}: {
  pick: PickRow;
  totalCount: number;
  projectType: string;
  colorMode: ColorMode;
  showWeftColor: boolean;
}) {
  const count = Math.max(totalCount, 1);
  const weftHex = pick.color ?? null;

  return (
    <div className="rounded-xl border-2 border-primary/30 bg-primary/5 dark:bg-primary/10 px-4 py-4 h-28 flex items-stretch gap-4 mx-auto w-full"
      style={{ maxWidth: `${Math.min(count * 80 + 80, 720)}px` }}>
      {/* Activity type icon — centered vertically */}
      <div className="shrink-0 flex items-center text-primary/50">
        {projectType === "lift" ? (
          <AppIcons.lift className="h-8 w-8" strokeWidth={1.5} />
        ) : (
          <AppIcons.treadle className="h-8 w-8" strokeWidth={1.5} />
        )}
      </div>

      {/* Box grid + optional weft bar — fills remaining height */}
      <div className="flex-1 flex flex-col gap-2 min-h-0">
        <div
          className="flex-1 grid gap-1.5 min-h-0"
          style={{ gridTemplateColumns: `repeat(${count}, 1fr)` }}
        >
          {Array.from({ length: count }, (_, i) => i + 1).map((n) => {
            const active = pick.active.includes(n);
            if (colorMode !== "theme" && active && weftHex) {
              if (colorMode === "filled") {
                const fg = contrastColor(weftHex);
                return (
                  <div key={n} style={{ backgroundColor: weftHex, borderColor: fg }}
                    className="rounded-md border-2 flex items-center justify-center text-xs font-bold">
                    <span style={{ color: fg }}>{n}</span>
                  </div>
                );
              }
              if (colorMode === "strip") {
                return (
                  <div key={n}
                    className="rounded-md border-2 relative overflow-hidden border-primary bg-primary flex items-center justify-center text-xs font-bold">
                    <span className="absolute bottom-0 left-0 right-0 h-[20%]"
                      style={{ backgroundColor: weftHex }} />
                    <span className="relative text-primary-foreground">{n}</span>
                  </div>
                );
              }
            }
            return (
              <div key={n}
                className={`rounded-md border-2 flex items-center justify-center text-xs font-bold ${
                  active
                    ? "bg-primary border-primary text-primary-foreground"
                    : "border-border bg-muted/60 text-foreground/70"
                }`}>
                {n}
              </div>
            );
          })}
        </div>

        {showWeftColor && weftHex && (
          <div
            className="h-6 w-full shrink-0 rounded-md flex items-center justify-center text-xs font-semibold uppercase tracking-wider"
            style={{ backgroundColor: weftHex, color: contrastColor(weftHex) }}
          >
            Weft Color
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Weaving pattern view — drawdown image windowed to current pick
// ---------------------------------------------------------------------------

// Overhead accounts for: app header, project header, progress bar,
// controls bar, pick instruction card, step controls, padding, and details panel bar.
const PATTERN_OVERHEAD_PX = 600;
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

type DrawdownPayload = {
  cell_px: number;
  warp_count: number;
  weft_count: number;
  floats: [number, number, number, number, string][];
};

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
  const [drawdownData, setDrawdownData] = useState<DrawdownPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const lsColKey = `project-drawdown-col-${projectId}`;

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const token = await getAuthToken();
        const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(`/api/projects/${projectId}/drawdown/data?cell_px=20`, { headers, credentials: "include" });
        if (!res.ok) throw new Error(`Pattern failed to load (${res.status})`);
        const data = (await res.json()) as DrawdownPayload;
        if (cancelled) return;
        setDrawdownData(data);
        try {
          const saved = localStorage.getItem(lsColKey);
          if (saved !== null && scrollRef.current) {
            scrollRef.current.scrollLeft = parseInt(saved, 10) || 0;
          }
        } catch { /* localStorage unavailable */ }
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Failed to load pattern");
      }
    }
    load();
    return () => { cancelled = true; };
  }, [projectId, lsColKey]);

  useEffect(() => {
    if (!drawdownData || !canvasRef.current) return;
    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    // Pass 1 — fill each float with its thread color
    for (const [x, y, w, h, fill] of drawdownData.floats) {
      ctx.fillStyle = fill;
      ctx.fillRect(x, y, w, h);
    }

    // Pass 2 — stroke all float borders in a single draw call
    const borders = new Path2D();
    for (const [x, y, w, h] of drawdownData.floats) {
      borders.rect(x, y, w, h);
    }
    ctx.strokeStyle = "#7f7f7f";
    ctx.lineWidth = 0.5;
    ctx.stroke(borders);
  }, [drawdownData]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    try { localStorage.setItem(lsColKey, String(e.currentTarget.scrollLeft)); } catch { /* noop */ }
  }, [lsColKey]);

  const pixelsPerRow = drawdownData?.cell_px ?? 20;
  const warpCount = drawdownData?.warp_count ?? 0;

  // Canvas is flipped: last pick at y=0 (top), first pick at bottom — matches PNG tile orientation.
  const flippedIndex = totalPicks - 1 - currentPickIndex;
  const translateY = containerH / 2 - pixelsPerRow / 2 - flippedIndex * pixelsPerRow;
  const futureRegionH = Math.max(0, containerH / 2 - pixelsPerRow / 2);
  const highlightTop = containerH / 2 - pixelsPerRow / 2 - 1;
  const highlightH = pixelsPerRow + 2;
  const boxH = Math.max(4, pixelsPerRow - 6);

  const reversedPicks = [...picks].reverse();

  const washoutOverlay = (
    <div
      className="absolute left-0 right-0 pointer-events-none"
      style={{
        top: 0,
        height: futureRegionH,
        background: "linear-gradient(to bottom, hsl(var(--background)) 20%, transparent)",
      }}
    />
  );

  if (!drawdownData) return (
    <div className="relative flex gap-2" style={{ height: containerH }}>
      <div className="flex-1 rounded-lg border overflow-hidden relative bg-muted flex flex-col items-center justify-center gap-2">
        {loadError ? (
          <span className="text-sm text-muted-foreground">{loadError}</span>
        ) : (
          <>
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Loading pattern…</span>
          </>
        )}
      </div>
      <div className="rounded-lg border overflow-hidden relative shrink-0 bg-muted animate-pulse" style={{ width: STEP_PANEL_W }} />
      <div className="rounded-lg border overflow-hidden relative shrink-0 bg-muted animate-pulse" style={{ width: COLOR_COL_W }} />
    </div>
  );

  return (
    <div className="relative flex gap-2" style={{ height: containerH }}>

      {/* Drawdown canvas — single load, translate to center current pick */}
      <div className="flex-1 relative rounded-lg border overflow-hidden">
        <div
          ref={scrollRef}
          className="absolute inset-0 overflow-x-auto overflow-y-hidden bg-white dark:bg-zinc-900"
          onScroll={handleScroll}
        >
          <div style={{ transform: `translateY(${translateY}px)`, transition: "transform 0.15s ease" }}>
            <canvas
              ref={canvasRef}
              width={warpCount * pixelsPerRow}
              height={(drawdownData?.weft_count ?? 0) * pixelsPerRow}
              style={{ display: "block", imageRendering: "pixelated" }}
            />
          </div>
        </div>
        {washoutOverlay}
      </div>

      {/* Lift/treadle step panel */}
      <div
        className="rounded-lg border overflow-hidden relative bg-background shrink-0"
        style={{ width: STEP_PANEL_W }}
      >
        <div style={{ transform: `translateY(${translateY}px)`, transition: "transform 0.15s ease", willChange: "transform" }}>
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
                    pick.active.includes(n) ? "bg-primary" : "bg-muted/40 ring-[0.5px] ring-border/40"
                  }`}
                  style={{ height: boxH }}
                />
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Weft color history column */}
      <div
        className="rounded-lg border overflow-hidden relative shrink-0"
        style={{ width: COLOR_COL_W }}
      >
        <div style={{ transform: `translateY(${translateY}px)`, transition: "transform 0.15s ease", willChange: "transform" }}>
          {reversedPicks.map((pick) => (
            <div
              key={pick.pick}
              style={{ height: pixelsPerRow, backgroundColor: pick.color ?? "hsl(var(--muted))" }}
            />
          ))}
        </div>
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
  draftId,
  currentPick,
  totalPicks,
}: {
  draftId: string;
  currentPick: number;
  totalPicks: number;
}) {
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const token = await getAuthToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`/api/drafts/${draftId}/drawdown`, { credentials: "include", headers });
      if (!res.ok) {
        if (!cancelled) setLoadError(true);
        return;
      }
      const blob = await res.blob();
      if (cancelled) return;
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(blob);
      objectUrlRef.current = url;
      setImgSrc(url);
    }
    load().catch(() => { if (!cancelled) setLoadError(true); });
    return () => {
      cancelled = true;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [draftId]);

  if (loadError) return (
    <div className="flex items-center justify-center rounded-lg border bg-muted text-muted-foreground text-sm p-6">
      Pattern preview unavailable for this design.
    </div>
  );
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
        className="hidden sm:flex h-12 w-12 items-center justify-center rounded-full border-2 border-primary/40 text-primary/70 text-lg font-medium transition-colors hover:border-primary hover:bg-primary/10 disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Back 10 picks"
        title="Back 10"
      >
        ‹‹
      </button>

      <button
        onClick={() => onStep("reverse")}
        disabled={atStart || disabled}
        className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-primary text-primary text-3xl font-light transition-colors hover:bg-primary hover:text-primary-foreground disabled:opacity-30 disabled:cursor-not-allowed"
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
        className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-primary text-primary text-3xl font-light transition-colors hover:bg-primary hover:text-primary-foreground disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Next pick"
      >
        ›
      </button>

      {/* ›› forward 10 — visible on sm+ */}
      <button
        onClick={() => onJump(Math.min(total + 1, currentPick + 10))}
        disabled={pastEnd || disabled}
        className="hidden sm:flex h-12 w-12 items-center justify-center rounded-full border-2 border-primary/40 text-primary/70 text-lg font-medium transition-colors hover:border-primary hover:bg-primary/10 disabled:opacity-30 disabled:cursor-not-allowed"
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
    <form onSubmit={handleSubmit} className="flex items-center justify-center gap-3">
      <label className="text-sm text-muted-foreground whitespace-nowrap">Go to pick</label>
      <input
        type="number"
        min={1}
        max={total}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm text-center focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none"
        placeholder="—"
      />
      <button
        type="submit"
        disabled={disabled || !value}
        className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${
          value && !disabled
            ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90"
            : "border-input bg-background text-muted-foreground opacity-40"
        }`}
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
      <div className="mb-1 flex justify-between text-sm text-muted-foreground">
        <span>{pct}%<span className="hidden sm:inline"> complete</span></span>
        <span>{Math.max(0, total - current + 1)} picks<span className="hidden sm:inline"> remaining</span></span>
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
  projectId,
  photos,
  onUploaded,
  onDeleted,
  readOnly = false,
}: {
  projectId: string;
  photos: ProjectPhoto[];
  onUploaded: (p: ProjectPhoto) => void;
  onDeleted: (id: string) => void;
  readOnly?: boolean;
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
        if (photos.length >= 10) { setError("Maximum 10 photos reached."); break; }
        const photo = await uploadProjectPhoto(projectId, file);
        onUploaded(photo);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (photoId: string) => {
    await deleteProjectPhoto(projectId, photoId);
    onDeleted(photoId);
    setConfirmDeleteId(null);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium">Photos <span className="text-muted-foreground font-normal">({photos.length}/10)</span></p>
        {!readOnly && photos.length < 10 && (
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
        readOnly ? (
          <p className="text-sm text-muted-foreground/60 italic">No photos.</p>
        ) : (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="w-full rounded-lg border border-dashed p-8 text-sm text-muted-foreground hover:border-ring hover:text-foreground transition-colors disabled:opacity-50"
          >
            Add photos to document your work
          </button>
        )
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
          {photos.map((p) => (
            <div key={p.id} className="group relative aspect-square">
              <AuthedImage
                src={projectPhotoUrl(projectId, p.id)}
                alt={p.filename}
                className="w-full h-full object-cover rounded-md border cursor-pointer"
                onClick={() => setLightbox(p.id)}
              />
              {!readOnly && (
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(p.id); }}
                  className="absolute top-1 right-1 hidden group-hover:flex h-5 w-5 items-center justify-center rounded-full bg-black/60 text-white text-xs hover:bg-black/80"
                  aria-label="Delete photo"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          {!readOnly && photos.length < 10 && (
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
            src={projectPhotoUrl(projectId, lightbox)}
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
  project,
  siblings,
  onPhotosChange,
}: {
  project: import("@/api/projects").ProjectDetail;
  siblings: ProjectSummary[];
  onPhotosChange: (photos: ProjectPhoto[]) => void;
}) {
  const { user } = useAuthContext();
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const [photos, setPhotos] = useState<ProjectPhoto[]>(project.photos);

  const pct = project.total_picks > 0
    ? Math.round(((project.current_pick - 1) / project.total_picks) * 100)
    : 100;
  const completedDate = project.completed_at
    ? new Date(project.completed_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })
    : null;

  const handleUploaded = (p: ProjectPhoto) => {
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
          <dd>{project.total_picks} picks ({pct}%)</dd>
          {project.num_items > 1 && (
            <><dt className="text-muted-foreground">Items</dt><dd>{project.num_items}</dd></>
          )}
          {project.finished_length_per_item && (
            <><dt className="text-muted-foreground">Length / item</dt>
            <dd>{displayLength(project.finished_length_per_item, project.length_unit, displayUnit)}</dd></>
          )}
          {project.warp_waste_allowance && (
            <><dt className="text-muted-foreground">Warp waste</dt>
            <dd>{displayLength(project.warp_waste_allowance, project.length_unit, displayUnit)}</dd></>
          )}
          <dt className="text-muted-foreground">Type</dt>
          <dd>{PROJECT_TYPE_LABELS[project.project_type]}</dd>
        </dl>
      </div>

      {/* Design preview */}
      <div>
        <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-2">Design Preview</h2>
        <div className="overflow-auto rounded-lg border bg-card p-2">
          <AuthedImage
            src={
              project.has_drawdown_preview
                ? projectDrawdownPreviewUrl(project.id)
                : drawdownPreviewUrl(project.id, project.color_replacements ?? undefined)
            }
            alt={`Design for ${project.draft_name}`}
            className="w-full block"
            style={{ imageRendering: "pixelated" }}
          />
        </div>
      </div>

      {/* Links */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Link
          to={`/drafts/${project.draft_id}`}
          className="rounded-lg border p-4 hover:border-ring transition-colors block"
        >
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Draft</p>
          <p className="font-medium text-sm">{project.draft_name}</p>
        </Link>
        {project.loom_id && project.loom_name && (
          <Link
            to={`/looms/${project.loom_id}`}
            className="rounded-lg border p-4 hover:border-ring transition-colors block"
          >
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Loom</p>
            <p className="font-medium text-sm">{project.loom_name}</p>
          </Link>
        )}
      </div>

      {/* Sibling projects */}
      {siblings.length > 0 && (
        <div>
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-2">Other projects on this draft</h2>
          <div className="space-y-1">
            {siblings.map((s) => {
              const isPlanning = s.status === "active" && !s.loom_id;
              const label = isPlanning ? "Plan" : PROJECT_STATUS_LABELS[s.status];
              const badgeCls = isPlanning
                ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                : s.status === "active"
                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                  : "bg-muted text-muted-foreground";
              return (
                <Link
                  key={s.id}
                  to={`/projects/${s.id}`}
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
        projectId={project.id}
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

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthContext();
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const [stepping, setStepping] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [colorMode, setColorMode] = useState<ColorMode>(
    () => (localStorage.getItem("proj-view:colorMode") as ColorMode) ?? "strip"
  );
  const [showWeftColor, setShowWeftColor] = useState(
    () => localStorage.getItem("proj-view:showWeftColor") !== "false"
  );
  const [showDrawdown, setShowDrawdown] = useState(
    () => localStorage.getItem("proj-view:showDrawdown") !== "false"
  );
  const [showPickDisplay] = useState(
    () => localStorage.getItem("proj-view:showPickDisplay") !== "false"
  );
  const [showProgress, setShowProgress] = useState(
    () => localStorage.getItem("proj-view:showProgress") !== "false"
  );
  const [hideTrailingUnused, setHideTrailingUnused] = useState(
    () => localStorage.getItem("proj-view:hideTrailingUnused") === "true"
  );
  const [panelOpen, setPanelOpen] = useState(
    () => localStorage.getItem("proj-view:panelOpen") === "true"
  );
  const [showDesignPreview, setShowDesignPreview] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesInput, setNotesInput] = useState("");
  const [showAssignLoom, setShowAssignLoom] = useState(false);
  const [confirmComplete, setConfirmComplete] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmClone, setConfirmClone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [cloneConflict, setCloneConflict] = useState<ProjectSummary | null>(null);
  const [restartConflict, setRestartConflict] = useState<ProjectSummary | null>(null);
  const [localPick, setLocalPick] = useState(1);

  const { isPresent, isSupported: presentModeSupported, toggle: togglePresentMode } = usePresentMode();

  const { data: project, isLoading, error } = useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id!),
    enabled: !!id,
  });

  const { data: picksData } = useQuery({
    queryKey: ["project-picks", id],
    queryFn: () => getProjectPicks(id!),
    enabled: !!id,
    staleTime: Infinity,
  });

  const isPlanning = project?.status === "active" && !project?.loom_id;
  const isCreated = project?.status === "created";
  const isCompleted = project?.status === "completed";

  // Auto-transition "created" → "active" when the tracker is opened
  const startMutation = useMutation({
    mutationFn: () => startProject(id!),
    onSuccess: (updated) => {
      queryClient.setQueryData(["project", id], (old: typeof project) =>
        old ? { ...updated, photos: old.photos } : updated
      );
    },
  });
  useEffect(() => {
    if (isCreated && id) startMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCreated, id]);

  const { data: allProjects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
    enabled: isPlanning || showAssignLoom,
  });

  const { data: siblingProjects = [] } = useQuery({
    queryKey: ["projects", { draftId: project?.draft_id }],
    queryFn: () => listProjects({ draftId: project!.draft_id }),
    enabled: isCompleted && !!project?.draft_id,
  });

  const { data: metrics } = useQuery<ProjectMetrics>({
    queryKey: ["project-metrics", id],
    queryFn: () => getProjectMetrics(id!),
    enabled: !!id && !!project && !isPlanning,
    refetchInterval: project?.status === "active" && !!project?.loom_id ? 30_000 : false,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["project", id] });

  const handleJump = useCallback(async (pick: number) => {
    if (!id || stepping) return;
    setStepping(true);
    try {
      const updated = await jumpProject(id, pick);
      queryClient.setQueryData<typeof project>(["project", id], (old) =>
        old ? { ...updated, photos: old.photos } : updated
      );
    } finally {
      setStepping(false);
    }
  }, [id, stepping, queryClient]);

  // Counts in-flight step requests. Used to suppress intermediate server responses
  // during rapid tapping — only the last response in a burst settles the cache.
  const pendingStepsRef = useRef(0);

  const handleStep = useCallback(async (direction: "advance" | "reverse") => {
    if (!id) return;
    // Read latest cached value so rapid taps each see the up-to-date pick
    const cached = queryClient.getQueryData<NonNullable<typeof project>>(["project", id]);
    if (!cached) return;
    if (direction === "advance" && cached.current_pick > cached.total_picks) return;
    if (direction === "reverse" && cached.current_pick <= 1) return;
    // Block advance when at item end — user must explicitly advance the item

    const newPick = direction === "advance" ? cached.current_pick + 1 : cached.current_pick - 1;

    // Instant optimistic update — UI responds before the server replies
    queryClient.setQueryData<typeof project>(["project", id], (old) =>
      old ? { ...old, current_pick: newPick } : old
    );

    pendingStepsRef.current += 1;
    try {
      const result = await stepProject(id, direction);
      pendingStepsRef.current -= 1;
      // Only settle once all in-flight steps have resolved. Earlier responses
      // are stale relative to the optimistic state (server serializes via FOR UPDATE,
      // but responses can arrive out of order over the network).
      if (pendingStepsRef.current === 0) {
        queryClient.setQueryData<typeof project>(["project", id], (old) => {
          if (!old) return old;
          // Never revert below the current optimistic pick — guards against the rare
          // case where a lower-pick response arrives last due to network reordering.
          const safePick = Math.max(old.current_pick, result.current_pick);
          return { ...old, current_pick: safePick, total_picks: result.total_picks, current_item: result.current_item };
        });
      }
    } catch {
      pendingStepsRef.current -= 1;
      // On error, invalidate to let the server state win
      queryClient.invalidateQueries({ queryKey: ["project", id] });
    }
  }, [id, queryClient]);

  const handleLocalStep = useCallback((direction: "advance" | "reverse") => {
    setLocalPick((prev) => {
      const total = project?.total_picks ?? 1;
      if (direction === "advance") return Math.min(prev + 1, total + 1);
      return Math.max(1, prev - 1);
    });
  }, [project?.total_picks]);

  const handleLocalJump = useCallback((pick: number) => {
    const total = project?.total_picks ?? 1;
    setLocalPick(Math.max(1, Math.min(pick, total + 1)));
  }, [project?.total_picks]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat) return;
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
    try { await completeProject(id); invalidate(); setConfirmComplete(false); }
    finally { setActionLoading(false); }
  };

  const handleAbandon = async () => {
    if (!id) return;
    setActionLoading(true);
    try { await abandonProject(id); invalidate(); setConfirmAbandon(false); }
    finally { setActionLoading(false); }
  };

  const handleAdvanceItem = useCallback(async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      const result = await advanceItem(id);
      queryClient.setQueryData<typeof project>(["project", id], (old) =>
        old ? { ...old, current_pick: result.current_pick, current_item: result.current_item } : old
      );
    } finally { setActionLoading(false); }
  }, [id, queryClient]);

  const handleJumpItem = useCallback(async (item: number) => {
    if (!id) return;
    setActionLoading(true);
    try {
      const updated = await jumpItem(id, item);
      queryClient.setQueryData<typeof project>(["project", id], (old) =>
        old ? { ...updated, photos: old.photos } : updated
      );
    } finally { setActionLoading(false); }
  }, [id, queryClient]);

  const handleRestart = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await restartProject(id);
      invalidate();
      setConfirmRestart(false);
      setRestartConflict(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && project?.loom_id) {
        const allActive = await listProjects().catch(() => []);
        setRestartConflict(allActive.find((a) => a.loom_id === project.loom_id && a.status === "active") ?? null);
        setConfirmRestart(false);
      }
    } finally { setActionLoading(false); }
  };

  const handleResolveAndRestart = async (resolve: "complete" | "abandon") => {
    if (!restartConflict || !id) return;
    setActionLoading(true);
    try {
      if (resolve === "complete") await completeProject(restartConflict.id);
      else await abandonProject(restartConflict.id);
      await restartProject(id);
      invalidate();
      setRestartConflict(null);
    } finally { setActionLoading(false); }
  };

  const handleClone = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      const cloned = await cloneProject(id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setConfirmClone(false);
      navigate(`/projects/${cloned.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && project?.loom_id) {
        const allActive = await listProjects().catch(() => []);
        setCloneConflict(allActive.find((a) => a.loom_id === project.loom_id && a.status === "active") ?? null);
        setConfirmClone(false);
      }
    } finally { setActionLoading(false); }
  };

  const handleResolveAndClone = async (resolve: "complete" | "abandon") => {
    if (!cloneConflict || !id) return;
    setActionLoading(true);
    try {
      if (resolve === "complete") await completeProject(cloneConflict.id);
      else await abandonProject(cloneConflict.id);
      const cloned = await cloneProject(id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setCloneConflict(null);
      navigate(`/projects/${cloned.id}`);
    } finally { setActionLoading(false); }
  };

  const handleDelete = async () => {
    if (!id) return;
    setActionLoading(true);
    try {
      await deleteProject(id);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects", { replace: true });
    } finally { setActionLoading(false); }
  };

  if (isLoading) return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-muted-foreground">Loading…</p>
    </div>
  );
  if (error || !project) return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-sm text-destructive">Project not found.</p>
    </div>
  );

  const displayPick = isPlanning ? localPick : project.current_pick;
  const currentPickIndex = displayPick - 1;

  const loomCount = project.project_type === "lift"
    ? (project.loom_num_shafts ?? null)
    : (project.loom_num_treadles ?? null);
  const declaredCount = project.project_type === "lift"
    ? (project.draft_num_shafts ?? 0)
    : (project.draft_num_treadles ?? 0);

  const maxFromPicks = picksData ? Math.max(0, ...picksData.picks.flatMap((p) => p.active)) : 0;
  // When a loom is assigned, use its treadle/shaft count; otherwise fall back to draft declared count.
  const maxActive = (loomCount !== null && loomCount > 0)
    ? loomCount
    : (declaredCount > 0 ? declaredCount : maxFromPicks);

  // Highest treadle/shaft index actually used in any pick across the full sequence.
  const maxUsed = picksData ? Math.max(0, ...picksData.picks.flatMap((p) => p.active)) : 0;
  // Count of trailing unused boxes (never used in any pick, counting from the top).
  const trailingUnused = maxActive > maxUsed ? maxActive - maxUsed : 0;
  // Effective box count shown: when hiding trailing, shrink to maxUsed.
  const displayCount = hideTrailingUnused && trailingUnused > 0 ? maxUsed : maxActive;

  const isMultiItem = project.num_items > 1;
  const isOnLastItem = project.current_item >= project.num_items;
  const isAtItemEnd = displayPick > project.total_picks && !isOnLastItem;
  const isFinished = displayPick > project.total_picks && isOnLastItem;
  const isActiveTracking = (project.status === "active" || project.status === "created") && !isPlanning;
  const isAbandoned = project.status === "abandoned";

  const isReadOnly = !!user?.is_superuser && project.owner_id !== user.id;

  // Badge for planning vs active
  const badgeClasses = isPlanning
    ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
    : project.status === "active"
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : "bg-muted text-muted-foreground";
  const badgeLabel = isPlanning ? "Plan" : PROJECT_STATUS_LABELS[project.status];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {isReadOnly && <SuperuserInspectionBanner />}
      {/* Page header */}
      <div className="shrink-0 border-b border-border bg-card px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3 min-w-0">
          {/* Breadcrumb — hidden on mobile/tablet, shown on desktop only */}
          <div className="hidden lg:flex items-center gap-1.5 text-sm shrink-0">
            {project.loom_id && (
              <>
                <Link to="/looms" className="text-muted-foreground hover:text-foreground">Equipment</Link>
                <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
              </>
            )}
            <Link to="/drafts" className="text-muted-foreground hover:text-foreground">Drafts</Link>
            <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            <Link to="/projects" className="text-muted-foreground hover:text-foreground">Projects</Link>
            <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            <Link to={`/projects/${project.id}`} className="text-muted-foreground hover:text-foreground truncate max-w-[12rem]">{project.name}</Link>
            <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          </div>
          {isReadOnly ? (
            <span className="font-semibold truncate">{project.name}</span>
          ) : editingName ? (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const trimmed = nameInput.trim();
                if (!trimmed) { setEditingName(false); return; }
                const updated = await renameProject(id!, trimmed);
                queryClient.setQueryData<typeof project>(["project", id], (old) =>
                  old ? { ...updated, photos: old.photos } : updated
                );
                queryClient.invalidateQueries({ queryKey: ["projects"] });
                setEditingName(false);
              }}
              className="flex items-center gap-2 min-w-0"
            >
              <input
                autoFocus
                className="rounded border border-input bg-background px-2 py-0.5 text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-ring"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") setEditingName(false); }}
                onBlur={async () => {
                  const trimmed = nameInput.trim();
                  if (trimmed && trimmed !== project.name) {
                    const updated = await renameProject(id!, trimmed);
                    queryClient.setQueryData<typeof project>(["project", id], (old) =>
                      old ? { ...updated, photos: old.photos } : updated
                    );
                    queryClient.invalidateQueries({ queryKey: ["projects"] });
                  }
                  setEditingName(false);
                }}
              />
            </form>
          ) : (
            <button
              onClick={() => { setNameInput(project.name); setEditingName(true); }}
              className="font-semibold hover:underline decoration-dashed underline-offset-2 cursor-text truncate"
              title="Click to rename"
            >
              {project.name}
            </button>
          )}
          <span className="text-sm text-muted-foreground truncate hidden sm:block">{project.draft_name}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShowDesignPreview(true)}
            className="rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
            title="View WIF design preview"
          >
            View design
          </button>
          {!isReadOnly && (
            <button
              onClick={() => setSettingsOpen(true)}
              className="rounded-md border border-border bg-background px-2.5 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="View settings"
              aria-label="Open view settings"
            >
              <AppIcons.settings className="h-4 w-4" />
            </button>
          )}
          <span className={`rounded px-2 py-0.5 text-xs font-medium ${badgeClasses}`}>
            {badgeLabel}
          </span>
          {presentModeSupported && (
            <button
              onClick={togglePresentMode}
              className="ml-3 rounded-md border border-border bg-background px-2.5 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title={isPresent ? "Exit present mode" : "Present mode — fullscreen + keep screen on"}
              aria-label={isPresent ? "Exit present mode" : "Enter present mode"}
            >
              {isPresent
                ? <AppIcons.exitPresentMode className="h-4 w-4" />
                : <AppIcons.presentMode className="h-4 w-4" />}
            </button>
          )}
        </div>
      </div>

      {/* Main content — fills remaining height; overflow-hidden prevents any page scroll */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {/* Completed summary */}
        {isCompleted && (
          <CompletedSummary
            project={project}
            siblings={siblingProjects.filter((s) => s.id !== id)}
            onPhotosChange={(photos) =>
              queryClient.setQueryData(["project", id], { ...project, photos })
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
            <div className="rounded-md border border-copper-subtle bg-copper-subtle px-4 py-3 text-sm">
              <p className="font-medium text-copper-on-subtle">This project was not completed</p>
              <p className="mt-0.5 text-xs text-copper-on-subtle">
                Abandoned at pick {project.current_pick} of {project.total_picks}
                {" "}({Math.round((project.current_pick - 1) / project.total_picks * 100)}% woven)
                {project.abandoned_at && ` · ${new Date(project.abandoned_at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })}`}
              </p>
            </div>
          </div>
        )}

        {/* Progress bar + item indicator */}
        {showProgress && !isPlanning && !isCompleted && (
          <div className="w-full px-8 pt-6">
            {isMultiItem && (
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1">
                  {Array.from({ length: project.num_items }, (_, i) => (
                    <button
                      key={i}
                      onClick={() => isActiveTracking && handleJumpItem(i + 1)}
                      disabled={!isActiveTracking || actionLoading}
                      title={`Jump to item ${i + 1}`}
                      className={`h-2.5 rounded-full transition-all ${
                        i + 1 === project.current_item
                          ? "w-6 bg-primary"
                          : i + 1 < project.current_item
                          ? "w-2.5 bg-primary/40"
                          : "w-2.5 bg-muted-foreground/30"
                      } ${isActiveTracking && !actionLoading ? "cursor-pointer hover:opacity-80" : "cursor-default"}`}
                    />
                  ))}
                </div>
                <span className="text-xs text-muted-foreground font-medium">
                  Item {project.current_item} of {project.num_items}
                </span>
              </div>
            )}
            <ProgressBar current={project.current_pick} total={project.total_picks} />
          </div>
        )}

        {/* Pick instruction — full width so treadle/lift boxes use available space */}
        {!isCompleted && showPickDisplay && <div className="w-full px-8 pt-4">
          {isAtItemEnd ? (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-lg font-medium">Item {project.current_item} complete!</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {project.total_picks} picks done. Ready to start item {project.current_item + 1} of {project.num_items}.
              </p>
              {isActiveTracking && (
                <div className="mt-6">
                  <Button variant="success" onClick={handleAdvanceItem} disabled={actionLoading}>
                    {actionLoading ? "…" : `Start item ${project.current_item + 1}`}
                  </Button>
                </div>
              )}
            </div>
          ) : isFinished ? (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-lg font-medium">
                {isMultiItem ? `All ${project.num_items} items complete!` : `All ${project.total_picks} picks complete!`}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Mark the project as completed when you're done.
              </p>
              {isActiveTracking && (
                <div className="mt-6">
                  {!confirmComplete ? (
                    <Button variant="success" onClick={() => setConfirmComplete(true)}>Mark complete</Button>
                  ) : (
                    <div className="flex items-center justify-center gap-2">
                      <span className="text-sm">Mark this project as completed?</span>
                      <Button size="sm" variant="success" onClick={handleComplete} disabled={actionLoading}>Confirm</Button>
                      <Button size="sm" variant="outline" onClick={() => setConfirmComplete(false)} disabled={actionLoading}>Cancel</Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : picksData ? (
            <PickDisplay
              pick={picksData.picks[currentPickIndex]}
              totalCount={displayCount}
              projectType={project.project_type}
              colorMode={colorMode}
              showWeftColor={showWeftColor}
            />
          ) : (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-sm text-muted-foreground">Pick data loading…</p>
            </div>
          )}
        </div>}

        {/* Spacer — always consumes remaining height so step controls stay pinned to bottom */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {/* Pattern view — wider on large screens to show more warp threads */}
          {showDrawdown && picksData && !isFinished && !isAtItemEnd && !isCompleted && !isAbandoned && (
            <div className="mx-auto w-full max-w-2xl lg:max-w-5xl xl:max-w-7xl px-8 pb-4 pt-4">
              <WeavingPatternView
                projectId={project.id}
                currentPickIndex={currentPickIndex}
                totalPicks={project.total_picks}
                picks={picksData.picks}
                maxActive={displayCount}
              />
            </div>
          )}

          {/* Abandoned design preview — full drawdown with unweaved portion desaturated */}
          {isAbandoned && (
            <div className="mx-auto w-full max-w-2xl lg:max-w-5xl xl:max-w-7xl px-8 pb-4 pt-4">
              <AbandonedDrawdownView
                draftId={project.draft_id}
                currentPick={project.current_pick}
                totalPicks={project.total_picks}
              />
            </div>
          )}
        </div>

        {/* Step controls — active tracking and planning */}
        <div className="w-full px-4 pb-6">
          {!isReadOnly && (isActiveTracking || isPlanning) && (
            <div className="flex flex-col gap-6 lg:grid lg:grid-cols-[1fr_auto_1fr] lg:items-center lg:gap-8 mb-4">
              {/* Left 1/3 on desktop, below step buttons on mobile */}
              <div className="order-2 lg:order-1 lg:flex lg:justify-center">
                <JumpToPick
                  total={project.total_picks}
                  onJump={isPlanning ? handleLocalJump : handleJump}
                  disabled={stepping}
                />
              </div>
              {/* Center 1/3 on desktop, top on mobile */}
              <div className="order-1 lg:order-2 flex justify-center">
                <StepControls
                  currentPick={displayPick}
                  total={project.total_picks}
                  onStep={isPlanning ? handleLocalStep : handleStep}
                  onJump={isPlanning ? handleLocalJump : handleJump}
                  stepping={stepping}
                />
              </div>
              {/* Right 1/3 reserved for future use */}
              <div className="hidden lg:block lg:order-3" />
            </div>
          )}

          {!isReadOnly && (isActiveTracking || isPlanning) && (
            <p className="text-center text-sm text-muted-foreground">
              ← → arrow keys or spacebar to navigate picks
            </p>
          )}
        </div>

      </div>

      {/* Details & settings panel — toggle bar always visible; sections scroll when open */}
      <div className="shrink-0 border-t bg-card">
        <button
          onClick={() => {
            const next = !panelOpen;
            setPanelOpen(next);
            localStorage.setItem("proj-view:panelOpen", String(next));
          }}
          className="flex w-full items-center justify-between px-6 py-2.5 text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
          aria-expanded={panelOpen}
        >
          Details &amp; settings
          <AppIcons.chevronDown
            className={`h-4 w-4 transition-transform duration-200 ${panelOpen ? "" : "-rotate-90"}`}
          />
        </button>
        {panelOpen && (
          <div className="overflow-y-auto max-h-[55dvh] border-t border-border/50">
            <div className="mx-auto max-w-2xl px-8 pb-10 space-y-0">
          {(!isCompleted || isReadOnly) && (
            <CollapsibleSection title={`Photos (${project.photos.length}/10)`} defaultOpen={isAbandoned}>
              <PhotoGrid
                projectId={project.id}
                photos={project.photos}
                readOnly={isReadOnly}
                onUploaded={(p) =>
                  queryClient.setQueryData<typeof project>(["project", id], (old) =>
                    old ? { ...old, photos: [...old.photos, p] } : old
                  )
                }
                onDeleted={(photoId) =>
                  queryClient.setQueryData<typeof project>(["project", id], (old) =>
                    old ? { ...old, photos: old.photos.filter((ph) => ph.id !== photoId) } : old
                  )
                }
              />
            </CollapsibleSection>
          )}

          {metrics && (
            <CollapsibleSection title="Session metrics">
              <SessionMetricsPanel metrics={metrics} />
            </CollapsibleSection>
          )}

          <CollapsibleSection title="Notes" defaultOpen={!!project.notes}>
            {isReadOnly ? (
              project.notes ? (
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{project.notes}</p>
              ) : (
                <p className="text-sm text-muted-foreground/60 italic">No notes.</p>
              )
            ) : editingNotes ? (
              <textarea
                autoFocus
                className="w-full rounded border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring resize-none"
                rows={4}
                value={notesInput}
                onChange={(e) => setNotesInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") setEditingNotes(false); }}
                onBlur={async () => {
                  const trimmed = notesInput.trim();
                  const current = project.notes ?? "";
                  if (trimmed !== current) {
                    const updated = await updateProjectNotes(id!, trimmed || null);
                    queryClient.setQueryData<typeof project>(["project", id], (old) =>
                      old ? { ...updated, photos: old.photos } : updated
                    );
                  }
                  setEditingNotes(false);
                }}
              />
            ) : (
              <button
                onClick={() => { setNotesInput(project.notes ?? ""); setEditingNotes(true); }}
                className="w-full text-left text-sm"
                title="Click to edit notes"
              >
                {project.notes ? (
                  <p className="whitespace-pre-wrap text-muted-foreground">{project.notes}</p>
                ) : (
                  <p className="text-muted-foreground/60 italic">Add notes...</p>
                )}
              </button>
            )}
          </CollapsibleSection>

          <CollapsibleSection title="Details">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Type</dt>
              <dd>{PROJECT_TYPE_LABELS[project.project_type]}</dd>
              {project.loom_name && (
                <><dt className="text-muted-foreground">Loom</dt><dd>{project.loom_name}</dd></>
              )}
              {project.draft_metadata_overrides?.num_treadles && (
                <><dt className="text-muted-foreground">Treadle count</dt>
                <dd className="flex items-center gap-1.5">
                  {project.draft_num_treadles}
                  <span className="text-xs text-muted-foreground">(overridden from {project.draft_metadata_overrides.num_treadles.original})</span>
                </dd></>
              )}
              {project.draft_metadata_overrides?.num_shafts && (
                <><dt className="text-muted-foreground">Shaft count</dt>
                <dd className="flex items-center gap-1.5">
                  {project.draft_num_shafts}
                  <span className="text-xs text-muted-foreground">(overridden from {project.draft_metadata_overrides.num_shafts.original})</span>
                </dd></>
              )}
              {project.num_items > 1 && (
                <><dt className="text-muted-foreground">Items</dt><dd>{project.num_items}</dd></>
              )}
              {project.finished_length_per_item && (
                <><dt className="text-muted-foreground">Length / item</dt>
                <dd>{displayLength(project.finished_length_per_item, project.length_unit, displayUnit)}</dd></>
              )}
              {project.warp_waste_allowance && (
                <><dt className="text-muted-foreground">Warp waste</dt>
                <dd>{displayLength(project.warp_waste_allowance, project.length_unit, displayUnit)}</dd></>
              )}
              {project.completed_at && (
                <><dt className="text-muted-foreground">Completed</dt>
                <dd>{new Date(project.completed_at).toLocaleDateString()}</dd></>
              )}
            </dl>
          </CollapsibleSection>

          {/* Active tracking: complete / abandon */}
          {!isReadOnly && isActiveTracking && (
            <CollapsibleSection title="Actions">
              <div className="flex flex-wrap gap-2">
                {!confirmComplete && !confirmAbandon && (
                  <>
                    {isFinished && (
                      <Button variant="success" size="sm" onClick={() => setConfirmComplete(true)}>
                        Mark complete
                      </Button>
                    )}
                    <Button variant="outline" size="sm" onClick={() => setConfirmAbandon(true)}>
                      Abandon
                    </Button>
                  </>
                )}
                {confirmComplete && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Mark this project as completed?</span>
                    <Button size="sm" variant="success" onClick={handleComplete} disabled={actionLoading}>Confirm</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmComplete(false)} disabled={actionLoading}>Cancel</Button>
                  </div>
                )}
                {confirmAbandon && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-destructive">Abandon this project?</span>
                    <Button size="sm" onClick={handleAbandon} disabled={actionLoading}>Confirm</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmAbandon(false)} disabled={actionLoading}>Cancel</Button>
                  </div>
                )}
              </div>
            </CollapsibleSection>
          )}

          {!isReadOnly && project.status === "abandoned" && (
            <CollapsibleSection title="Actions">
              <div className="space-y-3">
                {!confirmRestart && !restartConflict && (
                  <Button variant="outline" size="sm" onClick={() => setConfirmRestart(true)}>
                    Restart project
                  </Button>
                )}
                {confirmRestart && (
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Resume from pick {project.current_pick}?</span>
                    <Button size="sm" onClick={handleRestart} disabled={actionLoading}>Confirm</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmRestart(false)} disabled={actionLoading}>Cancel</Button>
                  </div>
                )}
                {restartConflict && (
                  <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-3 text-sm space-y-2">
                    <p className="font-medium text-copper-on-subtle">
                      This loom has an active project: <span className="font-semibold">{restartConflict.name}</span>
                    </p>
                    <p className="text-copper-on-subtle text-xs">Resolve it to restart this one.</p>
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

          {!isReadOnly && <CollapsibleSection title="Clone project">
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Create a new project with the same configuration, starting at pick 1.</p>
              {!confirmClone && !cloneConflict && (
                <Button variant="outline" size="sm" onClick={() => setConfirmClone(true)}>
                  Clone project
                </Button>
              )}
              {confirmClone && (
                <div className="flex items-center gap-2">
                  <span className="text-sm">Start a new project with the same settings?</span>
                  <Button size="sm" onClick={handleClone} disabled={actionLoading}>{actionLoading ? "Cloning…" : "Confirm"}</Button>
                  <Button size="sm" variant="outline" onClick={() => setConfirmClone(false)} disabled={actionLoading}>Cancel</Button>
                </div>
              )}
              {cloneConflict && (
                <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-3 text-sm space-y-2">
                  <p className="font-medium text-copper-on-subtle">
                    This loom has an active project: <span className="font-semibold">{cloneConflict.name}</span>
                  </p>
                  <p className="text-copper-on-subtle text-xs">Resolve it to start the clone.</p>
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
          </CollapsibleSection>}

          {!isReadOnly && <CollapsibleSection title="Danger zone">
            {!confirmDelete ? (
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)}>
                Delete project
              </Button>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm text-destructive">
                  Delete this project and all step history? This cannot be undone.
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
          </CollapsibleSection>}
            </div>
          </div>
        )}
      </div>

      {showDesignPreview && (
        <DesignPreviewModal
          projectId={project.id}
          hasDrawdownPreview={project.has_drawdown_preview}
          colorReplacements={project.color_replacements}
          onClose={() => setShowDesignPreview(false)}
        />
      )}

      {showAssignLoom && (
        <AssignLoomModal
          projectId={project.id}
          activeProjects={allProjects.filter((a) => a.status === "active")}
          projectType={project.project_type}
          draftNumTreadles={project.draft_num_treadles}
          draftNumShafts={project.draft_num_shafts}
          draftEffectiveNumTreadles={project.draft_effective_num_treadles}
          draftEffectiveNumShafts={project.draft_effective_num_shafts}
          onSuccess={() => {
            setShowAssignLoom(false);
            invalidate();
            queryClient.invalidateQueries({ queryKey: ["projects"] });
          }}
          onClose={() => setShowAssignLoom(false)}
        />
      )}

      {/* View settings drawer */}
      {settingsOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => setSettingsOpen(false)}
          />
          <div className="fixed inset-y-0 right-0 z-50 flex w-72 flex-col border-l border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="text-sm font-semibold">View settings</span>
              <button
                onClick={() => setSettingsOpen(false)}
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Close settings"
              >
                <AppIcons.close className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
              {/* Show/hide toggles */}
              <div className="space-y-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Show / hide</p>
                {([
                  { label: "Progress bar", value: showProgress, key: "proj-view:showProgress", setter: setShowProgress },
                  { label: "Drawdown pattern", value: showDrawdown, key: "proj-view:showDrawdown", setter: setShowDrawdown },
                  { label: "Weft color", value: showWeftColor, key: "proj-view:showWeftColor", setter: setShowWeftColor },
                ] as { label: string; value: boolean; key: string; setter: (v: boolean) => void }[]).map(({ label, value, key, setter }) => (
                  <div key={label} className="flex items-center justify-between">
                    <span className="text-sm">{label}</span>
                    <button
                      role="switch"
                      aria-checked={value}
                      onClick={() => { setter(!value); localStorage.setItem(key, String(!value)); }}
                      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring ${value ? "bg-primary" : "bg-input"}`}
                    >
                      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${value ? "translate-x-4" : "translate-x-1"}`} />
                    </button>
                  </div>
                ))}
              </div>

              {/* Trailing unused toggle — only shown when there are trailing boxes */}
              {trailingUnused > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Treadle display</p>
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-sm">Hide trailing unused</span>
                      <p className="text-xs text-muted-foreground">{trailingUnused} never-used trailing {trailingUnused === 1 ? "box" : "boxes"}</p>
                    </div>
                    <button
                      role="switch"
                      aria-checked={hideTrailingUnused}
                      onClick={() => {
                        const next = !hideTrailingUnused;
                        setHideTrailingUnused(next);
                        localStorage.setItem("proj-view:hideTrailingUnused", String(next));
                      }}
                      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring ${hideTrailingUnused ? "bg-primary" : "bg-input"}`}
                    >
                      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${hideTrailingUnused ? "translate-x-4" : "translate-x-1"}`} />
                    </button>
                  </div>
                </div>
              )}

              {/* Color mode selector — always shown; strip/filled have no visible effect without weft colors */}
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Color mode</p>
                <div className="inline-flex rounded-md border border-input overflow-hidden text-sm w-full">
                  {(["theme", "strip", "filled"] as ColorMode[]).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => { setColorMode(mode); localStorage.setItem("proj-view:colorMode", mode); }}
                      className={`flex-1 px-2.5 py-1.5 capitalize transition-colors ${
                        colorMode === mode
                          ? "bg-primary text-primary-foreground"
                          : "bg-background text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
                {!picksData?.has_weft_colors && (
                  <p className="text-xs text-muted-foreground">This design has no weft colors defined.</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
