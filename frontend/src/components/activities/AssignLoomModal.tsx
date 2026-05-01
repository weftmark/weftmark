import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { assignLoom, completeActivity, abandonActivity, ApiError, type ActivitySummary } from "@/api/activities";
import { listLooms, getLoom, SUPPORTED_LOOM_TYPES } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  activityId: string;
  activeActivities: ActivitySummary[];
  onSuccess: () => void;
  onClose: () => void;
}

const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export function AssignLoomModal({ activityId, activeActivities, onSuccess, onClose }: Props) {
  const [loomId, setLoomId] = useState("");
  const [loomVersionId, setLoomVersionId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflictActivity, setConflictActivity] = useState<ActivitySummary | null>(null);

  const { data: looms = [] } = useQuery({ queryKey: ["looms"], queryFn: listLooms });
  const { data: loomDetail } = useQuery({
    queryKey: ["loom", loomId],
    queryFn: () => getLoom(loomId),
    enabled: !!loomId,
  });

  const loomVersions = loomDetail?.versions ?? [];

  const handleLoomChange = (newLoomId: string) => {
    setLoomId(newLoomId);
    setLoomVersionId("");
    setError(null);
    setConflictActivity(null);
    if (newLoomId) {
      const conflict = activeActivities.find((a) => a.loom_id === newLoomId && a.id !== activityId) ?? null;
      setConflictActivity(conflict);
    }
  };

  const doAssign = async () => {
    setError(null);
    setLoading(true);
    try {
      await assignLoom(activityId, loomId, loomVersionId || undefined);
      onSuccess();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const conflict = activeActivities.find((a) => a.loom_id === loomId && a.id !== activityId) ?? null;
        setConflictActivity(conflict);
      } else {
        setError(err instanceof Error ? err.message : "Failed to assign loom");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResolveAndAssign = async (resolve: "complete" | "abandon") => {
    if (!conflictActivity) return;
    setError(null);
    setLoading(true);
    try {
      if (resolve === "complete") {
        await completeActivity(conflictActivity.id);
      } else {
        await abandonActivity(conflictActivity.id);
      }
      await assignLoom(activityId, loomId, loomVersionId || undefined);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign loom");
      setConflictActivity(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-lg border bg-background shadow-lg">
        <div className="px-6 pt-6 pb-4 border-b">
          <h2 className="text-lg font-semibold">Assign to loom</h2>
        </div>

        <div className="px-6 py-4 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Loom <span className="text-destructive">*</span></label>
            <select className={f} value={loomId} onChange={(e) => handleLoomChange(e.target.value)}>
              <option value="">Select a loom…</option>
              {looms.filter((l) => SUPPORTED_LOOM_TYPES.has(l.loom_type)).map((l) => (
                <option key={l.id} value={l.id}>{l.manufacturer} {l.model_name}</option>
              ))}
            </select>
            {looms.some((l) => !SUPPORTED_LOOM_TYPES.has(l.loom_type)) && (
              <p className="mt-1 text-xs text-muted-foreground">Looms without activity tracking support are not shown.</p>
            )}
          </div>

          {loomVersions.length > 1 && (
            <div>
              <label className="mb-1 block text-sm font-medium">Loom configuration</label>
              <select className={f} value={loomVersionId} onChange={(e) => setLoomVersionId(e.target.value)}>
                <option value="">Latest ({loomVersions.at(-1)?.name ?? `v${loomVersions.at(-1)?.version_number}`})</option>
                {loomVersions.map((v) => (
                  <option key={v.id} value={v.id}>{v.name ?? `Version ${v.version_number}`}</option>
                ))}
              </select>
            </div>
          )}

          {conflictActivity && (
            <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700 px-3 py-3 text-sm space-y-2">
              <p className="font-medium text-amber-900 dark:text-amber-200">
                This loom has an active activity: <span className="font-semibold">{conflictActivity.name}</span>
              </p>
              <p className="text-amber-800 dark:text-amber-300 text-xs">
                Mark it as completed or abandon it to assign this loom, or choose a different loom.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button type="button" size="sm" onClick={() => handleResolveAndAssign("complete")} disabled={loading}>
                  {loading ? "Working…" : "Mark completed & assign"}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => handleResolveAndAssign("abandon")} disabled={loading}>
                  {loading ? "Working…" : "Abandon & assign"}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => handleLoomChange("")} disabled={loading}>
                  Clear loom
                </Button>
              </div>
            </div>
          )}

          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button onClick={doAssign} disabled={!loomId || !!conflictActivity || loading}>
            {loading ? "Assigning…" : "Assign loom"}
          </Button>
        </div>
      </div>
    </div>
  );
}
