import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getActivity, getActivityPicks, stepActivity, completeActivity, abandonActivity,
  restartActivity, cloneActivity, listActivities, deleteActivity,
  renameActivity, ApiError, ACTIVITY_TYPE_LABELS, ACTIVITY_STATUS_LABELS,
  type ActivityDetail, type ActivitySummary, type PickRow,
} from "@/api/activities";
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
// Pick display
// ---------------------------------------------------------------------------

function PickDisplay({
  pick,
  activityType,
  totalShaftsOrTreadles,
  colorMode,
  showWeftColor,
}: {
  pick: PickRow;
  activityType: string;
  totalShaftsOrTreadles: number;
  colorMode: ColorMode;
  showWeftColor: boolean;
}) {
  const label = activityType === "lift" ? "Shaft" : "Treadle";
  const count = Math.max(totalShaftsOrTreadles, Math.max(...pick.active, 0));
  const weftHex = pick.color ?? null; // always read weft color independent of mode
  const colorInBoxes = colorMode !== "theme"; // strip/filled render color inside boxes
  // One row always — boxes scale to fill width regardless of shaft/treadle count
  const cols = count;

  return (
    <div className="space-y-4 w-full">
      <p className="text-center text-sm text-muted-foreground">
        {activityType === "lift" ? "Raise shafts" : "Press treadles"}
      </p>

      {/* Weft color band — full width, all modes, glanceable at a distance */}
      {showWeftColor && weftHex && (
        <div
          className="w-full rounded-lg h-12 flex items-center justify-center border border-border"
          style={{ backgroundColor: weftHex, color: contrastColor(weftHex) }}
        >
          <span className="text-xs font-semibold uppercase tracking-widest opacity-70">Weft Color</span>
        </div>
      )}

      <div
        className="grid w-full gap-2"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: count }, (_, i) => i + 1).map((n) => {
          const active = pick.active.includes(n);

          // Strip mode: primary fill + weft color accent at bottom
          if (colorMode === "strip" && colorInBoxes) {
            return (
              <div
                key={n}
                className={`relative aspect-square flex flex-col items-center justify-center rounded-lg border-2 font-bold overflow-hidden transition-colors ${
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-muted bg-muted/30 text-muted-foreground"
                }`}
              >
                <span className="text-[0.6em] font-normal opacity-60">{label[0]}</span>
                <span className="text-[1em] leading-tight">{n}</span>
                {active && weftHex && (
                  <span
                    className="absolute bottom-0 left-0 right-0 h-[14%]"
                    style={{ backgroundColor: weftHex }}
                  />
                )}
              </div>
            );
          }

          // Filled mode: weft color background + thick contrast border
          if (colorMode === "filled" && colorInBoxes && active && weftHex) {
            const fg = contrastColor(weftHex);
            return (
              <div
                key={n}
                style={{ backgroundColor: weftHex, borderColor: fg, color: fg }}
                className="aspect-square flex flex-col items-center justify-center rounded-lg border-4 font-bold"
              >
                <span className="text-[0.6em] font-normal opacity-70">{label[0]}</span>
                <span className="text-[1em] leading-tight">{n}</span>
              </div>
            );
          }

          // Theme mode (also fallback for strip/filled when no weft color)
          return (
            <div
              key={n}
              className={`aspect-square flex flex-col items-center justify-center rounded-lg border-2 font-bold transition-colors ${
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-muted bg-muted/30 text-muted-foreground"
              }`}
            >
              <span className="text-[0.6em] font-normal opacity-60">{label[0]}</span>
              <span className="text-[1em] leading-tight">{n}</span>
            </div>
          );
        })}
      </div>

      {pick.active.length === 0 && (
        <p className="text-center text-sm text-muted-foreground italic">
          No active {label.toLowerCase()}s for this pick
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step controls
// ---------------------------------------------------------------------------

function StepControls({
  activity,
  onStep,
  stepping,
}: {
  activity: ActivityDetail;
  onStep: (dir: "advance" | "reverse") => void;
  stepping: boolean;
}) {
  const atStart = activity.current_pick <= 1;
  const pastEnd = activity.current_pick > activity.total_picks;

  return (
    <div className="flex items-center justify-center gap-8">
      <button
        onClick={() => onStep("reverse")}
        disabled={atStart || stepping || activity.status !== "active"}
        className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-input text-3xl font-light transition-colors hover:border-ring hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Previous pick"
      >
        ‹
      </button>

      <div className="text-center min-w-28">
        <p className="text-5xl font-bold tabular-nums">
          {Math.min(activity.current_pick, activity.total_picks)}
        </p>
        <p className="text-sm text-muted-foreground">of {activity.total_picks}</p>
      </div>

      <button
        onClick={() => onStep("advance")}
        disabled={pastEnd || stepping || activity.status !== "active"}
        className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-input text-3xl font-light transition-colors hover:border-ring hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed"
        aria-label="Next pick"
      >
        ›
      </button>
    </div>
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
// Page
// ---------------------------------------------------------------------------

export function ActivityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [stepping, setStepping] = useState(false);
  const [colorMode, setColorMode] = useState<ColorMode>("strip");
  const [showWeftColor, setShowWeftColor] = useState(true);
  const [editingName, setEditingName] = useState(false);
  const [nameInput, setNameInput] = useState("");
  const [confirmComplete, setConfirmComplete] = useState(false);
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const [confirmClone, setConfirmClone] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [cloneConflict, setCloneConflict] = useState<ActivitySummary | null>(null);
  const [restartConflict, setRestartConflict] = useState<ActivitySummary | null>(null);

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

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["activity", id] });

  const handleStep = useCallback(async (direction: "advance" | "reverse") => {
    if (!id || stepping) return;
    setStepping(true);
    try {
      const updated = await stepActivity(id, direction);
      queryClient.setQueryData(["activity", id], updated);
    } finally {
      setStepping(false);
    }
  }, [id, stepping, queryClient]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); handleStep("advance"); }
      if (e.key === "ArrowLeft") { e.preventDefault(); handleStep("reverse"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleStep]);

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

  const currentPickIndex = activity.current_pick - 1;
  const currentPickData = picksData?.picks[currentPickIndex];
  const prevPickData = currentPickIndex > 0 ? picksData?.picks[currentPickIndex - 1] : undefined;
  const nextPickData = picksData?.picks[currentPickIndex + 1];

  const declaredCount = activity.activity_type === "lift"
    ? (activity.project_num_shafts ?? 0)
    : (activity.project_num_treadles ?? 0);
  // Use declared count as the authoritative box count; fall back to pick data only when undeclared
  const maxFromPicks = picksData ? Math.max(0, ...picksData.picks.flatMap((p) => p.active)) : 0;
  const maxActive = declaredCount > 0 ? declaredCount : maxFromPicks;

  const isFinished = activity.current_pick > activity.total_picks;

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
                  queryClient.setQueryData(["activity", id], updated);
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
                      queryClient.setQueryData(["activity", id], updated);
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
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${
          activity.status === "active"
            ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
            : "bg-muted text-muted-foreground"
        }`}>
          {ACTIVITY_STATUS_LABELS[activity.status]}
        </span>
      </header>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        {/* Progress + color mode — comfortable narrow band */}
        <div className="mx-auto max-w-2xl px-8 pt-6 space-y-3">
          <ProgressBar current={activity.current_pick} total={activity.total_picks} />
          {picksData?.has_weft_colors && (
            <div className="flex items-center justify-end gap-4">
              {/* Weft color toggle */}
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

              {/* Color mode segmented control */}
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

        {/* Pick display — full viewport width, generous padding */}
        <div className="px-8 py-6">
          {isFinished ? (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-lg font-medium">All {activity.total_picks} picks complete!</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Mark the activity as completed when you're done.
              </p>
            </div>
          ) : currentPickData ? (
            <PickDisplay
              pick={currentPickData}
              activityType={activity.activity_type}
              totalShaftsOrTreadles={maxActive}
              colorMode={colorMode}
              showWeftColor={showWeftColor}
            />
          ) : (
            <div className="mx-auto max-w-lg rounded-lg border border-dashed p-10 text-center">
              <p className="text-sm text-muted-foreground">Pick data loading…</p>
            </div>
          )}
        </div>

        {/* Step controls + preview + hint — centered column */}
        <div className="mx-auto max-w-lg px-8 pb-6 space-y-6">
          {activity.status === "active" && (
            <StepControls activity={activity} onStep={handleStep} stepping={stepping} />
          )}

          {picksData && activity.status === "active" && !isFinished && (
            <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
              {prevPickData && (
                <div className="rounded-md border border-dashed p-3">
                  <div className="mb-1 flex items-center gap-1.5 font-medium">
                    {prevPickData.color && showWeftColor && (
                      <span
                        className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm border border-border"
                        style={{ backgroundColor: prevPickData.color }}
                      />
                    )}
                    ← Pick {activity.current_pick - 1}
                  </div>
                  <p>{prevPickData.active.length > 0 ? prevPickData.active.join(", ") : "—"}</p>
                </div>
              )}
              {nextPickData && (
                <div className={`rounded-md border border-dashed p-3 ${!prevPickData ? "col-start-2" : ""}`}>
                  <div className="mb-1 flex items-center gap-1.5 font-medium">
                    {nextPickData.color && showWeftColor && (
                      <span
                        className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm border border-border"
                        style={{ backgroundColor: nextPickData.color }}
                      />
                    )}
                    Pick {activity.current_pick + 1} →
                  </div>
                  <p>{nextPickData.active.length > 0 ? nextPickData.active.join(", ") : "—"}</p>
                </div>
              )}
            </div>
          )}

          {activity.status === "active" && (
            <p className="text-center text-xs text-muted-foreground">
              ← → arrow keys or spacebar to navigate picks
            </p>
          )}
        </div>

        {/* Collapsible sections — readable width */}
        <div className="mx-auto max-w-2xl px-8 pb-10 space-y-0 border-t">
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

          {activity.status === "active" && (
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
    </div>
  );
}
