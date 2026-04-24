import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listActivities, ACTIVITY_TYPE_LABELS, ACTIVITY_STATUS_LABELS, type ActivitySummary } from "@/api/activities";
import { CreateActivityModal } from "@/components/activities/CreateActivityModal";
import { Button } from "@/components/ui/button";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  completed: "bg-muted text-muted-foreground",
  abandoned: "bg-muted text-muted-foreground",
};

function ActivityCard({ activity }: { activity: ActivitySummary }) {
  const pct = activity.total_picks > 0
    ? Math.round((Math.min(activity.current_pick - 1, activity.total_picks) / activity.total_picks) * 100)
    : 0;

  return (
    <Link
      to={`/activities/${activity.id}`}
      className="block rounded-lg border p-4 hover:border-ring transition-colors"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium">{activity.name}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[activity.status]}`}>
          {ACTIVITY_STATUS_LABELS[activity.status]}
        </span>
      </div>
      <p className="mt-0.5 text-sm text-muted-foreground">{ACTIVITY_TYPE_LABELS[activity.activity_type]}</p>
      <div className="mt-3">
        <div className="mb-1 flex justify-between text-xs text-muted-foreground">
          <span>Pick {Math.min(activity.current_pick, activity.total_picks)} of {activity.total_picks}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </Link>
  );
}

export function ActivitiesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);

  const { data: activities = [], isLoading, error } = useQuery({
    queryKey: ["activities"],
    queryFn: listActivities,
  });

  const active = activities.filter((a) => a.status === "active");
  const finished = activities.filter((a) => a.status !== "active");

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Dashboard</Link>
          <span className="font-semibold">Activities</span>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)}>New activity</Button>
      </header>

      <main className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-8">
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

        {finished.length > 0 && (
          <section>
            <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Completed &amp; abandoned</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {finished.map((a) => <ActivityCard key={a.id} activity={a} />)}
            </div>
          </section>
        )}
      </main>

      {showCreate && (
        <CreateActivityModal
          onSuccess={(id) => { queryClient.invalidateQueries({ queryKey: ["activities"] }); navigate(`/activities/${id}`); }}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}
