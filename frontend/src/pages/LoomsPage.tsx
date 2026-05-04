import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { listLooms, type Loom } from "@/api/looms";
import { AppIcons } from "@/lib/icons";
import { listActivities } from "@/api/activities";
import { NewLoomModal } from "@/components/looms/NewLoomModal";
import { Button } from "@/components/ui/button";

interface LoomActivityCounts {
  active: number;
  completed: number;
  abandoned: number;
}

function LoomCard({ loom, activityCounts }: { loom: Loom; activityCounts?: LoomActivityCounts }) {
  const v = loom.current_version;
  return (
    <Link
      to={`/looms/${loom.id}`}
      className="rounded-lg border p-5 hover:border-ring transition-colors block"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3">
          <div className="shrink-0 mt-0.5">
            {loom.supports_lift_tracking
              ? <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
              : loom.supports_treadle_tracking
                ? <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                : <AppIcons.equipment className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />}
          </div>
          <div>
            <p className="font-medium">{loom.manufacturer} {loom.model_name}</p>
            {loom.serial_number && (
              <p className="text-xs text-muted-foreground">S/N: {loom.serial_number}</p>
            )}
          </div>
        </div>
        <div className="text-right text-xs text-muted-foreground shrink-0">
          {v && (
            <span>
              {v.num_shafts != null ? `${v.num_shafts}S` : null}
              {v.num_shafts != null && v.num_treadles != null ? " / " : null}
              {v.num_treadles != null ? `${v.num_treadles}T` : null}
            </span>
          )}
        </div>
      </div>
      {v?.weaving_width && (
        <p className="mt-2 text-sm text-muted-foreground">
          Weaving width: {v.weaving_width} {v.weaving_width_unit}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        {loom.supports_lift_tracking && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">lift tracking</span>
        )}
        {loom.supports_treadle_tracking && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">treadle tracking</span>
        )}
      </div>
      {activityCounts && (activityCounts.active + activityCounts.completed + activityCounts.abandoned) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t pt-2.5">
          {activityCounts.active > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
              {activityCounts.active} active
            </span>
          )}
          {activityCounts.completed > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {activityCounts.completed} completed
            </span>
          )}
          {activityCounts.abandoned > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {activityCounts.abandoned} abandoned
            </span>
          )}
        </div>
      )}
    </Link>
  );
}

export function LoomsPage() {
  const [showNew, setShowNew] = useState(false);
  const queryClient = useQueryClient();

  const { data: looms, isLoading, error } = useQuery({
    queryKey: ["looms"],
    queryFn: listLooms,
  });

  const { data: activities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities(),
  });

  const activityCountsByLoom = activities.reduce<Record<string, LoomActivityCounts>>(
    (acc, a) => {
      if (!a.loom_id) return acc;
      if (!acc[a.loom_id]) acc[a.loom_id] = { active: 0, completed: 0, abandoned: 0 };
      if (a.status === "active") acc[a.loom_id].active++;
      else if (a.status === "completed") acc[a.loom_id].completed++;
      else if (a.status === "abandoned") acc[a.loom_id].abandoned++;
      return acc;
    },
    {},
  );

  const handleSuccess = () => {
    setShowNew(false);
    queryClient.invalidateQueries({ queryKey: ["looms"] });
  };

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Equipment</h1>
        <Button size="sm" onClick={() => setShowNew(true)}>New loom</Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Failed to load looms
        </p>
      )}
      {looms && looms.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-muted-foreground">No looms yet.</p>
          <Button className="mt-4" onClick={() => setShowNew(true)}>
            Add your first loom
          </Button>
        </div>
      )}
      {looms && looms.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {looms.map((l) => (
            <LoomCard key={l.id} loom={l} activityCounts={activityCountsByLoom[l.id]} />
          ))}
        </div>
      )}

      {showNew && (
        <NewLoomModal onSuccess={handleSuccess} onClose={() => setShowNew(false)} />
      )}
    </div>
  );
}
