import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getProject, deleteProject, previewUrl } from "@/api/projects";
import { Button } from "@/components/ui/button";

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: project, isLoading, error } = useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects", { replace: true });
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-destructive">Project not found.</span>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b px-6 py-4 flex items-center gap-4">
        <Link to="/projects" className="text-sm text-muted-foreground hover:text-foreground">
          ← Projects
        </Link>
        <span className="font-semibold">{project.name}</span>
      </header>

      <main className="flex-1 p-6 max-w-5xl mx-auto w-full space-y-6">

        {/* Lint status */}
        {project.lint_errors.length > 0 && (
          <div className="rounded-md bg-destructive/10 p-4 space-y-1">
            <p className="text-sm font-medium text-destructive">Errors</p>
            {project.lint_errors.map((e, i) => (
              <p key={i} className="text-sm text-destructive">{e}</p>
            ))}
          </div>
        )}
        {project.lint_warnings.length > 0 && (
          <div className="rounded-md bg-muted p-4 space-y-1">
            <p className="text-sm font-medium">Warnings</p>
            {project.lint_warnings.map((w, i) => (
              <p key={i} className="text-sm text-muted-foreground">{w}</p>
            ))}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Metadata */}
          <div className="space-y-4">
            <h2 className="text-base font-semibold">Design Info</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">File</dt>
              <dd>{project.wif_filename}</dd>
              <dt className="text-muted-foreground">Shafts</dt>
              <dd>{project.num_shafts ?? "—"}</dd>
              <dt className="text-muted-foreground">Treadles</dt>
              <dd>{project.num_treadles ?? "—"}</dd>
              <dt className="text-muted-foreground">Warp threads</dt>
              <dd>{project.warp_threads ?? "—"}</dd>
              <dt className="text-muted-foreground">Weft threads</dt>
              <dd>{project.weft_threads ?? "—"}</dd>
              {project.wif_source_software && (
                <>
                  <dt className="text-muted-foreground">Source software</dt>
                  <dd>{project.wif_source_software}{project.wif_source_version ? ` ${project.wif_source_version}` : ""}</dd>
                </>
              )}
            </dl>

            <h2 className="text-base font-semibold pt-2">Features</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              {(
                [
                  ["Threading diagram", project.has_threading],
                  ["Tie-up grid", project.has_tieup],
                  ["Treadle-tracking", project.has_treadling],
                  ["Lift-tracking", project.has_liftplan],
                  ["Color palette", project.has_color_palette],
                ] as [string, boolean][]
              ).map(([label, available]) => (
                <>
                  <dt key={`${label}-dt`} className="text-muted-foreground">{label}</dt>
                  <dd key={`${label}-dd`} className={available ? "text-foreground" : "text-muted-foreground"}>
                    {available ? "✓ Available" : "✗ Not in file"}
                  </dd>
                </>
              ))}
            </dl>

            <div className="pt-4 flex gap-2">
              {!confirmDelete ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => setConfirmDelete(true)}
                >
                  Delete project
                </Button>
              ) : (
                <>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => deleteMutation.mutate()}
                    disabled={deleteMutation.isPending}
                  >
                    Confirm delete
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)}>
                    Cancel
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Preview */}
          <div>
            <h2 className="text-base font-semibold mb-3">Design Preview</h2>
            {project.has_preview ? (
              <div className="overflow-auto rounded-lg border bg-white p-2">
                <img
                  src={previewUrl(project.id)}
                  alt={`Draft preview for ${project.name}`}
                  className="max-w-full"
                />
              </div>
            ) : (
              <div className="rounded-lg border border-dashed p-8 text-center">
                <p className="text-sm text-muted-foreground">
                  Preview not available for this file.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
