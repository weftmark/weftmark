import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createActivity, completeActivity, abandonActivity, listActivities, ApiError, ACTIVITY_TYPE_LABELS, type ActivityType, type ActivitySummary } from "@/api/activities";
import { listProjects } from "@/api/projects";
import { listLooms, getLoom, SUPPORTED_LOOM_TYPES } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  onSuccess: (id: string) => void;
  onClose: () => void;
  defaultProjectId?: string;
}

const CM_PER_IN = 2.54;

function convertLen(value: string, toUnit: "cm" | "in"): string {
  const v = parseFloat(value);
  if (!value || isNaN(v)) return value;
  const result = toUnit === "in" ? v / CM_PER_IN : v * CM_PER_IN;
  return parseFloat(result.toFixed(2)).toString();
}

const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export function CreateActivityModal({ onSuccess, onClose, defaultProjectId }: Props) {
  const [name, setName] = useState("");
  const [projectId, setProjectId] = useState(defaultProjectId ?? "");
  const [activityType, setActivityType] = useState<ActivityType | "">("");
  const [loomId, setLoomId] = useState("");
  const [loomVersionId, setLoomVersionId] = useState("");
  const [finishedLength, setFinishedLength] = useState("");
  const [numItems, setNumItems] = useState("1");
  const [wasteBetween, setWasteBetween] = useState("");
  const [warpWaste, setWarpWaste] = useState("");
  const [lengthUnit, setLengthUnit] = useState<"cm" | "in">("cm");

  const handleUnitChange = (newUnit: "cm" | "in") => {
    setFinishedLength((v) => convertLen(v, newUnit));
    setWasteBetween((v) => convertLen(v, newUnit));
    setWarpWaste((v) => convertLen(v, newUnit));
    setLengthUnit(newUnit);
  };
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflictActivity, setConflictActivity] = useState<ActivitySummary | null>(null);

  const { data: projects = [] } = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const { data: looms = [] } = useQuery({ queryKey: ["looms"], queryFn: listLooms });
  const { data: loomDetail } = useQuery({
    queryKey: ["loom", loomId],
    queryFn: () => getLoom(loomId),
    enabled: !!loomId,
  });

  const selectedProject = projects.find((p) => p.id === projectId);
  const selectedLoom = looms.find((l) => l.id === loomId);

  // Filter activity types by what the WIF supports and loom supports
  const availableTypes: ActivityType[] = [];
  if (selectedProject) {
    if (selectedProject.has_treadling) availableTypes.push("treadle");
    if (selectedProject.has_liftplan) availableTypes.push("lift");
  }

  // Filter to types the loom also supports (if a loom is selected)
  const filteredTypes = selectedLoom
    ? availableTypes.filter((t) => {
        if (t === "treadle") return selectedLoom.supports_treadle_tracking;
        if (t === "lift") return selectedLoom.supports_lift_tracking;
        return true;
      })
    : availableTypes;

  // Auto-select type when only one option
  const effectiveType: ActivityType | "" =
    activityType ||
    (filteredTypes.length === 1 ? filteredTypes[0] : "");

  const loomVersions = loomDetail?.versions ?? [];
  const selectedVersion = loomVersions.find((v) => v.id === loomVersionId);

  const loomWasteInCurrentUnit = (allowance: string | null | undefined, wasteUnit: string): string => {
    if (!allowance) return "";
    return wasteUnit === lengthUnit ? allowance : convertLen(allowance, lengthUnit);
  };

  const handleLoomChange = (newLoomId: string) => {
    setLoomId(newLoomId);
    setLoomVersionId("");
    setActivityType("");
    setWarpWaste("");
    setConflictActivity(null);
    setError(null);
  };

  const _buildPayload = () => ({
    name: name.trim(),
    project_id: projectId,
    activity_type: effectiveType as ActivityType,
    loom_id: loomId || undefined,
    loom_version_id: loomVersionId || undefined,
    finished_length_per_item: finishedLength ? parseFloat(finishedLength) : undefined,
    num_items: parseInt(numItems, 10) || 1,
    waste_between_items: wasteBetween ? parseFloat(wasteBetween) : undefined,
    warp_waste_allowance: warpWaste ? parseFloat(warpWaste) : undefined,
    length_unit: lengthUnit,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!effectiveType) return;
    setError(null);
    setConflictActivity(null);
    setLoading(true);
    try {
      const created = await createActivity(_buildPayload());
      onSuccess(created.id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && loomId) {
        const activities = await listActivities().catch(() => []);
        const conflict = activities.find((a) => a.loom_id === loomId && a.status === "active") ?? null;
        setConflictActivity(conflict);
      } else {
        setError(err instanceof Error ? err.message : "Failed to create activity");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResolveAndCreate = async (resolve: "complete" | "abandon") => {
    if (!conflictActivity || !effectiveType) return;
    setError(null);
    setLoading(true);
    try {
      if (resolve === "complete") {
        await completeActivity(conflictActivity.id);
      } else {
        await abandonActivity(conflictActivity.id);
      }
      const created = await createActivity(_buildPayload());
      onSuccess(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create activity");
      setConflictActivity(null);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = name.trim() && projectId && !!effectiveType && !loading;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="px-6 pt-6 pb-4 border-b">
          <h2 className="text-lg font-semibold">New activity</h2>
        </div>

        <form onSubmit={handleSubmit} className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          <div>
            <label className="mb-1 block text-sm font-medium">Activity name <span className="text-destructive">*</span></label>
            <input className={f} value={name} onChange={(e) => setName(e.target.value)} placeholder="Spring towels — warp 1" required />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">WIF project <span className="text-destructive">*</span></label>
            {defaultProjectId ? (
              <p className="py-2 text-sm">{selectedProject?.name ?? "—"}</p>
            ) : (
              <select className={f} value={projectId} onChange={(e) => { setProjectId(e.target.value); setActivityType(""); }} required>
                <option value="">Select a project…</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Loom <span className="text-muted-foreground font-normal">(optional)</span></label>
            <select className={f} value={loomId} onChange={(e) => handleLoomChange(e.target.value)}>
              <option value="">No loom selected</option>
              {looms.filter((l) => SUPPORTED_LOOM_TYPES.has(l.loom_type)).map((l) => (
                <option key={l.id} value={l.id}>{l.manufacturer} {l.model_name}</option>
              ))}
            </select>
            {looms.some((l) => !SUPPORTED_LOOM_TYPES.has(l.loom_type)) && (
              <p className="mt-1 text-xs text-muted-foreground">Looms without activity tracking support are not shown.</p>
            )}
          </div>

          {selectedLoom && loomVersions.length > 1 && (
            <div>
              <label className="mb-1 block text-sm font-medium">Loom configuration</label>
              <select className={f} value={loomVersionId} onChange={(e) => {
                setLoomVersionId(e.target.value);
                const v = loomVersions.find((v) => v.id === e.target.value);
                if (v?.warp_waste_allowance) setWarpWaste(loomWasteInCurrentUnit(v.warp_waste_allowance, v.warp_waste_unit));
              }}>
                <option value="">Latest ({loomVersions.at(-1)?.name ?? `v${loomVersions.at(-1)?.version_number}`})</option>
                {loomVersions.map((v) => (
                  <option key={v.id} value={v.id}>{v.name ?? `Version ${v.version_number}`}</option>
                ))}
              </select>
            </div>
          )}

          {selectedProject && (
            <div>
              <label className="mb-1 block text-sm font-medium">Activity type <span className="text-destructive">*</span></label>
              {filteredTypes.length === 0 ? (
                <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5 text-sm">
                  {selectedLoom && availableTypes.length > 0 ? (
                    <>
                      <p className="font-medium text-destructive">Loom and project are incompatible</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        This WIF supports {availableTypes.map(t => ACTIVITY_TYPE_LABELS[t]).join(" and ")}, but the selected loom does not.
                        {availableTypes.includes("lift") && !selectedLoom.supports_lift_tracking && " The loom does not support lift tracking."}
                        {availableTypes.includes("treadle") && !selectedLoom.supports_treadle_tracking && " The loom does not support treadle tracking."}
                        {" "}Try a different loom or go to the project page to generate a lift plan.
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="font-medium text-destructive">No activity types available</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        This WIF has no treadling or lift plan data. Go to the project page to generate a lift plan if the file has tieup and treadling sections.
                      </p>
                    </>
                  )}
                </div>
              ) : filteredTypes.length === 1 ? (
                <p className="text-sm py-2">{ACTIVITY_TYPE_LABELS[filteredTypes[0]]}</p>
              ) : (
                <select className={f} value={effectiveType} onChange={(e) => setActivityType(e.target.value as ActivityType)} required>
                  <option value="">Select type…</option>
                  {filteredTypes.map((t) => (
                    <option key={t} value={t}>{ACTIVITY_TYPE_LABELS[t]}</option>
                  ))}
                </select>
              )}
            </div>
          )}

          <div className="border-t pt-4">
            <p className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Warp plan</p>
            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <label className="mb-1 block text-sm font-medium">Finished length / item</label>
                <div className="flex gap-2">
                  <input type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={finishedLength} onChange={(e) => setFinishedLength(e.target.value)} placeholder="50" />
                  <select className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={lengthUnit} onChange={(e) => handleUnitChange(e.target.value as "cm" | "in")}>
                    <option value="cm">cm</option>
                    <option value="in">in</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Number of items</label>
                <input type="number" min={1} step="1" className={f} value={numItems} onChange={(e) => setNumItems(e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-3">
              {parseInt(numItems, 10) > 1 && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Waste between items</label>
                  <div className="flex gap-1">
                    <input type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={wasteBetween} onChange={(e) => setWasteBetween(e.target.value)} placeholder="5" />
                    <span className="flex items-center rounded-md border border-input bg-muted px-2 text-sm text-muted-foreground">{lengthUnit}</span>
                  </div>
                </div>
              )}
              <div className={parseInt(numItems, 10) <= 1 ? "col-span-2" : ""}>
                <label className="mb-1 block text-sm font-medium">Loom warp waste</label>
                <div className="flex gap-1">
                  <input type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={warpWaste || loomWasteInCurrentUnit(selectedVersion?.warp_waste_allowance ?? loomDetail?.versions.at(-1)?.warp_waste_allowance, selectedVersion?.warp_waste_unit ?? loomDetail?.versions.at(-1)?.warp_waste_unit ?? "cm")} onChange={(e) => setWarpWaste(e.target.value)} placeholder="30" />
                  <span className="flex items-center rounded-md border border-input bg-muted px-2 text-sm text-muted-foreground">{lengthUnit}</span>
                </div>
              </div>
            </div>
          </div>

          {conflictActivity && (
            <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-700 px-3 py-3 text-sm space-y-2">
              <p className="font-medium text-amber-900 dark:text-amber-200">
                This loom has an active activity: <span className="font-semibold">{conflictActivity.name}</span>
              </p>
              <p className="text-amber-800 dark:text-amber-300 text-xs">
                Mark it as completed or abandon it to start this new activity, or choose a different loom.
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button type="button" size="sm" onClick={() => handleResolveAndCreate("complete")} disabled={loading}>
                  {loading ? "Working…" : "Mark completed & continue"}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => handleResolveAndCreate("abandon")} disabled={loading}>
                  {loading ? "Working…" : "Abandon & continue"}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => handleLoomChange("")} disabled={loading}>
                  Clear loom
                </Button>
              </div>
            </div>
          )}
          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </form>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {loading ? "Creating…" : "Start activity"}
          </Button>
        </div>
      </div>
    </div>
  );
}
