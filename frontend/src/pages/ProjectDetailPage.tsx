import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getProject, deleteProject, generateLiftplan, overrideProjectMetadata, previewUrl, downloadWif, downloadWifModified } from "@/api/projects";
import { listActivities } from "@/api/activities";
import { ActivitySummaryList } from "@/components/activities/ActivitySummaryList";
import { CreateActivityModal } from "@/components/activities/CreateActivityModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showDangerZone, setShowDangerZone] = useState(false);
  const [showCreateActivity, setShowCreateActivity] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const { data: project, isLoading, error } = useQuery({
    queryKey: ["project", id],
    queryFn: () => getProject(id!),
    enabled: !!id,
  });

  const { data: projectActivities = [] } = useQuery({
    queryKey: ["activities", { projectId: id }],
    queryFn: () => listActivities({ projectId: id! }),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects", { replace: true });
    },
  });

  const generateMutation = useMutation({
    mutationFn: () => generateLiftplan(id!),
    onSuccess: (updated) => {
      queryClient.setQueryData(["project", id], updated);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  const overrideMutation = useMutation({
    mutationFn: ({ field, value }: { field: "num_treadles" | "num_shafts"; value: number }) =>
      overrideProjectMetadata(id!, field, value),
    onSuccess: (updated) => {
      queryClient.setQueryData(["project", id], updated);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
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
    <div className="p-6 max-w-5xl mx-auto w-full space-y-6">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/projects" className="text-stone-500 hover:text-stone-900">Projects</Link>
        <ChevronRight className="h-3.5 w-3.5 text-stone-400" />
        <span className="font-medium text-stone-900">{project.name}</span>
      </div>

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
          {/* Left column: Info + Features + Activities */}
          <div className="space-y-6">
            <div className="space-y-4">
              <h2 className="text-base font-semibold">Design Info</h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">File</dt>
                <dd className="flex flex-wrap items-center gap-2">
                  <span>{project.wif_filename}</span>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
                    disabled={downloading}
                    onClick={async () => {
                      setDownloadError(null);
                      setDownloading(true);
                      try {
                        await downloadWif(project.id, project.wif_filename);
                      } catch {
                        setDownloadError("Download failed");
                      } finally {
                        setDownloading(false);
                      }
                    }}
                  >
                    {downloading ? "Downloading…" : project.has_modified_file ? "Download original" : "Download"}
                  </button>
                  {project.has_modified_file && (
                    <button
                      type="button"
                      className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
                      disabled={downloading}
                      onClick={async () => {
                        setDownloadError(null);
                        setDownloading(true);
                        try {
                          await downloadWifModified(project.id, project.wif_filename);
                        } catch {
                          setDownloadError("Download failed");
                        } finally {
                          setDownloading(false);
                        }
                      }}
                    >
                      Download modified
                    </button>
                  )}
                </dd>
                {downloadError && (
                  <dd className="col-span-2 text-xs text-destructive">{downloadError}</dd>
                )}
                <dt className="text-muted-foreground">Shafts</dt>
                <dd className="flex items-center gap-1.5">
                  {project.num_shafts ?? "—"}
                  {project.metadata_overrides?.num_shafts && (
                    <span className="text-xs text-muted-foreground">(value overwritten)</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">Treadles</dt>
                <dd className="flex items-center gap-1.5">
                  {project.num_treadles ?? "—"}
                  {project.metadata_overrides?.num_treadles && (
                    <span className="text-xs text-muted-foreground">(value overwritten)</span>
                  )}
                </dd>
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
            </div>

            <div className="space-y-3 border-t pt-4">
              <h2 className="text-base font-semibold">Features</h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {(
                  [
                    ["Threading diagram", project.has_threading],
                    ["Tie-up grid", project.has_tieup],
                    ["Treadle-tracking", project.has_treadling],
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
                <dt className="text-muted-foreground">Lift-tracking</dt>
                <dd>
                  {project.has_liftplan ? (
                    <span className="text-foreground">
                      ✓ Available
                      {project.liftplan_generated && (
                        <span className="ml-1.5 text-xs text-muted-foreground">(computed)</span>
                      )}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">✗ Not in file</span>
                  )}
                </dd>
              </dl>

              {!project.has_liftplan && project.has_treadling && project.has_tieup && (
                <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm dark:border-amber-800 dark:bg-amber-950">
                  <p className="font-medium text-amber-900 dark:text-amber-100">Lift plan not in file</p>
                  <p className="mt-0.5 text-amber-800 dark:text-amber-200 text-xs">
                    This WIF has treadling and tie-up data. A lift plan can be computed algorithmically and added to the project.
                  </p>
                  {generateMutation.isError && (
                    <p className="mt-1 text-xs text-destructive">
                      {generateMutation.error instanceof Error ? generateMutation.error.message : "Generation failed"}
                    </p>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-2"
                    onClick={() => generateMutation.mutate()}
                    disabled={generateMutation.isPending}
                  >
                    {generateMutation.isPending ? "Generating…" : "Generate lift plan"}
                  </Button>
                </div>
              )}

              {/* Treadle metadata mismatch — offer override */}
              {project.effective_num_treadles != null &&
                project.num_treadles != null &&
                project.effective_num_treadles !== project.num_treadles && (
                <div className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2.5 text-sm dark:border-stone-700 dark:bg-stone-900/30">
                  <p className="font-medium text-stone-700 dark:text-stone-300">Treadle metadata mismatch</p>
                  <p className="mt-0.5 text-stone-600 dark:text-stone-400 text-xs">
                    [WEAVING] declares {project.num_treadles} treadles but the treadling data only uses {project.effective_num_treadles}.
                    {project.metadata_overrides?.num_treadles
                      ? ` (overridden from ${project.metadata_overrides.num_treadles.original})`
                      : " Override to fix loom compatibility checks and correct the exported file."}
                  </p>
                  {overrideMutation.isError && overrideMutation.variables?.field === "num_treadles" && (
                    <p className="mt-1 text-xs text-destructive">
                      {overrideMutation.error instanceof Error ? overrideMutation.error.message : "Override failed"}
                    </p>
                  )}
                  {!project.metadata_overrides?.num_treadles && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={() => overrideMutation.mutate({ field: "num_treadles", value: project.effective_num_treadles! })}
                      disabled={overrideMutation.isPending}
                    >
                      {overrideMutation.isPending && overrideMutation.variables?.field === "num_treadles"
                        ? "Overriding…"
                        : `Set treadles to ${project.effective_num_treadles}`}
                    </Button>
                  )}
                </div>
              )}

              {/* Shaft metadata mismatch — offer override */}
              {project.effective_num_shafts != null &&
                project.num_shafts != null &&
                project.effective_num_shafts !== project.num_shafts && (
                <div className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2.5 text-sm dark:border-stone-700 dark:bg-stone-900/30">
                  <p className="font-medium text-stone-700 dark:text-stone-300">Shaft metadata mismatch</p>
                  <p className="mt-0.5 text-stone-600 dark:text-stone-400 text-xs">
                    [WEAVING] declares {project.num_shafts} shafts but the lift plan only uses {project.effective_num_shafts}.
                    {project.metadata_overrides?.num_shafts
                      ? ` (overridden from ${project.metadata_overrides.num_shafts.original})`
                      : " Override to fix loom compatibility checks and correct the exported file."}
                  </p>
                  {overrideMutation.isError && overrideMutation.variables?.field === "num_shafts" && (
                    <p className="mt-1 text-xs text-destructive">
                      {overrideMutation.error instanceof Error ? overrideMutation.error.message : "Override failed"}
                    </p>
                  )}
                  {!project.metadata_overrides?.num_shafts && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={() => overrideMutation.mutate({ field: "num_shafts", value: project.effective_num_shafts! })}
                      disabled={overrideMutation.isPending}
                    >
                      {overrideMutation.isPending && overrideMutation.variables?.field === "num_shafts"
                        ? "Overriding…"
                        : `Set shafts to ${project.effective_num_shafts}`}
                    </Button>
                  )}
                </div>
              )}
            </div>

            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold">Activities</h2>
                <div className="flex items-center gap-3">
                  <Button size="sm" onClick={() => setShowCreateActivity(true)}>New activity</Button>
                  <Link to="/activities" className="text-xs text-muted-foreground hover:text-foreground">
                    All activities →
                  </Link>
                </div>
              </div>
              <ActivitySummaryList activities={projectActivities} />
            </div>
          </div>

          {/* Right column: Preview */}
          <div>
            <h2 className="text-base font-semibold mb-3">Design Preview</h2>
            {project.has_preview ? (
              <div className="overflow-auto rounded-lg border bg-white p-2">
                <AuthedImage
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

        {/* Danger zone */}
        <div className="border-t pt-4">
          <button
            type="button"
            onClick={() => setShowDangerZone((v) => !v)}
            className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-destructive transition-colors"
          >
            <span>Danger zone</span>
            <span>{showDangerZone ? "▲" : "▼"}</span>
          </button>
          {showDangerZone && (
            <div className="mt-3 rounded-md border border-destructive/30 p-4 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium">Delete project</p>
                <p className="text-xs text-muted-foreground mt-0.5">Permanently removes this project and its WIF file. Activities are not deleted.</p>
              </div>
              <div className="flex gap-2 shrink-0">
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
          )}
        </div>

      {showCreateActivity && (
        <CreateActivityModal
          defaultProjectId={id}
          onSuccess={(newId) => {
            setShowCreateActivity(false);
            queryClient.invalidateQueries({ queryKey: ["activities", { projectId: id }] });
            queryClient.invalidateQueries({ queryKey: ["activities"] });
            navigate(`/activities/${newId}`);
          }}
          onClose={() => setShowCreateActivity(false)}
        />
      )}
    </div>
  );
}
