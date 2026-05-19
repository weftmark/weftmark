import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listDrafts } from "@/api/drafts";
import { listProjects } from "@/api/projects";
import { DraftCard } from "@/components/drafts/DraftCard";
import { UploadWifModal } from "@/components/drafts/UploadWifModal";
import { Button } from "@/components/ui/button";

export function DraftsPage() {
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const { data: drafts = [], isLoading, error } = useQuery({
    queryKey: ["drafts", { includeArchived: showArchived }],
    queryFn: () => listDrafts(showArchived),
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const projectCountsByDraft = projects.reduce<Record<string, { active: number; planning: number; completed: number; abandoned: number }>>(
    (acc, a) => {
      const did = a.draft_id;
      if (!acc[did]) acc[did] = { active: 0, planning: 0, completed: 0, abandoned: 0 };
      if (a.status === "active" && !!a.loom_id) acc[did].active++;
      else if (a.status === "active" && !a.loom_id) acc[did].planning++;
      else if (a.status === "completed") acc[did].completed++;
      else if (a.status === "abandoned") acc[did].abandoned++;
      return acc;
    },
    {},
  );

  const handleUploadSuccess = () => {
    setShowUpload(false);
    queryClient.invalidateQueries({ queryKey: ["drafts"] });
  };

  const activeDrafts = drafts.filter((d) => !d.archived_at);
  const archivedDrafts = drafts.filter((d) => d.archived_at);

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Drafts</h1>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowArchived((v) => !v)}
            className={`text-sm transition-colors ${showArchived ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}`}
          >
            {showArchived ? "Hide archived" : "Show archived"}
          </button>
          <Button onClick={() => setShowUpload(true)}>New Draft</Button>
        </div>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading drafts…</p>}
      {error && <p className="text-sm text-destructive">Failed to load drafts.</p>}

      {!isLoading && drafts.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">
            {showArchived ? "No archived drafts." : "No drafts yet. Upload a WIF file to get started."}
          </p>
          {!showArchived && (
            <Button className="mt-4" onClick={() => setShowUpload(true)}>
              New Draft
            </Button>
          )}
        </div>
      )}

      {activeDrafts.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {activeDrafts.map((d) => (
            <DraftCard key={d.id} draft={d} projectCounts={projectCountsByDraft[d.id]} />
          ))}
        </div>
      )}

      {showArchived && archivedDrafts.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wide mb-3">Archived</h2>
          <div className="grid gap-4 sm:grid-cols-2 opacity-60">
            {archivedDrafts.map((d) => (
              <DraftCard key={d.id} draft={d} projectCounts={projectCountsByDraft[d.id]} archived />
            ))}
          </div>
        </div>
      )}

      {showUpload && (
        <UploadWifModal
          onSuccess={handleUploadSuccess}
          onClose={() => setShowUpload(false)}
        />
      )}
    </div>
  );
}
