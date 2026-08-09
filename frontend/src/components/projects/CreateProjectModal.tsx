import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createProject, completeProject, abandonProject, listProjects, ApiError, PROJECT_TYPE_LABELS, type ProjectType, type ProjectSummary } from "@/api/projects";
import { listDrafts, type Draft } from "@/api/drafts";
import { listLooms, getLoom, SUPPORTED_LOOM_TYPES, type Loom, type LoomVersion } from "@/api/looms";
import { Button } from "@/components/ui/button";
import { TagInput } from "@/components/ui/TagInput";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, convertLength, formatLength } from "@/lib/units";
import { useEscapeKey } from "@/hooks/useEscapeKey";

interface Props {
  readonly onSuccess: (id: string) => void;
  readonly onClose: () => void;
  readonly defaultDraftId?: string;
}

const CM_PER_IN = 2.54;

function convertLen(value: string, toUnit: "cm" | "in"): string {
  const v = Number.parseFloat(value);
  if (!value || Number.isNaN(v)) return value;
  const result = toUnit === "in" ? v / CM_PER_IN : v * CM_PER_IN;
  return Number.parseFloat(result.toFixed(2)).toString();
}

const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

function loomWasteInUnit(allowance: string | null | undefined, wasteUnit: string, lengthUnit: "cm" | "in"): string {
  if (!allowance) return "";
  return wasteUnit === lengthUnit ? allowance : convertLen(allowance, lengthUnit);
}

function computeAvailableProjectTypes(selectedDraft: Draft | undefined): ProjectType[] {
  const types: ProjectType[] = [];
  if (selectedDraft?.has_treadling) types.push("treadle");
  if (selectedDraft?.has_liftplan) types.push("lift");
  return types;
}

function filterTypesByLoom(availableTypes: ProjectType[], selectedLoom: Loom | undefined): ProjectType[] {
  if (!selectedLoom) return availableTypes;
  return availableTypes.filter((t) => {
    if (t === "treadle") return selectedLoom.supports_treadle_tracking;
    if (t === "lift") return selectedLoom.supports_lift_tracking;
    return true;
  });
}

function computeMismatches(
  selectedLoom: Loom | undefined,
  effectiveType: ProjectType | "",
  availableTypes: ProjectType[],
  effectiveTreadles: number | null,
  loomTreadles: number | null,
  effectiveShafts: number | null,
  loomShafts: number | null,
) {
  const treadleMismatch =
    !!selectedLoom &&
    (effectiveType === "treadle" || (!effectiveType && availableTypes.includes("treadle"))) &&
    (effectiveTreadles ?? 0) > 0 &&
    (loomTreadles ?? 0) > 0 &&
    (effectiveTreadles ?? 0) > (loomTreadles ?? 0);

  const shaftMismatch =
    !!selectedLoom &&
    (effectiveType === "lift" || (!effectiveType && availableTypes.includes("lift"))) &&
    (effectiveShafts ?? 0) > 0 &&
    (loomShafts ?? 0) > 0 &&
    (effectiveShafts ?? 0) > (loomShafts ?? 0);

  return { treadleMismatch, shaftMismatch };
}

function computeFinishedLengthInfo(
  finishedLength: string,
  lengthUnit: "cm" | "in",
  warpLengthDefaultCm: number | null,
) {
  const finishedLengthCm =
    finishedLength !== "" && !Number.isNaN(Number.parseFloat(finishedLength))
      ? convertLength(Number.parseFloat(finishedLength), lengthUnit, "cm")
      : null;
  const warpLengthDefaultLabel =
    warpLengthDefaultCm != null ? formatLength(convertLength(warpLengthDefaultCm, "cm", lengthUnit), lengthUnit) : null;
  const deviatesFromDefault =
    warpLengthDefaultCm != null && finishedLengthCm != null && Math.abs(finishedLengthCm - warpLengthDefaultCm) > 0.5;
  const matchesDefault =
    warpLengthDefaultCm != null && finishedLengthCm != null && Math.abs(finishedLengthCm - warpLengthDefaultCm) <= 0.5;
  return { warpLengthDefaultLabel, deviatesFromDefault, matchesDefault };
}

function ProjectTypeSection({
  filteredTypes,
  availableTypes,
  selectedLoom,
  effectiveType,
  setProjectType,
}: {
  readonly filteredTypes: ProjectType[];
  readonly availableTypes: ProjectType[];
  readonly selectedLoom: Loom | undefined;
  readonly effectiveType: ProjectType | "";
  readonly setProjectType: (t: ProjectType) => void;
}) {
  if (filteredTypes.length === 0) {
    return (
      <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5 text-sm">
        {selectedLoom && availableTypes.length > 0 ? (
          <>
            <p className="font-medium text-destructive">Loom and draft are incompatible</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              This WIF supports {availableTypes.map((t) => PROJECT_TYPE_LABELS[t]).join(" and ")}, but the selected loom does not.
              {availableTypes.includes("lift") && !selectedLoom.supports_lift_tracking && " The loom does not support lift tracking."}
              {availableTypes.includes("treadle") && !selectedLoom.supports_treadle_tracking && " The loom does not support treadle tracking."}
              {" "}Try a different loom or go to the draft page to generate a lift plan.
            </p>
          </>
        ) : (
          <>
            <p className="font-medium text-destructive">No project types available</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              This WIF has no treadling or lift plan data. Go to the draft page to generate a lift plan if the file has tieup and treadling sections.
            </p>
          </>
        )}
      </div>
    );
  }
  if (filteredTypes.length === 1) {
    return <p className="text-sm py-2">{PROJECT_TYPE_LABELS[filteredTypes[0]]}</p>;
  }
  return (
    <select id="project-type" className={f} value={effectiveType} onChange={(e) => setProjectType(e.target.value as ProjectType)} required>
      <option value="">Select type…</option>
      {filteredTypes.map((t) => (
        <option key={t} value={t}>{PROJECT_TYPE_LABELS[t]}</option>
      ))}
    </select>
  );
}

function NoLoomSelectedNotice() {
  return (
    <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
      <p className="font-medium text-foreground">No loom selected — preview mode</p>
      <p className="mt-0.5 text-xs text-subdued">
        This project will not be linked to equipment. Select a project type below to create a standalone tracking preview. You can create a separate project to preview the other type.
      </p>
    </div>
  );
}

function LoomVersionSelector({
  loomVersions,
  loomVersionId,
  onChange,
}: {
  readonly loomVersions: LoomVersion[];
  readonly loomVersionId: string;
  readonly onChange: (versionId: string) => void;
}) {
  return (
    <div>
      <label htmlFor="project-loom-version" className="mb-1 block text-sm font-medium">Loom configuration</label>
      <select id="project-loom-version" className={f} value={loomVersionId} onChange={(e) => onChange(e.target.value)}>
        <option value="">Latest ({loomVersions.at(-1)?.name ?? `v${loomVersions.at(-1)?.version_number}`})</option>
        {loomVersions.map((v) => (
          <option key={v.id} value={v.id}>{v.name ?? `Version ${v.version_number}`}</option>
        ))}
      </select>
    </div>
  );
}

function CompatibilityMismatchNotice({
  treadleMismatch,
  shaftMismatch,
  selectedLoom,
  effectiveTreadles,
  loomTreadles,
  effectiveShafts,
  loomShafts,
}: {
  readonly treadleMismatch: boolean;
  readonly shaftMismatch: boolean;
  readonly selectedLoom: Loom | undefined;
  readonly effectiveTreadles: number | null;
  readonly loomTreadles: number | null;
  readonly effectiveShafts: number | null;
  readonly loomShafts: number | null;
}) {
  if (!(treadleMismatch || shaftMismatch) || !selectedLoom) return null;
  return (
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
  );
}

function MetadataMismatchNotice({
  treadleMetaMismatch,
  shaftMetaMismatch,
  treadleMismatch,
  shaftMismatch,
  selectedDraft,
}: {
  readonly treadleMetaMismatch: boolean;
  readonly shaftMetaMismatch: boolean;
  readonly treadleMismatch: boolean;
  readonly shaftMismatch: boolean;
  readonly selectedDraft: Draft | undefined;
}) {
  if (!(treadleMetaMismatch || shaftMetaMismatch) || treadleMismatch || shaftMismatch || !selectedDraft) return null;
  return (
    <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
      <p className="font-medium text-foreground">WIF metadata note</p>
      <p className="mt-0.5 text-xs text-subdued">
        {treadleMetaMismatch
          ? `The WIF file declares ${selectedDraft.num_treadles} treadles in metadata, but the treadling data only uses ${selectedDraft.effective_num_treadles}. Loom compatibility uses the actual count (${selectedDraft.effective_num_treadles}). You can fix the declared count in your design software.`
          : `The WIF file declares ${selectedDraft.num_shafts} shafts in metadata, but the lift plan only uses ${selectedDraft.effective_num_shafts}. Loom compatibility uses the actual count (${selectedDraft.effective_num_shafts}). You can fix the declared count in your design software.`}
      </p>
    </div>
  );
}

function WarpPlanFields({
  selectedDraft,
  draftHasWarpLength,
  finishedLength,
  setFinishedLength,
  lengthUnit,
  onUnitChange,
  finishedLengthDeviatesFromDefault,
  warpLengthDefaultLabel,
  finishedLengthMatchesDefault,
  numItems,
  setNumItems,
  wasteBetween,
  setWasteBetween,
  warpWaste,
  setWarpWaste,
  warpWasteInputValue,
}: {
  readonly selectedDraft: Draft | undefined;
  readonly draftHasWarpLength: boolean;
  readonly finishedLength: string;
  readonly setFinishedLength: (v: string) => void;
  readonly lengthUnit: "cm" | "in";
  readonly onUnitChange: (u: "cm" | "in") => void;
  readonly finishedLengthDeviatesFromDefault: boolean;
  readonly warpLengthDefaultLabel: string | null;
  readonly finishedLengthMatchesDefault: boolean;
  readonly numItems: string;
  readonly setNumItems: (v: string) => void;
  readonly wasteBetween: string;
  readonly setWasteBetween: (v: string) => void;
  readonly warpWaste: string;
  readonly setWarpWaste: (v: string) => void;
  readonly warpWasteInputValue: string;
}) {
  const numItemsInt = Number.parseInt(numItems, 10);
  return (
    <div className="border-t pt-4">
      <p className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">Warp plan</p>
      <p className="mb-3 text-xs text-muted-foreground">Warp plan tracking is not yet available. These fields are coming in a future update.</p>

      {selectedDraft && !draftHasWarpLength && (
        <div className="mb-3 rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
          <p className="font-medium text-foreground">Warp length not set</p>
          <p className="mt-0.5 text-xs text-subdued">
            Set the warp length on the draft page to enable warp waste and spacing calculations.
          </p>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <label htmlFor="project-finished-length" className="mb-1 block text-sm font-medium">Finished length / item</label>
          <div className="flex gap-2">
            <input
              id="project-finished-length"
              type="number"
              min={0}
              step="0.1"
              className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={finishedLength}
              onChange={(e) => setFinishedLength(e.target.value)}
              placeholder="50"
            />
            <select
              className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={lengthUnit}
              onChange={(e) => onUnitChange(e.target.value as "cm" | "in")}
            >
              <option value="cm">cm</option>
              <option value="in">in</option>
            </select>
          </div>
          {finishedLengthDeviatesFromDefault && (
            <p className="mt-1 text-xs text-copper-on-subtle">
              Changed from WIF warp length ({warpLengthDefaultLabel})
            </p>
          )}
          {finishedLengthMatchesDefault && (
            <p className="mt-1 text-xs text-muted-foreground">Pre-filled from WIF warp length</p>
          )}
        </div>
        <div>
          <label htmlFor="project-num-items" className="mb-1 block text-sm font-medium">Number of items</label>
          <input id="project-num-items" type="number" min={1} step="1" className={f} value={numItems} onChange={(e) => setNumItems(e.target.value)} />
        </div>
      </div>

      {draftHasWarpLength && (
        <div className="grid grid-cols-2 gap-3 mt-3">
          {numItemsInt > 1 && (
            <div>
              <label htmlFor="project-waste-between" className="mb-1 block text-sm font-medium">Waste between items</label>
              <div className="flex gap-1">
                <input id="project-waste-between" type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={wasteBetween} onChange={(e) => setWasteBetween(e.target.value)} placeholder="5" />
                <span className="flex items-center rounded-md border border-input bg-muted px-2 text-sm text-muted-foreground">{lengthUnit}</span>
              </div>
            </div>
          )}
          <div className={numItemsInt <= 1 ? "col-span-2" : ""}>
            <label htmlFor="project-loom-warp-waste" className="mb-1 block text-sm font-medium">Loom warp waste</label>
            <div className="flex gap-1">
              <input id="project-loom-warp-waste" type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={warpWaste || warpWasteInputValue} onChange={(e) => setWarpWaste(e.target.value)} placeholder="30" />
              <span className="flex items-center rounded-md border border-input bg-muted px-2 text-sm text-muted-foreground">{lengthUnit}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function LoomConflictNotice({
  conflictProject,
  loading,
  onResolve,
  onClearLoom,
}: {
  readonly conflictProject: ProjectSummary;
  readonly loading: boolean;
  readonly onResolve: (resolve: "complete" | "abandon") => void;
  readonly onClearLoom: () => void;
}) {
  return (
    <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-3 text-sm space-y-2">
      <p className="font-medium text-copper-on-subtle">
        This loom has an active project: <span className="font-semibold">{conflictProject.name}</span>
      </p>
      <p className="text-copper-on-subtle text-xs">
        Mark it as completed or abandon it to start this new project, or choose a different loom.
      </p>
      <div className="flex flex-wrap gap-2 pt-1">
        <Button type="button" size="sm" onClick={() => onResolve("complete")} disabled={loading}>
          {loading ? "Working…" : "Mark completed & continue"}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => onResolve("abandon")} disabled={loading}>
          {loading ? "Working…" : "Abandon & continue"}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onClearLoom} disabled={loading}>
          Clear loom
        </Button>
      </div>
    </div>
  );
}

export function CreateProjectModal({ onSuccess, onClose, defaultDraftId }: Props) {
  useEscapeKey(onClose);
  const { user } = useAuthContext();
  const [name, setName] = useState("");
  const [draftId, setDraftId] = useState(defaultDraftId ?? "");
  const [projectType, setProjectType] = useState<ProjectType | "">("");
  const [loomId, setLoomId] = useState("");
  const [loomVersionId, setLoomVersionId] = useState("");
  const [finishedLength, setFinishedLength] = useState("");
  const [numItems, setNumItems] = useState("1");
  const [wasteBetween, setWasteBetween] = useState("");
  const [warpWaste, setWarpWaste] = useState("");
  const [lengthUnit, setLengthUnit] = useState<"cm" | "in">(
    measurementSystemToUnit(user?.measurement_system ?? "metric")
  );
  // Track previous draft ID to detect when draft selection changes.
  const [prevDraftId, setPrevDraftId] = useState<string | undefined>(undefined);

  const handleUnitChange = (newUnit: "cm" | "in") => {
    setFinishedLength((v) => convertLen(v, newUnit));
    setWasteBetween((v) => convertLen(v, newUnit));
    setWarpWaste((v) => convertLen(v, newUnit));
    setLengthUnit(newUnit);
  };
  const [tags, setTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflictProject, setConflictProject] = useState<ProjectSummary | null>(null);

  const { data: drafts = [] } = useQuery({ queryKey: ["drafts"], queryFn: () => listDrafts() });
  const { data: looms = [] } = useQuery({ queryKey: ["looms"], queryFn: () => listLooms() });
  const { data: loomDetail } = useQuery({
    queryKey: ["loom", loomId],
    queryFn: () => getLoom(loomId),
    enabled: !!loomId,
  });

  const selectedDraft = drafts.find((d) => d.id === draftId);
  const selectedLoom = looms.find((l) => l.id === loomId);

  // Pre-populate finished length when draft selection changes (setState during render — React-approved).
  const warpLengthDefaultCm = selectedDraft?.warp_length_cm ?? null;
  if (selectedDraft?.id !== prevDraftId) {
    setPrevDraftId(selectedDraft?.id);
    if (selectedDraft?.warp_length_cm != null) {
      const val = convertLength(selectedDraft.warp_length_cm, "cm", lengthUnit);
      setFinishedLength(Number.parseFloat(val.toFixed(1)).toString());
    } else {
      setFinishedLength("");
    }
  }

  // Filter project types by what the WIF supports and loom supports
  const availableTypes = computeAvailableProjectTypes(selectedDraft);

  // Filter to types the loom also supports (if a loom is selected)
  const filteredTypes = filterTypesByLoom(availableTypes, selectedLoom);

  // Auto-select type when only one option
  const effectiveType: ProjectType | "" =
    projectType ||
    (filteredTypes.length === 1 ? filteredTypes[0] : "");

  const loomVersions = loomDetail?.versions ?? [];
  const selectedVersion = loomVersions.find((v) => v.id === loomVersionId);

  const loomTreadles = selectedLoom?.current_version?.num_treadles ?? null;
  const loomShafts = selectedLoom?.current_version?.num_shafts ?? null;

  // Use effective counts (from actual treadling data) for compatibility; fall back to declared
  const effectiveTreadles = selectedDraft?.effective_num_treadles ?? selectedDraft?.num_treadles ?? null;
  const effectiveShafts = selectedDraft?.effective_num_shafts ?? selectedDraft?.num_shafts ?? null;

  const { treadleMismatch, shaftMismatch } = computeMismatches(
    selectedLoom,
    effectiveType,
    availableTypes,
    effectiveTreadles,
    loomTreadles,
    effectiveShafts,
    loomShafts,
  );

  // Informational: declared metadata doesn't match actual usage
  const treadleMetaMismatch =
    selectedDraft?.num_treadles != null &&
    selectedDraft?.effective_num_treadles != null &&
    selectedDraft.num_treadles !== selectedDraft.effective_num_treadles;

  const shaftMetaMismatch =
    selectedDraft?.num_shafts != null &&
    selectedDraft?.effective_num_shafts != null &&
    selectedDraft.num_shafts !== selectedDraft.effective_num_shafts;

  const draftHasWarpLength = selectedDraft?.warp_length_cm != null;
  const { warpLengthDefaultLabel, deviatesFromDefault: finishedLengthDeviatesFromDefault, matchesDefault: finishedLengthMatchesDefault } =
    computeFinishedLengthInfo(finishedLength, lengthUnit, warpLengthDefaultCm);

  const handleLoomChange = (newLoomId: string) => {
    setLoomId(newLoomId);
    setLoomVersionId("");
    setProjectType("");
    setWarpWaste("");
    setConflictProject(null);
    setError(null);
  };

  const _buildPayload = () => ({
    name: name.trim(),
    draft_id: draftId,
    project_type: effectiveType as ProjectType,
    loom_id: loomId || undefined,
    loom_version_id: loomVersionId || undefined,
    finished_length_per_item: finishedLength ? Number.parseFloat(finishedLength) : undefined,
    num_items: Number.parseInt(numItems, 10) || 1,
    waste_between_items: wasteBetween ? Number.parseFloat(wasteBetween) : undefined,
    warp_waste_allowance: warpWaste ? Number.parseFloat(warpWaste) : undefined,
    length_unit: lengthUnit,
    tags: tags.length ? tags : undefined,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!effectiveType) return;
    setError(null);
    setConflictProject(null);
    setLoading(true);
    try {
      const created = await createProject(_buildPayload());
      onSuccess(created.id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && loomId) {
        const projects = await listProjects().catch(() => []);
        const conflict = projects.find((p) => p.loom_id === loomId && p.status === "active") ?? null;
        setConflictProject(conflict);
      } else {
        setError(err instanceof Error ? err.message : "Failed to create project");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResolveAndCreate = async (resolve: "complete" | "abandon") => {
    if (!conflictProject || !effectiveType) return;
    setError(null);
    setLoading(true);
    try {
      if (resolve === "complete") {
        await completeProject(conflictProject.id);
      } else {
        await abandonProject(conflictProject.id);
      }
      const created = await createProject(_buildPayload());
      onSuccess(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
      setConflictProject(null);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = name.trim() && draftId && !!effectiveType && !loading;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="px-6 pt-6 pb-4 border-b">
          <h2 className="text-lg font-semibold">New project</h2>
        </div>

        <form onSubmit={handleSubmit} className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          <div>
            <label htmlFor="project-name" className="mb-1 block text-sm font-medium">Project name <span className="text-destructive">*</span></label>
            <input id="project-name" className={f} value={name} onChange={(e) => setName(e.target.value)} placeholder="Spring towels — warp 1" required />
          </div>

          <div>
            <label htmlFor="project-tags" className="mb-1 block text-sm font-medium">Tags <span className="text-muted-foreground font-normal">(optional)</span></label>
            <TagInput id="project-tags" tags={tags} onChange={setTags} placeholder="cotton, twill…" />
          </div>

          <div>
            <label htmlFor="project-draft" className="mb-1 block text-sm font-medium">Draft <span className="text-destructive">*</span></label>
            {defaultDraftId ? (
              <p className="py-2 text-sm">{selectedDraft?.name ?? "—"}</p>
            ) : (
              <select id="project-draft" className={f} value={draftId} onChange={(e) => { setDraftId(e.target.value); setProjectType(""); }} required>
                <option value="">Select a draft…</option>
                {drafts.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label htmlFor="project-loom" className="mb-1 block text-sm font-medium">Loom <span className="text-muted-foreground font-normal">(optional)</span></label>
            <select id="project-loom" className={f} value={loomId} onChange={(e) => handleLoomChange(e.target.value)}>
              <option value="">No loom selected</option>
              {looms.filter((l) => SUPPORTED_LOOM_TYPES.has(l.loom_type)).map((l) => (
                <option key={l.id} value={l.id}>{l.manufacturer} {l.model_name}</option>
              ))}
            </select>
            {looms.some((l) => !SUPPORTED_LOOM_TYPES.has(l.loom_type)) && (
              <p className="mt-1 text-xs text-muted-foreground">Looms without project tracking support are not shown.</p>
            )}
          </div>

          {!loomId && selectedDraft && <NoLoomSelectedNotice />}

          {selectedLoom && loomVersions.length > 1 && (
            <LoomVersionSelector
              loomVersions={loomVersions}
              loomVersionId={loomVersionId}
              onChange={(versionId) => {
                setLoomVersionId(versionId);
                const v = loomVersions.find((lv) => lv.id === versionId);
                if (v?.warp_waste_allowance) setWarpWaste(loomWasteInUnit(v.warp_waste_allowance, v.warp_waste_unit, lengthUnit));
              }}
            />
          )}

          <CompatibilityMismatchNotice
            treadleMismatch={treadleMismatch}
            shaftMismatch={shaftMismatch}
            selectedLoom={selectedLoom}
            effectiveTreadles={effectiveTreadles}
            loomTreadles={loomTreadles}
            effectiveShafts={effectiveShafts}
            loomShafts={loomShafts}
          />

          <MetadataMismatchNotice
            treadleMetaMismatch={treadleMetaMismatch}
            shaftMetaMismatch={shaftMetaMismatch}
            treadleMismatch={treadleMismatch}
            shaftMismatch={shaftMismatch}
            selectedDraft={selectedDraft}
          />

          {selectedDraft && (
            <div>
              <label htmlFor="project-type" className="mb-1 block text-sm font-medium">Project type <span className="text-destructive">*</span></label>
              <ProjectTypeSection
                filteredTypes={filteredTypes}
                availableTypes={availableTypes}
                selectedLoom={selectedLoom}
                effectiveType={effectiveType}
                setProjectType={setProjectType}
              />
            </div>
          )}

          <WarpPlanFields
            selectedDraft={selectedDraft}
            draftHasWarpLength={draftHasWarpLength}
            finishedLength={finishedLength}
            setFinishedLength={setFinishedLength}
            lengthUnit={lengthUnit}
            onUnitChange={handleUnitChange}
            finishedLengthDeviatesFromDefault={finishedLengthDeviatesFromDefault}
            warpLengthDefaultLabel={warpLengthDefaultLabel}
            finishedLengthMatchesDefault={finishedLengthMatchesDefault}
            numItems={numItems}
            setNumItems={setNumItems}
            wasteBetween={wasteBetween}
            setWasteBetween={setWasteBetween}
            warpWaste={warpWaste}
            setWarpWaste={setWarpWaste}
            warpWasteInputValue={loomWasteInUnit(
              selectedVersion?.warp_waste_allowance ?? loomDetail?.versions.at(-1)?.warp_waste_allowance,
              selectedVersion?.warp_waste_unit ?? loomDetail?.versions.at(-1)?.warp_waste_unit ?? "cm",
              lengthUnit,
            )}
          />

          {conflictProject && (
            <LoomConflictNotice
              conflictProject={conflictProject}
              loading={loading}
              onResolve={handleResolveAndCreate}
              onClearLoom={() => handleLoomChange("")}
            />
          )}
          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </form>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {loading ? "Creating…" : "Start project"}
          </Button>
        </div>
      </div>
    </div>
  );
}
