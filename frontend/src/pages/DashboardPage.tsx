import { useAuth } from "@/hooks/useAuth";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listActivities, ACTIVITY_TYPE_LABELS } from "@/api/activities";
import { listProjects } from "@/api/projects";
import { listLooms } from "@/api/looms";
import { AppIcons } from "@/lib/icons";

export function DashboardPage() {
  const { user } = useAuth();

  const { data: activities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities(),
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const { data: looms = [] } = useQuery({
    queryKey: ["looms"],
    queryFn: listLooms,
  });

  const activeActivities = activities.filter((a) => a.status === "active" && !!a.loom_id);
  const planningActivities = activities.filter((a) => a.status === "active" && !a.loom_id);
  const completedCount = activities.filter((a) => a.status === "completed").length;

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

      {/* Projects */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Projects</h2>
          <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground">
            View all →
          </Link>
        </div>
        {projects.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-muted-foreground">No projects uploaded yet.</p>
            <Link to="/projects" className="mt-2 inline-block text-sm text-foreground underline underline-offset-2">
              Upload a WIF file →
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {projects.slice(0, 3).map((project) => (
              <Link
                key={project.id}
                to="/projects"
                className="rounded-lg border p-4 hover:border-ring transition-colors flex items-start gap-3"
              >
                <div className="shrink-0 mt-0.5">
                  <AppIcons.project className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{project.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground truncate">{project.wif_filename}</p>
                </div>
              </Link>
            ))}
            {projects.length > 3 && (
              <Link
                to="/projects"
                className="rounded-lg border border-dashed p-4 flex items-center justify-center hover:border-ring transition-colors"
              >
                <span className="text-xs text-muted-foreground">+{projects.length - 3} more</span>
              </Link>
            )}
          </div>
        )}
      </section>

      {/* Activities */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide">Activities</h2>
          <Link to="/activities" className="text-xs text-muted-foreground hover:text-foreground">
            View all →
          </Link>
        </div>

        {activeActivities.length > 0 && (
          <div className="space-y-3 mb-3">
            {activeActivities.map((a) => {
              const pct =
                a.total_picks > 0
                  ? Math.round((Math.min(a.current_pick - 1, a.total_picks) / a.total_picks) * 100)
                  : 0;
              return (
                <Link
                  key={a.id}
                  to={`/activities/${a.id}`}
                  className="flex items-center gap-4 rounded-lg border p-4 hover:border-ring transition-colors"
                >
                  <div className="shrink-0">
                    {a.activity_type === "treadle"
                      ? <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                      : <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{a.name}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {ACTIVITY_TYPE_LABELS[a.activity_type]}
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

        {planningActivities.length > 0 && (
          <div className="space-y-2 mb-3">
            {planningActivities.map((a) => (
              <Link
                key={a.id}
                to={`/activities/${a.id}`}
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

        {activeActivities.length === 0 && planningActivities.length === 0 && (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-muted-foreground">No active activities.</p>
            <Link
              to="/activities"
              className="mt-2 inline-block text-sm text-foreground underline underline-offset-2"
            >
              Start or plan an activity →
            </Link>
          </div>
        )}

        <div className="mt-3 grid grid-cols-2 gap-3">
          <div className="rounded-lg border p-4 flex items-center gap-3">
            <AppIcons.activityCompleted className="h-6 w-6 text-muted-foreground shrink-0" strokeWidth={1.75} />
            <div>
              <p className="text-2xl font-bold tabular-nums">{completedCount}</p>
              <p className="text-xs text-muted-foreground">Completed</p>
            </div>
          </div>
          <div className="rounded-lg border p-4 flex items-center gap-3">
            <AppIcons.activityActive className="h-6 w-6 text-muted-foreground shrink-0" strokeWidth={1.75} />
            <div>
              <p className="text-2xl font-bold tabular-nums">{activeActivities.length + planningActivities.length}</p>
              <p className="text-xs text-muted-foreground">Active</p>
            </div>
          </div>
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
