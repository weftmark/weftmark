import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, displayLength, formatApproxLength, convertLength, type LengthUnit } from "@/lib/units";
import {
  getProject, setProjectColorReplacements, deleteProject, updateProjectNotes,
  updateProjectWarpSetup, drawdownSvgUrl, drawdownPreviewUrl, projectDrawdownSvgUrl,
  updateProjectShare, revokeProjectShare,
  getWarpingPlan,
  PROJECT_TYPE_LABELS, PROJECT_STATUS_LABELS,
  type ProjectDetail,
} from "@/api/projects";
import { TieUpDiagram } from "@/components/TieUpDiagram";
import { previewUrl } from "@/api/drafts";
import { getAuthToken } from "@/api/client";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { Button, buttonVariants } from "@/components/ui/button";
import { AppIcons } from "@/lib/icons";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_BADGE: Record<string, string> = {
  created: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  completed: "bg-muted text-muted-foreground",
  abandoned: "bg-muted text-muted-foreground",
};

// ---------------------------------------------------------------------------
// Authed SVG fetch hook
// ---------------------------------------------------------------------------

type SvgAction = { type: "start" } | { type: "done"; svg: string } | { type: "error" };
type SvgState = { svg: string | null; loading: boolean };
function svgReducer(_: SvgState, action: SvgAction): SvgState {
  if (action.type === "start") return { svg: null, loading: true };
  if (action.type === "done") return { svg: action.svg, loading: false };
  return { svg: null, loading: false };
}

function useAuthedSvg(url: string | null): { svg: string | null; loading: boolean } {
  const [{ svg, loading }, dispatch] = useReducer(svgReducer, { svg: null, loading: false });

  useEffect(() => {
    if (!url) return;
    const fetchUrl = url;
    let cancelled = false;
    dispatch({ type: "start" });

    async function load() {
      const token = await getAuthToken();
      const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(fetchUrl, { headers, credentials: "include" });
      if (!res.ok || cancelled) { if (!cancelled) dispatch({ type: "error" }); return; }
      const text = await res.text();
      if (!cancelled) dispatch({ type: "done", svg: text });
    }
    load().catch(() => { if (!cancelled) dispatch({ type: "error" }); });
    return () => { cancelled = true; };
  }, [url]);

  return { svg, loading };
}

// ---------------------------------------------------------------------------
// Zoom percentage input — lets the user type a zoom value directly.
// ---------------------------------------------------------------------------

function ZoomInput({ zoom, onCommit }: { zoom: number; onCommit: (z: number) => void }) {
  const [editing, setEditing] = useState(false);
  const [raw, setRaw] = useState("");

  function startEdit(e: React.FocusEvent<HTMLInputElement>) {
    setRaw(String(Math.round(zoom * 100)));
    setEditing(true);
    e.currentTarget.select();
  }

  function commit(input: string) {
    setEditing(false);
    const n = parseInt(input, 10);
    if (!isNaN(n)) {
      onCommit(Math.max(0.05, Math.min(8, n / 100)));
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") { e.currentTarget.blur(); }
    else if (e.key === "Escape") { setEditing(false); e.currentTarget.blur(); }
  }

  return (
    <input
      type="text"
      inputMode="numeric"
      value={editing ? raw : `${Math.round(zoom * 100)}%`}
      onFocus={startEdit}
      onChange={(e) => setRaw(e.target.value.replace(/[^\d]/g, ""))}
      onBlur={(e) => commit(e.currentTarget.value)}
      onKeyDown={handleKeyDown}
      className="w-12 rounded border border-input bg-background px-1 py-0.5 text-center text-xs tabular-nums focus:outline-none focus:ring-1 focus:ring-ring"
      title="Click to set zoom level"
    />
  );
}

// ---------------------------------------------------------------------------
// Drawdown modal (click thumbnail to open)
// ---------------------------------------------------------------------------

function DrawdownModal({ svgUrl, title = "Design preview", onClose }: {
  svgUrl: string;
  title?: string;
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const zoomRef = useRef(1);
  const panRef = useRef({ x: 0, y: 0 });
  const innerRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const svgSizeRef = useRef<{ w: number; h: number } | null>(null);
  const dragRef = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const { svg, loading: isLoading } = useAuthedSvg(svgUrl);

  // Wheel events are captured on the backdrop with passive:false so we can
  // preventDefault — this blocks page scroll and touchpad back-navigation while
  // the modal is open. All values accessed via stable refs, so deps array is empty.
  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    if (!containerRef.current?.contains(e.target as Node)) return;
    const dx = e.deltaMode === 0 ? e.deltaX : e.deltaX * 40;
    const dy = e.deltaMode === 0 ? e.deltaY : e.deltaY * 40;
    if (e.ctrlKey || e.metaKey) {
      const rect = containerRef.current.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const factor = dy < 0 ? 1.1 : 1 / 1.1;
      const newZ = Math.max(0.05, Math.min(8, zoomRef.current * factor));
      const ratio = newZ / zoomRef.current;
      const newPan = {
        x: cx - (cx - panRef.current.x) * ratio,
        y: cy - (cy - panRef.current.y) * ratio,
      };
      panRef.current = newPan;
      zoomRef.current = newZ;
      setZoom(+(newZ.toFixed(2)));
      applyTransform(newZ, newPan.x, newPan.y);
      updateBorderStroke(newZ);
    } else {
      const newPan = { x: panRef.current.x - dx, y: panRef.current.y - dy };
      panRef.current = newPan;
      applyTransform(zoomRef.current, newPan.x, newPan.y);
    }
   
  }, []);

  useEffect(() => {
    const el = backdropRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "0") handleReset();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onClose]);

  function applyTransform(z: number, px: number, py: number) {
    if (!innerRef.current) return;
    innerRef.current.style.transform = `translate(${px}px, ${py}px) scale(${z})`;
  }

  // Keep the float border visually constant (~0.5px on screen) regardless of CSS zoom.
  // stroke-width is in SVG units; dividing by z compensates for the CSS scale.
  function updateBorderStroke(z: number) {
    const path = innerRef.current?.querySelector("svg path");
    if (path) path.setAttribute("stroke-width", String(+(0.5 / Math.max(1, z)).toFixed(4)));
  }

  function computeFitZoom(): number {
    if (!svgSizeRef.current || !containerRef.current) return 1;
    const cw = containerRef.current.clientWidth - 24;
    const ch = containerRef.current.clientHeight - 24;
    return Math.max(0.05, Math.min(1, cw / svgSizeRef.current.w, ch / svgSizeRef.current.h));
  }

  function centerPan(z: number): { x: number; y: number } {
    if (!svgSizeRef.current || !containerRef.current) return { x: 0, y: 0 };
    return {
      x: (containerRef.current.clientWidth - svgSizeRef.current.w * z) / 2,
      y: (containerRef.current.clientHeight - svgSizeRef.current.h * z) / 2,
    };
  }

  // Auto-fit on SVG load — runs before paint to avoid flash at wrong zoom
  useLayoutEffect(() => {
    if (!svg || !innerRef.current || !containerRef.current) return;
    const svgEl = innerRef.current.querySelector("svg");
    if (svgEl) {
      const w = svgEl.getAttribute("width");
      const h = svgEl.getAttribute("height");
      if (w && h) {
        svgSizeRef.current = { w: parseFloat(w), h: parseFloat(h) };
      } else {
        const vb = svgEl.getAttribute("viewBox");
        if (vb) {
          const parts = vb.trim().split(/\s+/);
          if (parts.length >= 4) svgSizeRef.current = { w: parseFloat(parts[2]), h: parseFloat(parts[3]) };
        }
      }
    }
    const z = computeFitZoom();
    const p = centerPan(z);
    panRef.current = p;
    zoomRef.current = z;
    setZoom(+(z.toFixed(2)));
    applyTransform(z, p.x, p.y);
    updateBorderStroke(z);
  }, [svg]);

  function handleZoomChange(newZ: number) {
    if (!containerRef.current) return;
    const cw = containerRef.current.clientWidth;
    const ch = containerRef.current.clientHeight;
    const ratio = newZ / zoomRef.current;
    const newPan = {
      x: cw / 2 + (panRef.current.x - cw / 2) * ratio,
      y: ch / 2 + (panRef.current.y - ch / 2) * ratio,
    };
    panRef.current = newPan;
    zoomRef.current = newZ;
    setZoom(newZ);
    applyTransform(newZ, newPan.x, newPan.y);
    updateBorderStroke(newZ);
  }

  function handleReset() {
    const z = computeFitZoom();
    const p = centerPan(z);
    panRef.current = p;
    zoomRef.current = z;
    setZoom(+(z.toFixed(2)));
    applyTransform(z, p.x, p.y);
    updateBorderStroke(z);
  }

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { px: e.clientX, py: e.clientY, ox: panRef.current.x, oy: panRef.current.y };
    e.currentTarget.style.cursor = "grabbing";
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragRef.current) return;
    const newPan = {
      x: dragRef.current.ox + (e.clientX - dragRef.current.px),
      y: dragRef.current.oy + (e.clientY - dragRef.current.py),
    };
    panRef.current = newPan;
    applyTransform(zoomRef.current, newPan.x, newPan.y);
  }

  function handlePointerUp(e: React.PointerEvent<HTMLDivElement>) {
    dragRef.current = null;
    e.currentTarget.style.cursor = "grab";
  }

  const btnCls = "flex items-center justify-center rounded border border-border bg-muted px-2 py-1 text-sm hover:bg-accent hover:text-accent-foreground transition-colors";

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="bg-card rounded-xl border border-border shadow-xl flex flex-col"
        style={{ width: "min(96vw, 1400px)", height: "min(92vh, 1200px)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border shrink-0">
          <span className="text-sm font-medium truncate flex-1">{title}</span>
          <button className={btnCls} onClick={() => handleZoomChange(Math.max(0.05, +(zoomRef.current - 0.25).toFixed(2)))} title="Zoom out">
            <AppIcons.zoomOut className="h-4 w-4" />
          </button>
          <ZoomInput zoom={zoom} onCommit={handleZoomChange} />
          <button className={btnCls} onClick={() => handleZoomChange(Math.min(8, +(zoomRef.current + 0.25).toFixed(2)))} title="Zoom in">
            <AppIcons.zoomIn className="h-4 w-4" />
          </button>
          <button className={btnCls} onClick={handleReset} title="Zoom to fit (0)">
            <AppIcons.zoomFit className="h-4 w-4" />
          </button>
          <button
            className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors ml-1"
            onClick={onClose}
            title="Close"
          >
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>

        {/* Pan/zoom content — transform-based, no scroll, GPU-accelerated */}
        <div
          ref={containerRef}
          className="flex-1 overflow-hidden select-none relative"
          style={{ cursor: "grab", touchAction: "none" }}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
        >
          {isLoading && (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              Loading drawdown…
            </div>
          )}
          {!isLoading && !svg && (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              Could not load drawdown.
            </div>
          )}
          <div
            ref={innerRef}
            style={{ transformOrigin: "0 0", display: "inline-block", willChange: "transform" }}
            dangerouslySetInnerHTML={svg ? { __html: svg } : undefined}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tie-up modal
// ---------------------------------------------------------------------------

function TieUpModal({ projectId, draftName, onClose }: {
  projectId: string;
  draftName: string;
  onClose: () => void;
}) {
  const { data: plan, isLoading } = useQuery({
    queryKey: ["warping-plan", projectId],
    queryFn: () => getWarpingPlan(projectId),
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card rounded-xl border border-border shadow-2xl flex flex-col max-w-lg w-full max-h-[80vh]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="font-semibold text-sm">Treadle Tie-Up — {draftName}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-5">
          {isLoading && (
            <div className="flex items-center justify-center h-24 text-sm text-muted-foreground">
              <AppIcons.spinner className="h-4 w-4 animate-spin mr-2" /> Loading…
            </div>
          )}
          {plan && !plan.has_tieup && (
            <p className="text-sm text-muted-foreground italic">
              Tie-up data not available — this WIF file does not contain a [TIEUP] section.
            </p>
          )}
          {plan?.has_tieup && plan.tieup && plan.tieup_num_shafts && plan.tieup_num_treadles && (
            <>
              <p className="text-xs text-muted-foreground mb-4">
                Columns = treadles · Rows = shafts · Filled = connected
              </p>
              <div className="overflow-x-auto">
                <TieUpDiagram
                  tieup={plan.tieup}
                  numShafts={plan.tieup_num_shafts}
                  numTreadles={plan.tieup_num_treadles}
                />
              </div>
            </>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-border">
          <Link
            to={`/projects/${projectId}/warping-plan`}
            className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
          >
            View Weave Plan
          </Link>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              window.open(`/projects/${projectId}/warping-plan`, "_blank");
            }}
          >
            <AppIcons.print className="h-4 w-4 mr-1.5" />
            Print / Save PDF
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Color palette section
// ---------------------------------------------------------------------------

function ColorPaletteSection({
  projectId,
  wifColors,
  warpStats,
  weftStats,
  colorReplacements,
  warpLengthCm,
  onSave,
  isSaving,
  locked,
}: {
  projectId: string;
  wifColors: { index: number; hex: string }[];
  warpStats: { hex: string; count: number; percentage: number }[] | null;
  weftStats: { hex: string; count: number; percentage: number }[] | null;
  colorReplacements: Record<string, string> | null;
  warpLengthCm: number | null;
  onSave: (replacements: Record<string, string>) => void;
  isSaving: boolean;
  locked?: boolean;
}) {
  const { user } = useAuthContext();
  const unit = measurementSystemToUnit(user?.measurement_system ?? "metric");

  const bothPresent = warpStats !== null && weftStats !== null;
  const visibleColors = bothPresent
    ? wifColors.filter(
        (c) =>
          weftStats!.some((s) => s.hex === c.hex) ||
          warpStats!.some((s) => s.hex === c.hex),
      )
    : wifColors;

  const [pending, setPending] = useState<Record<string, string>>(
    () => colorReplacements ?? {},
  );
  const [dirty, setDirty] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);

  function setReplacement(hex: string, replacement: string) {
    const next = { ...pending };
    if (replacement.toLowerCase() === hex.toLowerCase()) {
      delete next[hex];
    } else {
      next[hex] = replacement;
    }
    setPending(next);
    setDirty(true);
  }

  if (visibleColors.length === 0) return null;

  const weftTotal = weftStats ? weftStats.reduce((s, r) => s + r.count, 0) : 0;
  const hasReplacements = Object.keys(pending).length > 0;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Color Palette
          </h3>
          {locked && (
            <span className="text-xs text-muted-foreground">(locked — project active)</span>
          )}
        </div>
        <div className="flex gap-2">
          {hasReplacements && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPreviewOpen((v) => !v)}
            >
              Preview
            </Button>
          )}
          {!locked && dirty && (
            <Button
              size="sm"
              onClick={() => { onSave(pending); setDirty(false); }}
              disabled={isSaving}
            >
              {isSaving ? "Saving…" : "Save colors"}
            </Button>
          )}
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30 text-muted-foreground text-xs uppercase tracking-wide">
              <th className="px-3 py-2 text-left">Color</th>
              <th className="px-3 py-2 text-right">Warp ends</th>
              <th className="px-3 py-2 text-right">Weft picks</th>
              {warpLengthCm !== null && weftStats !== null && (
                <th className="px-3 py-2 text-right">Est. weft length</th>
              )}
              {!locked && <th className="px-3 py-2 text-left">Replace with</th>}
            </tr>
          </thead>
          <tbody>
            {visibleColors.map((c) => {
              const displayHex = pending[c.hex] ?? c.hex;
              const warpStat = warpStats?.find((s) => s.hex === c.hex);
              const weftStat = weftStats?.find((s) => s.hex === c.hex);
              const estLength =
                warpLengthCm !== null && weftStat && weftTotal > 0
                  ? formatApproxLength(warpLengthCm * (weftStat.count / weftTotal), unit)
                  : null;

              return (
                <tr key={c.hex} className="border-b border-border last:border-0">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block h-5 w-5 rounded border border-border flex-shrink-0"
                        style={{ background: displayHex }}
                      />
                      <span className="font-mono text-xs text-muted-foreground">
                        {c.hex}
                        {pending[c.hex] && (
                          <span className="ml-1 text-accent"> → {pending[c.hex]}</span>
                        )}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {warpStat ? `${warpStat.count} (${warpStat.percentage}%)` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {weftStat ? `${weftStat.count} (${weftStat.percentage}%)` : "—"}
                  </td>
                  {warpLengthCm !== null && weftStats !== null && (
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {estLength ?? "—"}
                    </td>
                  )}
                  {!locked && (
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={displayHex}
                          onChange={(e) => setReplacement(c.hex, e.target.value)}
                          className="h-6 w-10 cursor-pointer rounded border border-border bg-transparent p-0.5"
                          title="Pick replacement color"
                        />
                        {pending[c.hex] && (
                          <button
                            className="text-xs text-muted-foreground hover:text-foreground"
                            onClick={() => setReplacement(c.hex, c.hex)}
                            title="Reset to original"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Color replacement preview card */}
      {previewOpen && (
        <div className="rounded-lg border border-border overflow-hidden">
          <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-muted/20">
            <span className="text-sm font-medium">Preview with color replacements</span>
            <button
              className="rounded p-0.5 text-muted-foreground hover:text-foreground"
              onClick={() => setPreviewOpen(false)}
            >
              <AppIcons.close className="h-4 w-4" />
            </button>
          </div>
          <div className="p-3">
            <button
              type="button"
              className="block rounded-md border border-border hover:border-ring transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
              onClick={() => setPreviewModalOpen(true)}
              title="Click to open full-size preview"
            >
              <AuthedImage
                src={drawdownPreviewUrl(projectId, pending)}
                alt="Color replacement preview"
                className="block rounded-md"
                style={{ maxWidth: 220, maxHeight: 220, width: "auto", height: "auto" }}
              />
            </button>
          </div>
        </div>
      )}

      {previewModalOpen && (
        <DrawdownModal
          svgUrl={drawdownSvgUrl(projectId, 8, pending)}
          onClose={() => setPreviewModalOpen(false)}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Warp setup editor (visible + editable when status === "created")
// ---------------------------------------------------------------------------

// Map any WIF / loom unit string to the two supported display units.
// "in"-family → "in"; everything metric (cm, mm, m) → "cm"; null → null.
function mapToSupportedUnit(unit: string | null | undefined): LengthUnit | null {
  if (!unit) return null;
  const u = unit.toLowerCase().trim();
  if (u === "in" || u.startsWith("inch") || u === "\"" ||
      u === "yd" || u.startsWith("yard") || u.startsWith("ft") || u.startsWith("foot") || u.startsWith("feet")) return "in";
  if (u === "cm" || u.startsWith("cent") || u === "mm" || u.startsWith("milli") || u === "m" || u.startsWith("meter") || u.startsWith("metre")) return "cm";
  return null;
}

function WarpSetupSection({
  project,
  displayUnit,
  onUpdated,
}: {
  project: ProjectDetail;
  displayUnit: LengthUnit;
  onUpdated: (p: ProjectDetail) => void;
}) {
  // Per-field unit defaults: prefer the original source unit over the user's global preference.
  // Length / item + waste-between: use the draft WIF warp_length_unit if available.
  // Loom waste: use the loom version's warp_waste_unit if available.
  const defaultItemUnit: LengthUnit =
    mapToSupportedUnit(project.draft_wif_measurements?.warp_length_unit) ?? displayUnit;
  const defaultWasteUnit: LengthUnit =
    (mapToSupportedUnit(project.loom_warp_waste_unit) ?? displayUnit) as LengthUnit;

  const [itemUnit, setItemUnit] = useState<LengthUnit>(defaultItemUnit);
  const [wasteUnit, setWasteUnit] = useState<LengthUnit>(defaultWasteUnit);

  // Ground-truth loom waste in cm; changes only when backend data refreshes.
  const loomWasteDefaultCm = useMemo((): number | null => {
    if (project.warp_waste_allowance) {
      const n = parseFloat(project.warp_waste_allowance);
      if (!isNaN(n)) return convertLength(n, (project.length_unit as LengthUnit) ?? "cm", "cm");
    }
    if (project.loom_warp_waste_allowance) {
      const n = parseFloat(project.loom_warp_waste_allowance);
      if (!isNaN(n)) return convertLength(n, (project.loom_warp_waste_unit as LengthUnit) ?? "cm", "cm");
    }
    return null;
  }, [project.warp_waste_allowance, project.loom_warp_waste_allowance, project.loom_warp_waste_unit, project.length_unit]);

  // Helpers to convert a stored project value (in project.length_unit) to a target unit via cm.
  function fromStored(raw: string | null, target: LengthUnit): string {
    if (!raw) return "";
    const n = parseFloat(raw);
    if (isNaN(n)) return "";
    const cm = convertLength(n, (project.length_unit as LengthUnit) ?? "cm", "cm");
    return convertLength(cm, "cm", target).toFixed(1);
  }

  // Initialise field values in their respective field units.
  const [items, setItems] = useState(String(project.num_items ?? 1));
  const [lengthPerItem, setLengthPerItem] = useState(() => {
    if (project.finished_length_per_item) return fromStored(project.finished_length_per_item, defaultItemUnit);
    if (project.draft_warp_length_cm != null) return convertLength(project.draft_warp_length_cm, "cm", defaultItemUnit).toFixed(1);
    return "";
  });
  const [loomWaste, setLoomWaste] = useState(() =>
    loomWasteDefaultCm !== null ? convertLength(loomWasteDefaultCm, "cm", defaultWasteUnit).toFixed(1) : ""
  );
  const [loomWasteDirty, setLoomWasteDirty] = useState(false);
  const [wasteBetween, setWasteBetween] = useState(() => fromStored(project.waste_between_items, defaultItemUnit));

  // Keep refs so the useEffect below can read current values without triggering on them.
  const wasteUnitRef = useRef(wasteUnit);
  const loomWasteDirtyRef = useRef(loomWasteDirty);
  useLayoutEffect(() => {
    wasteUnitRef.current = wasteUnit;
    loomWasteDirtyRef.current = loomWasteDirty;
  });

  // Sync loom waste when backend data changes (e.g. navigating back after setting loom default).
  // Intentionally omits wasteUnit and loomWasteDirty from deps — those are handled by the
  // explicit handlers below so a unit change or edit doesn't re-run this effect.
  useEffect(() => {
    if (loomWasteDirtyRef.current) return;
    setLoomWaste(
      loomWasteDefaultCm !== null
        ? convertLength(loomWasteDefaultCm, "cm", wasteUnitRef.current).toFixed(1)
        : ""
    );
  }, [loomWasteDefaultCm]);  

  // Unit-change handlers auto-convert current field values to the new unit.
  function handleItemUnitChange(newUnit: LengthUnit) {
    const conv = (v: string) => { const n = parseFloat(v); return isNaN(n) ? v : convertLength(n, itemUnit, newUnit).toFixed(1); };
    if (lengthPerItem) setLengthPerItem(conv(lengthPerItem));
    if (wasteBetween) setWasteBetween(conv(wasteBetween));
    setItemUnit(newUnit);
  }
  function handleWasteUnitChange(newUnit: LengthUnit) {
    if (loomWaste) { const n = parseFloat(loomWaste); if (!isNaN(n)) setLoomWaste(convertLength(n, wasteUnit, newUnit).toFixed(1)); }
    setWasteUnit(newUnit);
  }

  const numItems = Math.max(1, parseInt(items, 10) || 1);

  // "Origin" values for dirty detection — computed in current field units so a unit change alone isn't dirty.
  const origLength = (() => {
    if (project.finished_length_per_item) return fromStored(project.finished_length_per_item, itemUnit);
    if (project.draft_warp_length_cm != null) return convertLength(project.draft_warp_length_cm, "cm", itemUnit).toFixed(1);
    return "";
  })();
  const origWaste = loomWasteDefaultCm !== null ? convertLength(loomWasteDefaultCm, "cm", wasteUnit).toFixed(1) : "";
  const origBetween = fromStored(project.waste_between_items, itemUnit);

  const isDirty =
    items !== String(project.num_items ?? 1) ||
    lengthPerItem !== origLength ||
    loomWaste !== origWaste ||
    (numItems > 1 && wasteBetween !== origBetween);

  const mutation = useMutation({
    mutationFn: () => {
      const toCm = (v: string, u: LengthUnit) => convertLength(parseFloat(v), u, "cm");
      return updateProjectWarpSetup(project.id, {
        num_items: numItems,
        finished_length_per_item: lengthPerItem ? toCm(lengthPerItem, itemUnit) : null,
        waste_between_items: numItems > 1 && wasteBetween ? toCm(wasteBetween, itemUnit) : null,
        warp_waste_allowance: loomWaste ? toCm(loomWaste, wasteUnit) : null,
        length_unit: "cm",
      });
    },
    onSuccess: (updated) => { setLoomWasteDirty(false); onUpdated(updated); },
  });

  const inputCls = "flex-1 min-w-0 rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring";
  const unitSelect = (value: LengthUnit, onChange: (u: LengthUnit) => void) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as LengthUnit)}
      className="shrink-0 rounded border border-input bg-background px-1 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
    >
      <option value="cm">cm</option>
      <option value="in">in</option>
    </select>
  );

  const loomWasteUnconfigured = project.loom_id && !project.loom_warp_waste_allowance && !project.warp_waste_allowance;

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Warp Setup</h3>
      <div className="grid grid-cols-[1fr_1fr] gap-x-4 gap-y-2 text-sm items-start">
        <label className="text-muted-foreground self-center">Items</label>
        <input
          type="number"
          min="1"
          value={items}
          onChange={(e) => setItems(e.target.value)}
          className="w-full rounded border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />

        <label className="text-muted-foreground self-center">Length / item</label>
        <div className="flex gap-1">
          <input type="number" min="0" step="0.1" value={lengthPerItem}
            onChange={(e) => setLengthPerItem(e.target.value)} className={inputCls} />
          {unitSelect(itemUnit, handleItemUnitChange)}
        </div>

        <div className="self-start pt-1">
          <label className="text-muted-foreground">Loom waste</label>
          {loomWasteUnconfigured && (
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
              Default not set on loom.{" "}
              <Link to={`/looms/${project.loom_id}`} className="underline underline-offset-2 hover:text-foreground">
                Configure loom
              </Link>
            </p>
          )}
        </div>
        <div className="flex gap-1 self-start pt-1">
          <input type="number" min="0" step="0.1" value={loomWaste}
            onChange={(e) => { setLoomWaste(e.target.value); setLoomWasteDirty(true); }} className={inputCls} />
          {unitSelect(wasteUnit, handleWasteUnitChange)}
        </div>

        {numItems > 1 && (
          <>
            <label className="text-muted-foreground self-center">Waste between items</label>
            <div className="flex gap-1">
              <input type="number" min="0" step="0.1" value={wasteBetween}
                onChange={(e) => setWasteBetween(e.target.value)} className={inputCls} />
              {unitSelect(itemUnit, handleItemUnitChange)}
            </div>
          </>
        )}
      </div>

      {isDirty && (
        <Button size="sm" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save"}
        </Button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Share modal
// ---------------------------------------------------------------------------

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.cssText = "position:fixed;opacity:0;top:0;left:0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }
}

function ShareModal({
  project,
  onUpdated,
  onClose,
}: {
  project: ProjectDetail;
  onUpdated: (updated: ProjectDetail) => void;
  onClose: () => void;
}) {
  const [visibility, setVisibility] = useState<"link" | "public">(
    project.share_visibility === "public" ? "public" : "link"
  );
  const [expiryDays, setExpiryDays] = useState<string>("30");
  const [copied, setCopied] = useState(false);

  const hasSlug = !!project.share_slug && project.share_visibility !== "private";
  const shareUrl = hasSlug ? `${window.location.origin}/p/${project.share_slug}` : null;

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const shareMutation = useMutation({
    mutationFn: () => {
      const days = parseInt(expiryDays, 10);
      const expires = !isNaN(days) && days > 0
        ? new Date(Date.now() + days * 86_400_000).toISOString()
        : null;
      return updateProjectShare(project.id, visibility, expires);
    },
    onSuccess: onUpdated,
  });

  const revokeMutation = useMutation({
    mutationFn: () => revokeProjectShare(project.id),
    onSuccess: () => {
      onUpdated({ ...project, share_slug: null, share_visibility: "private", share_expires_at: null });
      onClose();
    },
  });

  async function handleCopy() {
    if (!shareUrl) return;
    const ok = await copyToClipboard(shareUrl);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } else {
      alert(`Copy this URL:\n${shareUrl}`);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-card rounded-xl border border-border shadow-2xl flex flex-col max-w-md w-full">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="font-semibold text-sm flex items-center gap-2">
            <AppIcons.share className="h-4 w-4" />
            Share project
          </h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {hasSlug && shareUrl ? (
            <>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={shareUrl}
                  className="flex-1 rounded border border-border bg-muted px-2 py-1.5 text-xs font-mono text-muted-foreground select-all min-w-0"
                  onClick={(e) => (e.target as HTMLInputElement).select()}
                />
                <Button variant="outline" size="sm" onClick={handleCopy} className="shrink-0 min-w-[72px]">
                  {copied ? "Copied!" : (
                    <><AppIcons.copyLink className="h-3.5 w-3.5 mr-1" />Copy</>
                  )}
                </Button>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                <span>{project.share_visibility === "public" ? "Public" : "Anyone with link"}</span>
                {project.share_expires_at && (
                  <span>· expires {new Date(project.share_expires_at).toLocaleDateString()}</span>
                )}
                <a
                  href={`/p/${project.share_slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-auto flex items-center gap-1 hover:text-foreground transition-colors"
                >
                  View <AppIcons.externalLink className="h-3 w-3" />
                </a>
              </div>
              <div className="pt-1 border-t border-border">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => revokeMutation.mutate()}
                  disabled={revokeMutation.isPending}
                >
                  {revokeMutation.isPending ? "Revoking…" : "Revoke link"}
                </Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-xs text-muted-foreground">
                Create a read-only link to share this project with others.
              </p>
              <div className="flex gap-4 text-sm flex-wrap">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name={`vis-${project.id}`}
                    value="link"
                    checked={visibility === "link"}
                    onChange={() => setVisibility("link")}
                  />
                  Anyone with link
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name={`vis-${project.id}`}
                    value="public"
                    checked={visibility === "public"}
                    onChange={() => setVisibility("public")}
                  />
                  Public (listed)
                </label>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <label className="text-muted-foreground text-xs shrink-0">Expires after</label>
                <select
                  value={expiryDays}
                  onChange={(e) => setExpiryDays(e.target.value)}
                  className="rounded border border-border bg-background px-2 py-1 text-xs"
                >
                  <option value="7">7 days</option>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                  <option value="365">1 year</option>
                  <option value="">Never</option>
                </select>
              </div>
              <Button
                size="sm"
                onClick={() => shareMutation.mutate()}
                disabled={shareMutation.isPending}
              >
                {shareMutation.isPending ? "Creating…" : "Create link"}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notes inline editor
// ---------------------------------------------------------------------------

function NotesSection({
  projectId,
  initialNotes,
  onUpdated,
}: {
  projectId: string;
  initialNotes: string | null;
  onUpdated: (updated: ProjectDetail) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialNotes ?? "");

  const mutation = useMutation({
    mutationFn: (notes: string) => updateProjectNotes(projectId, notes || null),
    onSuccess: (updated) => {
      onUpdated(updated);
      setEditing(false);
    },
  });

  if (!editing) {
    return (
      <section className="space-y-1">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Notes</h3>
          <button
            className="text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setEditing(true)}
          >
            {initialNotes ? "Edit" : "Add notes"}
          </button>
        </div>
        {initialNotes && (
          <p className="text-sm whitespace-pre-wrap text-foreground/80">{initialNotes}</p>
        )}
      </section>
    );
  }

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Notes</h3>
      <textarea
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-y min-h-[80px]"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        autoFocus
      />
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => mutation.mutate(value)}
          disabled={mutation.isPending}
        >
          Save
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => { setValue(initialNotes ?? ""); setEditing(false); }}
        >
          Cancel
        </Button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function ProjectLandingPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthContext();
  const qc = useQueryClient();
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");

  const [drawdownOpen, setDrawdownOpen] = useState(false);
  const [tieupOpen, setTieupOpen] = useState(false);
  const [shareModalOpen, setShareModalOpen] = useState(false);

  const { data: project, isLoading, error } = useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id!),
    enabled: !!id,
  });

  const colorMutation = useMutation({
    mutationFn: (replacements: Record<string, string>) =>
      setProjectColorReplacements(id!, replacements),
    onSuccess: (updated) => qc.setQueryData(["project", id], updated),
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects");
    },
  });

  const progress = useMemo(() => {
    if (!project) return null;
    const done = project.current_pick - 1;
    const pct = Math.min(100, Math.round((done / Math.max(project.total_picks, 1)) * 100));
    return { pct, done, total: project.total_picks };
  }, [project]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
        Loading project…
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center justify-center h-40 gap-3">
        <p className="text-sm text-muted-foreground">Project not found.</p>
        <Button variant="outline" size="sm" onClick={() => navigate("/projects")}>
          Back to Projects
        </Button>
      </div>
    );
  }

  const isActive = project.status === "active" || project.status === "created";
  const m = project.draft_wif_measurements;
  const warpLengthCm = project.draft_warp_length_cm;

  return (
    <div className="h-full overflow-y-auto">
    <div className="mx-auto max-w-3xl px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="mt-0.5 flex-shrink-0"
          onClick={() => navigate("/projects")}
        >
          <AppIcons.chevronRight className="h-4 w-4 rotate-180" />
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE[project.status] ?? "bg-muted text-muted-foreground"}`}
            >
              {PROJECT_STATUS_LABELS[project.status]}
            </span>
            <span className="rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {PROJECT_TYPE_LABELS[project.project_type]}
            </span>
            {project.share_slug && project.share_visibility !== "private" && (
              <button
                onClick={() => setShareModalOpen(true)}
                className="rounded-full px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/60 dark:text-blue-300 flex items-center gap-1 hover:opacity-80 transition-opacity"
                title="Project is shared — click to manage"
              >
                <AppIcons.share className="h-3 w-3" />
                Shared
              </button>
            )}
          </div>
          <h1 className="text-xl font-semibold leading-tight truncate">{project.name}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            <Link to={`/drafts/${project.draft_id}`} className="hover:underline">
              {project.draft_name}
            </Link>
            {project.loom_name && <span> · {project.loom_name}</span>}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="mt-0.5 flex-shrink-0 text-muted-foreground hover:text-foreground"
          onClick={() => setShareModalOpen(true)}
          title="Share project"
        >
          <AppIcons.share className="h-4 w-4" />
        </Button>
      </div>

      {/* Preview + specs */}
      <div className="grid grid-cols-[auto_1fr] gap-4 items-start">
        <div className="flex flex-col gap-1.5 flex-shrink-0">
          <button
            className="rounded-lg overflow-hidden border border-border bg-muted/20 hover:border-ring transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
            onClick={() => setDrawdownOpen(true)}
            title="Click to view full drawdown"
          >
            <AuthedImage
              src={previewUrl(project.draft_id)}
              alt="Draft preview"
              className="h-36 w-36 object-contain"
            />
          </button>
          {project.project_type === "treadle" && (
            <button
              className="text-xs text-center text-muted-foreground hover:text-foreground py-0.5 border border-border/50 rounded hover:border-border transition-colors"
              onClick={() => setTieupOpen(true)}
              title="View treadle tie-up diagram"
            >
              Tie-up
            </button>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm pt-1">
          {project.draft_num_shafts != null && (
            <>
              <dt className="text-muted-foreground">Shafts</dt>
              <dd>{project.draft_effective_num_shafts ?? project.draft_num_shafts}</dd>
            </>
          )}
          {project.draft_num_treadles != null && (
            <>
              <dt className="text-muted-foreground">Treadles</dt>
              <dd>{project.draft_effective_num_treadles ?? project.draft_num_treadles}</dd>
            </>
          )}
          {project.draft_warp_threads != null && (
            <>
              <dt className="text-muted-foreground">Warp threads</dt>
              <dd>{project.draft_warp_threads}</dd>
            </>
          )}
          {project.draft_weft_threads != null && (
            <>
              <dt className="text-muted-foreground">Picks / repeat</dt>
              <dd>{project.draft_weft_threads}</dd>
            </>
          )}
          {project.draft_weaving_width_override_cm != null && (
            <>
              <dt className="text-muted-foreground">Weaving width</dt>
              <dd>{displayLength(project.draft_weaving_width_override_cm, "cm", displayUnit)}</dd>
            </>
          )}
          {project.draft_epi_override != null ? (
            <>
              <dt className="text-muted-foreground">Sett</dt>
              <dd>{project.draft_epi_override} e.p.i.</dd>
            </>
          ) : m?.warp_spacing != null ? (
            <>
              <dt className="text-muted-foreground">Warp spacing</dt>
              <dd>{displayLength(m.warp_spacing, "cm", displayUnit)}</dd>
            </>
          ) : null}
          {warpLengthCm != null && (
            <>
              <dt className="text-muted-foreground">Warp length</dt>
              <dd>{displayLength(warpLengthCm, "cm", displayUnit)}</dd>
            </>
          )}
          {project.finished_length_per_item && (
            <>
              <dt className="text-muted-foreground">Length / item</dt>
              <dd>{displayLength(project.finished_length_per_item, project.length_unit, displayUnit)}</dd>
            </>
          )}
          {project.num_items > 1 && (
            <>
              <dt className="text-muted-foreground">Items</dt>
              <dd>{project.num_items}</dd>
            </>
          )}
          {project.waste_between_items && (
            <>
              <dt className="text-muted-foreground">Waste between items</dt>
              <dd>{displayLength(project.waste_between_items, project.length_unit, displayUnit)}</dd>
            </>
          )}
          {project.warp_waste_allowance && (
            <>
              <dt className="text-muted-foreground">Loom waste</dt>
              <dd>{displayLength(project.warp_waste_allowance, project.length_unit, displayUnit)}</dd>
            </>
          )}
        </dl>
      </div>

      {/* Progress */}
      {progress && (
        <section className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Progress</span>
            <span className="tabular-nums">
              {progress.done} / {progress.total} picks · {progress.pct}%
              {project.num_items > 1 &&
                ` · item ${project.current_item} of ${project.num_items}`}
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${progress.pct}%` }}
            />
          </div>
        </section>
      )}

      {/* Color palette */}
      {project.draft_wif_colors && project.draft_wif_colors.length > 0 && (
        <ColorPaletteSection
          projectId={project.id}
          wifColors={project.draft_wif_colors}
          warpStats={project.draft_warp_color_stats}
          weftStats={project.draft_weft_color_stats}
          colorReplacements={project.color_replacements}
          warpLengthCm={warpLengthCm}
          onSave={(r) => colorMutation.mutate(r)}
          isSaving={colorMutation.isPending}
          locked={project.status !== "created"}
        />
      )}

      {/* Warp setup — editable before weaving starts */}
      {project.status === "created" && (
        <WarpSetupSection
          project={project}
          displayUnit={displayUnit}
          onUpdated={(updated) => qc.setQueryData(["project", id], updated)}
        />
      )}

      {/* Notes */}
      <NotesSection
        projectId={project.id}
        initialNotes={project.notes}
        onUpdated={(updated) => qc.setQueryData(["project", id], updated)}
      />

      {/* Actions */}
      <section className="flex flex-wrap gap-2 pt-2 border-t border-border">
        <Button
          variant="destructive"
          onClick={() => {
            if (confirm("Delete this project? This cannot be undone.")) {
              deleteMutation.mutate();
            }
          }}
          disabled={deleteMutation.isPending}
        >
          Delete
        </Button>
        <Link
          to={`/projects/${project.id}/warping-plan`}
          className={cn(buttonVariants({ variant: "outline" }), "ml-auto")}
        >
          Weave Plan
        </Link>
        {isActive && (
          <Link
            to={`/projects/${project.id}/track`}
            className={cn(buttonVariants({ variant: project.status === "created" ? "success" : "default" }))}
          >
            <AppIcons.projectActive className="h-4 w-4 mr-1.5" />
            {project.status === "created" ? "Start Weaving" : "Track"}
          </Link>
        )}
      </section>

      {/* Drawdown modal */}
      {drawdownOpen && (
        <DrawdownModal
          svgUrl={
            project.has_drawdown_svg
              ? projectDrawdownSvgUrl(project.id)
              : drawdownSvgUrl(project.id, 8)
          }
          title={project.draft_name}
          onClose={() => setDrawdownOpen(false)}
        />
      )}
      {/* Tie-up modal */}
      {tieupOpen && (
        <TieUpModal
          projectId={project.id}
          draftName={project.draft_name}
          onClose={() => setTieupOpen(false)}
        />
      )}
      {/* Share modal */}
      {shareModalOpen && (
        <ShareModal
          project={project}
          onUpdated={(updated) => qc.setQueryData(["project", id], updated)}
          onClose={() => setShareModalOpen(false)}
        />
      )}
    </div>
    </div>
  );
}
