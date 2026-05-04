import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listDrafts } from "@/api/drafts";
import { listActivities } from "@/api/activities";
import { DraftCard } from "@/components/drafts/DraftCard";
import { UploadWifModal } from "@/components/drafts/UploadWifModal";
import { Button } from "@/components/ui/button";

export function DraftsPage() {
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);

  const { data: drafts = [], isLoading, error } = useQuery({
    queryKey: ["drafts"],
    queryFn: listDrafts,
  });

  const { data: activities = [] } = useQuery({
    queryKey: ["activities"],
    queryFn: () => listActivities(),
  });

  const activityCountsByDraft = activities.reduce<Record<string, { active: number; planning: number; completed: number; abandoned: number }>>(
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

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Drafts</h1>
        <Button onClick={() => setShowUpload(true)}>New Draft</Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading drafts…</p>}
      {error && <p className="text-sm text-destructive">Failed to load drafts.</p>}

      {!isLoading && drafts.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">
            No drafts yet. Upload a WIF file to get started.
          </p>
          <Button className="mt-4" onClick={() => setShowUpload(true)}>
            New Draft
          </Button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {drafts.map((d) => (
          <DraftCard key={d.id} draft={d} activityCounts={activityCountsByDraft[d.id]} />
        ))}
      </div>

      {showUpload && (
        <UploadWifModal
          onSuccess={handleUploadSuccess}
          onClose={() => setShowUpload(false)}
        />
      )}
    </div>
  );
}
