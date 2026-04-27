import { useAuth } from "@/hooks/useAuth";
import { api } from "@/api/client";
import { useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { listActivities, ACTIVITY_TYPE_LABELS } from "@/api/activities";
import { listProjects } from "@/api/projects";
import { listLooms } from "@/api/looms";

export function DashboardPage() {
  const { user, refetch } = useAuth();
  const navigate = useNavigate();

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

  const handleLogout = async () => {
    await api.post("/auth/logout");
    refetch();
    navigate("/login", { replace: true });
  };

  const activeActivities = activities.filter((a) => a.status === "active" && !!a.loom_id);
  const planningActivities = activities.filter((a) => a.status === "active" && !a.loom_id);
  const completedCount = activities.filter((a) => a.status === "completed").length;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <span className="font-semibold">Weaving Tracker</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <Link to="/settings" className="text-sm text-muted-foreground hover:text-foreground">
            Settings
          </Link>
          {user?.is_admin && (
            <Link to="/admin" className="text-sm text-muted-foreground hover:text-foreground">
              Admin
            </Link>
          )}
          <Button variant="outline" size="sm" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-8">
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
                  className="rounded-lg border p-4 hover:border-ring transition-colors"
                >
                  <p className="text-sm font-medium truncate">{loom.model_name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground truncate">{loom.manufacturer}</p>
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
                  className="rounded-lg border p-4 hover:border-ring transition-colors"
                >
                  <p className="text-sm font-medium truncate">{project.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{project.wif_filename}</p>
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
                  className="flex items-center justify-between rounded-lg border px-4 py-3 hover:border-ring transition-colors"
                >
                  <div>
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
            <div className="rounded-lg border p-4 text-center">
              <p className="text-2xl font-bold tabular-nums">{completedCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">Completed</p>
            </div>
            <div className="rounded-lg border p-4 text-center">
              <p className="text-2xl font-bold tabular-nums">{activities.length}</p>
              <p className="mt-1 text-xs text-muted-foreground">Total activities</p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
