import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listProjects } from "@/api/projects";
import { listActivities } from "@/api/activities";
import { ProjectCard } from "@/components/projects/ProjectCard";
import { UploadWifModal } from "@/components/projects/UploadWifModal";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { useNavigate, Link } from "react-router-dom";

export function ProjectsPage() {
  const { user, refetch: refetchAuth } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);

  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const { data: activities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities(),
  });

  const activityCountsByProject = activities.reduce<Record<string, { active: number; planning: number; completed: number; abandoned: number }>>(
    (acc, a) => {
      const pid = a.project_id;
      if (!acc[pid]) acc[pid] = { active: 0, planning: 0, completed: 0, abandoned: 0 };
      if (a.status === "active" && !!a.loom_id) acc[pid].active++;
      else if (a.status === "active" && !a.loom_id) acc[pid].planning++;
      else if (a.status === "completed") acc[pid].completed++;
      else if (a.status === "abandoned") acc[pid].abandoned++;
      return acc;
    },
    {},
  );

  const handleUploadSuccess = () => {
    setShowUpload(false);
    queryClient.invalidateQueries({ queryKey: ["projects"] });
  };

  const handleLogout = async () => {
    await fetch("/auth/logout", { method: "POST", credentials: "include" });
    refetchAuth();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">← Dashboard</Link>
          <span className="font-semibold">Projects</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <Link to="/settings" className="text-sm text-muted-foreground hover:text-foreground">
            Settings
          </Link>
          <Button variant="outline" size="sm" onClick={handleLogout}>
            Sign out
          </Button>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-4xl mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold">Projects</h1>
          <Button onClick={() => setShowUpload(true)}>New Project</Button>
        </div>

        {isLoading && (
          <p className="text-sm text-muted-foreground">Loading projects…</p>
        )}

        {error && (
          <p className="text-sm text-destructive">Failed to load projects.</p>
        )}

        {!isLoading && projects.length === 0 && (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">
              No projects yet. Upload a WIF file to get started.
            </p>
            <Button className="mt-4" onClick={() => setShowUpload(true)}>
              New Project
            </Button>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} activityCounts={activityCountsByProject[p.id]} />
          ))}
        </div>
      </main>

      {showUpload && (
        <UploadWifModal
          onSuccess={handleUploadSuccess}
          onClose={() => setShowUpload(false)}
        />
      )}
    </div>
  );
}
