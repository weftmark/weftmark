import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { assignLoom } from "@/api/projects";
import { listLooms, getLoom, SUPPORTED_LOOM_TYPES } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  projectId: string;
  projectType?: string;
  draftNumTreadles?: number | null;
  draftNumShafts?: number | null;
  draftEffectiveNumTreadles?: number | null;
  draftEffectiveNumShafts?: number | null;
  onSuccess: () => void;
  onClose: () => void;
}

const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export function AssignLoomModal({ projectId, projectType, draftNumTreadles, draftNumShafts, draftEffectiveNumTreadles, draftEffectiveNumShafts, onSuccess, onClose }: Props) {
  const [loomId, setLoomId] = useState("");
  const [loomVersionId, setLoomVersionId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: looms = [] } = useQuery({ queryKey: ["looms"], queryFn: () => listLooms() });
  const { data: loomDetail } = useQuery({
    queryKey: ["loom", loomId],
    queryFn: () => getLoom(loomId),
    enabled: !!loomId,
  });

  const loomVersions = loomDetail?.versions ?? [];
  const selectedLoom = looms.find((l) => l.id === loomId);

  const loomTreadles = selectedLoom?.current_version?.num_treadles ?? null;
  const loomShafts = selectedLoom?.current_version?.num_shafts ?? null;

  const effectiveTreadles = draftEffectiveNumTreadles ?? draftNumTreadles ?? null;
  const effectiveShafts = draftEffectiveNumShafts ?? draftNumShafts ?? null;

  const treadleMismatch =
    !!selectedLoom &&
    (projectType === "treadle" || !projectType) &&
    (effectiveTreadles ?? 0) > 0 &&
    (loomTreadles ?? 0) > 0 &&
    (effectiveTreadles ?? 0) > (loomTreadles ?? 0);

  const shaftMismatch =
    !!selectedLoom &&
    (projectType === "lift" || !projectType) &&
    (effectiveShafts ?? 0) > 0 &&
    (loomShafts ?? 0) > 0 &&
    (effectiveShafts ?? 0) > (loomShafts ?? 0);

  const treadleMetaMismatch =
    draftNumTreadles != null &&
    draftEffectiveNumTreadles != null &&
    draftNumTreadles !== draftEffectiveNumTreadles;

  const shaftMetaMismatch =
    draftNumShafts != null &&
    draftEffectiveNumShafts != null &&
    draftNumShafts !== draftEffectiveNumShafts;

  const doAssign = async () => {
    setError(null);
    setLoading(true);
    try {
      await assignLoom(projectId, loomId, loomVersionId || undefined);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to assign loom");
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
            <select className={f} value={loomId} onChange={(e) => { setLoomId(e.target.value); setLoomVersionId(""); setError(null); }}>
              <option value="">Select a loom…</option>
              {looms.filter((l) => SUPPORTED_LOOM_TYPES.has(l.loom_type)).map((l) => (
                <option key={l.id} value={l.id}>{l.manufacturer} {l.model_name}</option>
              ))}
            </select>
            {looms.some((l) => !SUPPORTED_LOOM_TYPES.has(l.loom_type)) && (
              <p className="mt-1 text-xs text-muted-foreground">Looms without project tracking support are not shown.</p>
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

          {(treadleMismatch || shaftMismatch) && selectedLoom && (
            <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2.5 text-sm">
              <p className="font-medium text-copper-on-subtle">
                {treadleMismatch ? "Treadle count mismatch" : "Shaft count mismatch"}
              </p>
              <p className="mt-0.5 text-xs text-copper-on-subtle">
                {treadleMismatch
                  ? `This design uses up to ${effectiveTreadles} treadles, but ${selectedLoom.manufacturer} ${selectedLoom.model_name} only has ${loomTreadles}. Treadle positions beyond ${loomTreadles} cannot be pressed.`
                  : `This design uses up to ${effectiveShafts} shafts, but ${selectedLoom.manufacturer} ${selectedLoom.model_name} only has ${loomShafts}. Shaft positions beyond ${loomShafts} cannot be raised.`}
              </p>
            </div>
          )}

          {(treadleMetaMismatch || shaftMetaMismatch) && !treadleMismatch && !shaftMismatch && (
            <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
              <p className="font-medium text-foreground">WIF metadata note</p>
              <p className="mt-0.5 text-xs text-subdued">
                {treadleMetaMismatch
                  ? `The WIF file declares ${draftNumTreadles} treadles in metadata, but the treadling data only uses ${draftEffectiveNumTreadles}. Loom compatibility uses the actual count (${draftEffectiveNumTreadles}). You can fix the declared count in your design software.`
                  : `The WIF file declares ${draftNumShafts} shafts in metadata, but the lift plan only uses ${draftEffectiveNumShafts}. Loom compatibility uses the actual count (${draftEffectiveNumShafts}). You can fix the declared count in your design software.`}
              </p>
            </div>
          )}

          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button onClick={doAssign} disabled={!loomId || loading}>
            {loading ? "Assigning…" : "Assign loom"}
          </Button>
        </div>
      </div>
    </div>
  );
}
