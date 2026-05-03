import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listActivities, ACTIVITY_TYPE_LABELS, ACTIVITY_STATUS_LABELS, type ActivitySummary } from "@/api/activities";
import { previewUrl } from "@/api/projects";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { CreateActivityModal } from "@/components/activities/CreateActivityModal";
import { AssignLoomModal } from "@/components/activities/AssignLoomModal";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  plan: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  completed: "bg-muted text-muted-foreground",
  abandoned: "bg-muted text-muted-foreground",
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function groupByYear(
  items: ActivitySummary[],
  getDate: (a: ActivitySummary) => string | null,
): Array<{ year: number; items: ActivitySummary[] }> {
  const map = new Map<number, ActivitySummary[]>();
  for (const item of items) {
    const d = getDate(item);
    const year = d ? new Date(d).getFullYear() : new Date().getFullYear();
    if (!map.has(year)) map.set(year, []);
    map.get(year)!.push(item);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b - a)
    .map(([year, items]) => ({ year, items }));
}

function ActivityCard({ activity, onAssign }: {
  activity: ActivitySummary;
  onAssign?: (id: string) => void;
}) {
  const [showPreview, setShowPreview] = useState(false);
  const isPlanning = activity.status === "active" && !activity.loom_id;
  const badgeKey = isPlanning ? "plan" : activity.status;
  const badgeLabel = isPlanning ? "Plan" : ACTIVITY_STATUS_LABELS[activity.status];

  const endDate = activity.status === "completed"
    ? activity.completed_at
    : activity.status === "abandoned"
      ? activity.abandoned_at
      : null;

  const pct = activity.total_picks > 0
    ? Math.round((Math.min(activity.current_pick - 1, activity.total_picks) / activity.total_picks) * 100)
    : 0;

  return (
    <div className="relative rounded-lg border hover:border-ring transition-colors">
      <Link to={`/activities/${activity.id}`} className="block p-4">
        <div className="flex items-start justify-between gap-2">
          <span className="font-medium">{activity.name}</span>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              aria-label="Preview design"
              onClick={(e) => { e.preventDefault(); setShowPreview(true); }}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title="Preview design"
            >
              <svg width="13" height="13" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
                <rect x="0" y="0" width="5" height="5" rx="1" />
                <rect x="7" y="0" width="5" height="5" rx="1" />
                <rect x="0" y="7" width="5" height="5" rx="1" />
                <rect x="7" y="7" width="5" height="5" rx="1" />
              </svg>
            </button>
            <span className={`min-w-[5.5rem] text-center rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[badgeKey]}`}>
              {badgeLabel}
            </span>
          </div>
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">{ACTIVITY_TYPE_LABELS[activity.activity_type]}</p>
        {endDate && (
          <p className="mt-0.5 text-xs text-muted-foreground">{fmtDate(endDate)}</p>
        )}
        {!isPlanning && activity.status === "active" && (
          <div className="mt-3">
            <div className="mb-1 flex justify-between text-xs text-muted-foreground">
              <span>Pick {Math.min(activity.current_pick, activity.total_picks)} of {activity.total_picks}</span>
              <span>{pct}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )}
      </Link>
      {isPlanning && onAssign && (
        <div className="border-t px-3 pb-3 pt-2">
          <button
            type="button"
            onClick={() => onAssign(activity.id)}
            className="w-full rounded-md border border-dashed border-input px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-ring hover:bg-muted hover:text-foreground"
          >
            Assign to loom…
          </button>
        </div>
      )}
      {showPreview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowPreview(false)}
        >
          <div className="relative max-w-xl w-full" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setShowPreview(false)}
              className="absolute -top-9 right-0 text-white/70 hover:text-white text-sm"
            >
              Close ✕
            </button>
            <p className="absolute -top-9 left-0 text-white/70 text-sm truncate max-w-xs">{activity.name}</p>
            <AuthedImage
              src={previewUrl(activity.project_id)}
              alt="Design preview"
              className="w-full rounded-lg shadow-2xl"
              style={{ imageRendering: "pixelated" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function YearGroup({
  year,
  items,
  defaultExpanded,
  onAssign,
}: {
  year: number;
  items: ActivitySummary[];
  defaultExpanded: boolean;
  onAssign?: (id: string) => void;
}) {
  const [open, setOpen] = useState(defaultExpanded);
  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-2 mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{year} ({items.length})</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((a) => <ActivityCard key={a.id} activity={a} onAssign={onAssign} />)}
        </div>
      )}
    </div>
  );
}

export function ActivitiesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [assigningActivityId, setAssigningActivityId] = useState<string | null>(null);

  const { data: activities = [], isLoading, error } = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities(),
  });

  const currentYear = new Date().getFullYear();

  const planning = activities.filter((a) => a.status === "active" && !a.loom_id);
  const active = activities.filter((a) => a.status === "active" && !!a.loom_id);

  const completed = activities
    .filter((a) => a.status === "completed")
    .sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? ""));

  const abandoned = activities
    .filter((a) => a.status === "abandoned")
    .sort((a, b) => (b.abandoned_at ?? "").localeCompare(a.abandoned_at ?? ""));

  const completedByYear = groupByYear(completed, (a) => a.completed_at);
  const abandonedByYear = groupByYear(abandoned, (a) => a.abandoned_at);

  return (
    <div className="p-6 max-w-3xl mx-auto w-full space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Activities</h1>
        <Button size="sm" onClick={() => setShowCreate(true)}>New activity</Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">Failed to load activities.</p>}

      {!isLoading && activities.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">No activities yet. Start one to begin tracking a weaving session.</p>
          <Button className="mt-4" onClick={() => setShowCreate(true)}>New activity</Button>
        </div>
      )}

      {active.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Active</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {active.map((a) => <ActivityCard key={a.id} activity={a} />)}
          </div>
        </section>
      )}

      {planning.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Planning</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {planning.map((a) => <ActivityCard key={a.id} activity={a} onAssign={setAssigningActivityId} />)}
          </div>
        </section>
      )}

      {completedByYear.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Completed</h2>
          <div className="space-y-4">
            {completedByYear.map(({ year, items }) => (
              <YearGroup
                key={year}
                year={year}
                items={items}
                defaultExpanded={year === currentYear}
              />
            ))}
          </div>
        </section>
      )}

      {abandonedByYear.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Abandoned</h2>
          <div className="space-y-4">
            {abandonedByYear.map(({ year, items }) => (
              <YearGroup
                key={year}
                year={year}
                items={items}
                defaultExpanded={false}
              />
            ))}
          </div>
        </section>
      )}

      {showCreate && (
        <CreateActivityModal
          onSuccess={(id) => { queryClient.invalidateQueries({ queryKey: ["activities"] }); navigate(`/activities/${id}`); }}
          onClose={() => setShowCreate(false)}
        />
      )}

      {assigningActivityId && (
        <AssignLoomModal
          activityId={assigningActivityId}
          activeActivities={activities.filter((a) => a.status === "active")}
          onSuccess={() => { setAssigningActivityId(null); queryClient.invalidateQueries({ queryKey: ["activities"] }); }}
          onClose={() => setAssigningActivityId(null)}
        />
      )}
    </div>
  );
}
