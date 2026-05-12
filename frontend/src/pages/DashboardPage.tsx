import { useAuth } from "@/hooks/useAuth";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { listProjects, PROJECT_TYPE_LABELS } from "@/api/projects";
import { listDrafts } from "@/api/drafts";
import { listLooms } from "@/api/looms";
import { getActivityHeatmap, type ActivityDay } from "@/api/users";
import { AppIcons } from "@/lib/icons";

const DOW_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const RANGE_OPTIONS = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 366 },
] as const;

function intensityClass(count: number): string {
  if (count === 0) return "bg-muted";
  if (count <= 2) return "bg-accent/30";
  if (count <= 5) return "bg-accent/55";
  if (count <= 10) return "bg-accent/80";
  return "bg-accent";
}

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

interface TooltipState {
  day: ActivityDay;
  x: number;
  y: number;
}

function defaultDaysFromHistory(earliestDate: string | null): number {
  if (!earliestDate) return 30;
  const ageDays = (Date.now() - new Date(earliestDate + "T00:00:00Z").getTime()) / 86_400_000;
  if (ageDays < 30) return 30;
  if (ageDays < 90) return 90;
  if (ageDays < 180) return 180;
  return 366;
}

function buildGrid(rangeStart: Date, rangeEnd: Date): Date[][] {
  const start = new Date(rangeStart);
  start.setDate(start.getDate() - start.getDay()); // align to Sunday
  const days: Date[] = [];
  const cur = new Date(start);
  while (cur <= rangeEnd) {
    days.push(new Date(cur));
    cur.setDate(cur.getDate() + 1);
  }
  const weeks: Date[][] = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return weeks;
}

function HeatmapGrid({
  weeks,
  rangeEnd,
  dayByDate,
  onCellEnter,
  onCellLeave,
}: {
  weeks: Date[][];
  rangeEnd: Date;
  dayByDate: Map<string, ActivityDay>;
  onCellEnter: (e: React.MouseEvent, dateStr: string) => void;
  onCellLeave: () => void;
}) {
  const monthLabels: { label: string; col: number }[] = [];
  weeks.forEach((week, wi) => {
    week.forEach((d) => {
      if (d.getDate() === 1) monthLabels.push({ label: d.toLocaleString("default", { month: "short" }), col: wi });
    });
  });

  return (
    <div className="overflow-x-auto pb-1">
      <div className="inline-flex flex-col gap-[3px]" style={{ minWidth: "max-content" }}>
        <div className="flex gap-[3px]" style={{ paddingLeft: "22px" }}>
          {weeks.map((_, wi) => {
            const label = monthLabels.find((m) => m.col === wi);
            return (
              <div key={wi} className="w-[10px] text-[9px] text-muted-foreground leading-none overflow-visible whitespace-nowrap">
                {label ? label.label : ""}
              </div>
            );
          })}
        </div>
        {[0, 1, 2, 3, 4, 5, 6].map((dow) => (
          <div key={dow} className="flex items-center gap-[3px]">
            <span className="w-[18px] text-[9px] text-muted-foreground text-right shrink-0 leading-none">
              {dow % 2 === 1 ? DOW_LABELS[dow] : ""}
            </span>
            {weeks.map((week, wi) => {
              const day = week[dow];
              if (!day || day > rangeEnd) return <div key={wi} className="w-[10px] h-[10px] rounded-[2px] opacity-0" />;
              const dateStr = toDateStr(day);
              const count = dayByDate.get(dateStr)?.count ?? 0;
              return (
                <div
                  key={wi}
                  className={`w-[10px] h-[10px] rounded-[2px] ${intensityClass(count)} ${count > 0 ? "cursor-pointer" : "cursor-default"}`}
                  onMouseEnter={(e) => onCellEnter(e, dateStr)}
                  onMouseLeave={onCellLeave}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function ActivityHeatmap() {
  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  // null = user hasn't made an explicit choice; effective values are derived from data
  const [selectedDays, setSelectedDays] = useState<number | null>(null);
  const [selectedYear, setSelectedYear] = useState<number>(today.getFullYear());
  const [mode, setMode] = useState<"range" | "year" | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Base fetch: always 366-day window + metadata
  const { data: baseData } = useQuery({
    queryKey: ["activity-heatmap"],
    queryFn: () => getActivityHeatmap(),
    staleTime: 60_000,
  });

  const earliestDate = baseData?.earliest_activity_date ?? null;

  // Derive effective mode — user choice wins; fall back to data-driven default
  const effectiveMode = useMemo((): "range" | "year" => {
    if (mode !== null) return mode;
    if (!earliestDate) return "range";
    return (today.getTime() - new Date(earliestDate + "T00:00:00Z").getTime()) / 86_400_000 >= 365
      ? "year"
      : "range";
  }, [mode, earliestDate, today]);

  // Derive effective days — user choice wins; fall back to data-driven default
  const effectiveDays = useMemo(
    () => selectedDays ?? defaultDaysFromHistory(earliestDate),
    [selectedDays, earliestDate],
  );

  // Year fetch: only when in year mode
  const { data: yearData } = useQuery({
    queryKey: ["activity-heatmap-year", selectedYear],
    queryFn: () => getActivityHeatmap({ year: selectedYear }),
    enabled: effectiveMode === "year",
    staleTime: 5 * 60_000,
  });

  const displayData = effectiveMode === "year" ? yearData : baseData;
  const dayByDate = new Map((displayData?.days ?? []).map((d) => [d.date, d]));

  const yearsWithActivity = baseData?.years_with_activity ?? [];
  const hasMultipleYears = useMemo(() => {
    if (effectiveMode === "year") return true;
    if (yearsWithActivity.length > 1) return true;
    if (!earliestDate) return false;
    return (today.getTime() - new Date(earliestDate + "T00:00:00Z").getTime()) / 86_400_000 >= 365;
  }, [effectiveMode, yearsWithActivity, earliestDate, today]);

  // Grid bounds
  let rangeStart: Date;
  let rangeEnd: Date;
  if (effectiveMode === "year") {
    rangeStart = new Date(selectedYear, 0, 1);
    rangeEnd = selectedYear === today.getFullYear() ? today : new Date(selectedYear, 11, 31);
  } else {
    rangeEnd = today;
    rangeStart = new Date(today);
    rangeStart.setDate(today.getDate() - effectiveDays + 1);
  }
  const weeks = buildGrid(rangeStart, rangeEnd);

  const totalSteps = (displayData?.days ?? []).reduce((s, d) => s + d.count, 0);
  const activeDays = (displayData?.days ?? []).filter((d) => d.count > 0).length;

  function scheduleHide() {
    hideTimerRef.current = setTimeout(() => setTooltip(null), 120);
  }
  function cancelHide() {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
  }
  function handleCellEnter(e: React.MouseEvent, dateStr: string) {
    cancelHide();
    const day = dayByDate.get(dateStr);
    if (!day || day.count === 0) { setTooltip(null); return; }
    setTooltip({ day, x: e.clientX, y: e.clientY });
  }

  return (
    <div className="space-y-3">
      {/* Selector row */}
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {totalSteps.toLocaleString()} step{totalSteps !== 1 ? "s" : ""} across {activeDays} day{activeDays !== 1 ? "s" : ""}
        </p>
        {hasMultipleYears ? (
          <select
            value={selectedYear}
            onChange={(e) => { setMode("year"); setSelectedYear(Number(e.target.value)); setTooltip(null); }}
            className="text-xs rounded border border-border bg-background px-2 py-0.5 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {(yearsWithActivity.length > 0 ? yearsWithActivity : [today.getFullYear()]).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        ) : (
          <div className="flex gap-1">
            {RANGE_OPTIONS.map(({ label, days }) => (
              <button
                key={label}
                onClick={() => { setMode("range"); setSelectedDays(days); setTooltip(null); }}
                className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                  effectiveMode === "range" && effectiveDays === days
                    ? "border-ring bg-accent text-accent-foreground font-medium"
                    : "border-border text-muted-foreground hover:text-foreground hover:border-ring"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>

      <HeatmapGrid
        weeks={weeks}
        rangeEnd={rangeEnd}
        dayByDate={dayByDate}
        onCellEnter={handleCellEnter}
        onCellLeave={scheduleHide}
      />

      <div className="flex items-center gap-1.5 justify-end">
        <span className="text-[9px] text-muted-foreground">Less</span>
        {[0, 2, 5, 10, 11].map((v) => (
          <div key={v} className={`w-[10px] h-[10px] rounded-[2px] ${intensityClass(v)}`} />
        ))}
        <span className="text-[9px] text-muted-foreground">More</span>
      </div>

      {tooltip && (
        <div
          className="fixed z-50 w-52 rounded-lg border bg-popover text-popover-foreground shadow-md p-3 space-y-2"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
          onMouseEnter={cancelHide}
          onMouseLeave={scheduleHide}
        >
          <p className="text-xs font-medium text-muted-foreground">
            {new Date(tooltip.day.date + "T12:00:00").toLocaleDateString("default", {
              weekday: "short", year: "numeric", month: "short", day: "numeric",
            })}
          </p>
          <ul className="space-y-1">
            {tooltip.day.projects.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/projects/${p.id}`}
                  className="flex items-center justify-between gap-2 rounded px-1.5 py-1 text-xs hover:bg-muted transition-colors"
                  onClick={() => setTooltip(null)}
                >
                  <span className="truncate font-medium">{p.name}</span>
                  <span className="shrink-0 text-muted-foreground tabular-nums">{p.step_count} step{p.step_count !== 1 ? "s" : ""}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const { data: drafts = [] } = useQuery({
    queryKey: ["drafts"],
    queryFn: listDrafts,
  });

  const { data: looms = [] } = useQuery({
    queryKey: ["looms"],
    queryFn: listLooms,
  });

  const activeProjects = projects.filter((a) => a.status === "active" && !!a.loom_id);
  const planningProjects = projects.filter((a) => a.status === "active" && !a.loom_id);
  const completedCount = projects.filter((a) => a.status === "completed").length;

  return (
    <div className="p-6 max-w-3xl mx-auto w-full space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-muted-foreground">Welcome back, {user?.display_name}.</p>
      </div>

      {/* Equipment */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Equipment</h2>
          <Link to="/looms" className="text-xs text-muted-foreground hover:text-foreground">
            View all →
          </Link>
        </div>
        {looms.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-muted-foreground">No looms added yet.</p>
            <Link to="/looms" className="mt-2 inline-block text-sm text-foreground underline underline-offset-2">
              Add your first loom →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {looms.slice(0, 3).map((loom) => (
              <Link
                key={loom.id}
                to="/looms"
                className="rounded-lg border p-4 hover:border-ring transition-colors flex items-start gap-3"
              >
                <div className="shrink-0 mt-0.5">
                  {loom.supports_lift_tracking
                    ? <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                    : loom.supports_treadle_tracking
                      ? <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                      : <AppIcons.equipment className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{loom.model_name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground truncate">{loom.manufacturer}</p>
                </div>
              </Link>
            ))}
            {looms.length > 3 && (
              <Link
                to="/looms"
                className="rounded-lg border border-dashed p-4 flex items-center justify-center hover:border-ring transition-colors"
              >
                <span className="text-xs text-muted-foreground">+{looms.length - 3} more</span>
              </Link>
            )}
          </div>
        )}
      </section>

      {/* Drafts */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Drafts</h2>
          <Link to="/drafts" className="text-xs text-muted-foreground hover:text-foreground">
            View all →
          </Link>
        </div>
        {drafts.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-muted-foreground">No drafts uploaded yet.</p>
            <Link to="/drafts" className="mt-2 inline-block text-sm text-foreground underline underline-offset-2">
              Upload a WIF file →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {drafts.slice(0, 3).map((draft) => (
              <Link
                key={draft.id}
                to="/drafts"
                className="rounded-lg border p-4 hover:border-ring transition-colors flex items-start gap-3"
              >
                <div className="shrink-0 mt-0.5">
                  <AppIcons.draft className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{draft.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground truncate">{draft.wif_filename}</p>
                </div>
              </Link>
            ))}
            {drafts.length > 3 && (
              <Link
                to="/drafts"
                className="rounded-lg border border-dashed p-4 flex items-center justify-center hover:border-ring transition-colors"
              >
                <span className="text-xs text-muted-foreground">+{drafts.length - 3} more</span>
              </Link>
            )}
          </div>
        )}
      </section>

      {/* Projects */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Projects</h2>
          <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground">
            View all →
          </Link>
        </div>

        {activeProjects.length > 0 && (
          <div className="space-y-3 mb-3">
            {activeProjects.map((a) => {
              const pct =
                a.total_picks > 0
                  ? Math.round((Math.min(a.current_pick - 1, a.total_picks) / a.total_picks) * 100)
                  : 0;
              return (
                <Link
                  key={a.id}
                  to={`/projects/${a.id}`}
                  className="flex items-center gap-4 rounded-lg border p-4 hover:border-ring transition-colors"
                >
                  <div className="shrink-0">
                    {a.project_type === "treadle"
                      ? <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                      : <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{a.name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {PROJECT_TYPE_LABELS[a.project_type]}
                    </p>
                    <div className="mt-2">
                      <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                        <span>
                          Pick {Math.min(a.current_pick, a.total_picks)} of {a.total_picks}
                        </span>
                        <span>{pct}%</span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  <span className="shrink-0 text-sm text-muted-foreground">Continue →</span>
                </Link>
              );
            })}
          </div>
        )}

        {planningProjects.length > 0 && (
          <div className="space-y-2 mb-3">
            {planningProjects.map((a) => (
              <Link
                key={a.id}
                to={`/projects/${a.id}`}
                className="flex items-center gap-4 rounded-lg border px-4 py-3 hover:border-ring transition-colors"
              >
                <AppIcons.planning className="h-6 w-6 text-muted-foreground shrink-0" strokeWidth={1.75} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{a.name}</p>
                  <p className="text-xs text-muted-foreground">{a.total_picks} picks planned</p>
                </div>
                <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
                  Plan
                </span>
              </Link>
            ))}
          </div>
        )}

        {activeProjects.length === 0 && planningProjects.length === 0 && (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-muted-foreground">No active projects.</p>
            <Link
              to="/projects"
              className="mt-2 inline-block text-sm text-foreground underline underline-offset-2"
            >
              Start or plan a project →
            </Link>
          </div>
        )}

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="rounded-lg border p-4 flex items-center gap-3">
            <AppIcons.projectActive className="h-6 w-6 text-muted-foreground shrink-0" strokeWidth={1.75} />
            <div>
              <p className="text-2xl font-bold tabular-nums">{activeProjects.length + planningProjects.length}</p>
              <p className="text-xs text-muted-foreground">Active</p>
            </div>
          </div>
          <div className="rounded-lg border p-4 flex items-center gap-3">
            <AppIcons.projectCompleted className="h-6 w-6 text-muted-foreground shrink-0" strokeWidth={1.75} />
            <div>
              <p className="text-2xl font-bold tabular-nums">{completedCount}</p>
              <p className="text-xs text-muted-foreground">Completed</p>
            </div>
          </div>
        </div>
      </section>

      {/* Activity heatmap */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Activity</h2>
        <div className="rounded-lg border p-4">
          <ActivityHeatmap />
        </div>
      </section>

      {/* Storage */}
      {user && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Storage</h2>
          <div className="rounded-lg border p-4">
            {(() => {
              const usedMB = user.storage_used_bytes / (1024 * 1024);
              const quotaMB = user.storage_quota_bytes / (1024 * 1024);
              const pct = Math.min(Math.round((user.storage_used_bytes / user.storage_quota_bytes) * 100), 100);
              const barColor = pct >= 90 ? "bg-red-500" : pct >= 75 ? "bg-amber-500" : "bg-primary";
              return (
                <>
                  <div className="mb-2 flex justify-between text-sm">
                    <span>{usedMB < 1 ? `${Math.round(usedMB * 1024)} KB` : `${usedMB.toFixed(1)} MB`} used</span>
                    <span className="text-muted-foreground">{Math.round(quotaMB)} MB total</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${pct}%` }} />
                  </div>
                  <p className="mt-1.5 text-xs text-muted-foreground text-right">{pct}% used</p>
                </>
              );
            })()}
          </div>
        </section>
      )}
    </div>
  );
}
