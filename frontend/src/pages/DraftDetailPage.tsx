import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDraft, deleteDraft, generateLiftplan, overrideDraftMetadata, setDraftWarpLength, setDraftWeavingWidth, setDraftEpi, previewSvgUrl, downloadWif, downloadWifModified } from "@/api/drafts";
import { listProjects } from "@/api/projects";
import { ProjectSummaryList } from "@/components/projects/ProjectSummaryList";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { DraftPreviewModal } from "@/components/drafts/DraftPreviewModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, convertLength, formatLength } from "@/lib/units";
import { nearestColorName } from "@/lib/colorName";

export function DraftDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthContext();
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showDangerZone, setShowDangerZone] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [editingWarpLength, setEditingWarpLength] = useState(false);
  const [warpLengthInput, setWarpLengthInput] = useState("");
  const [warpLengthUnit, setWarpLengthUnit] = useState<"cm" | "in">(displayUnit);
  const [editingWeavingWidth, setEditingWeavingWidth] = useState(false);
  const [weavingWidthInput, setWeavingWidthInput] = useState("");
  const [weavingWidthUnit, setWeavingWidthUnit] = useState<"cm" | "in">(displayUnit);
  const [editingEpi, setEditingEpi] = useState(false);
  const [epiInput, setEpiInput] = useState("");

  const { data: draft, isLoading, error } = useQuery({
    queryKey: ["draft", id],
    queryFn: () => getDraft(id!),
    enabled: !!id,
  });

  const { data: draftProjects = [] } = useQuery({
    queryKey: ["projects", { draftId: id }],
    queryFn: () => listProjects({ draftId: id! }),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDraft(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      navigate("/drafts", { replace: true });
    },
  });

  const generateMutation = useMutation({
    mutationFn: () => generateLiftplan(id!),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", id], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const overrideMutation = useMutation({
    mutationFn: ({ field, value }: { field: "num_treadles" | "num_shafts"; value: number }) =>
      overrideDraftMetadata(id!, field, value),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", id], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const warpLengthMutation = useMutation({
    mutationFn: ({ length, unit }: { length: number; unit: "cm" | "in" }) =>
      setDraftWarpLength(id!, length, unit),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", id], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditingWarpLength(false);
      setWarpLengthInput("");
    },
  });

  const weavingWidthMutation = useMutation({
    mutationFn: ({ width, unit }: { width: number; unit: "cm" | "in" }) =>
      setDraftWeavingWidth(id!, width, unit),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", id], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditingWeavingWidth(false);
      setWeavingWidthInput("");
    },
  });

  const epiMutation = useMutation({
    mutationFn: ({ epi }: { epi: number }) => setDraftEpi(id!, epi),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", id], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditingEpi(false);
      setEpiInput("");
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-muted-foreground">Loading…</span>
      </div>
    );
  }

  if (error || !draft) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-destructive">Draft not found.</span>
      </div>
    );
  }

  // Weaving width: user override → WIF weft_length → calculated from thread count × spacing
  const weavingWidthCm: number | null =
    draft.weaving_width_override_cm ??
    draft.wif_measurements?.weft_length ??
    (draft.warp_threads != null && draft.wif_measurements?.warp_spacing != null
      ? draft.warp_threads * draft.wif_measurements.warp_spacing
      : null);
  const weavingWidthSource: "override" | "wif" | "calculated" | null =
    draft.weaving_width_override_cm != null ? "override" :
    draft.wif_measurements?.weft_length != null ? "wif" :
    (draft.warp_threads != null && draft.wif_measurements?.warp_spacing != null) ? "calculated" :
    null;

  // EPI: user override → WIF warp_spacing → calculated from width ÷ thread count
  const epiFromSpacing =
    draft.wif_measurements?.warp_spacing != null && draft.wif_measurements.warp_spacing > 0
      ? Math.round((2.54 / draft.wif_measurements.warp_spacing) * 10) / 10
      : null;
  const epiFromWidthAndCount =
    weavingWidthCm != null && weavingWidthCm > 0 && draft.warp_threads != null
      ? Math.round((draft.warp_threads / (weavingWidthCm / 2.54)) * 10) / 10
      : null;
  const resolvedEpi: number | null =
    draft.epi_override ?? epiFromSpacing ?? epiFromWidthAndCount;
  const epiSource: "override" | "spacing" | "calculated" | null =
    draft.epi_override != null ? "override" :
    epiFromSpacing != null ? "spacing" :
    epiFromWidthAndCount != null ? "calculated" :
    null;

  return (
    <div className="p-6 max-w-5xl mx-auto w-full space-y-6">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/drafts" className="text-muted-foreground hover:text-foreground">Drafts</Link>
        <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="font-medium text-foreground">{draft.name}</span>
      </div>

        {/* Lint status */}
        {draft.lint_errors.length > 0 && (
          <div className="rounded-md bg-destructive/10 p-4 space-y-1">
            <p className="text-sm font-medium text-destructive">Errors</p>
            {draft.lint_errors.map((e, i) => (
              <p key={i} className="text-sm text-destructive">{e}</p>
            ))}
          </div>
        )}
        {draft.lint_warnings.length > 0 && (
          <div className="rounded-md bg-muted p-4 space-y-1">
            <p className="text-sm font-medium">Warnings</p>
            {draft.lint_warnings.map((w, i) => (
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
                  <span>{draft.wif_filename}</span>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
                    disabled={downloading}
                    onClick={async () => {
                      setDownloadError(null);
                      setDownloading(true);
                      try {
                        await downloadWif(draft.id, draft.wif_filename);
                      } catch {
                        setDownloadError("Download failed");
                      } finally {
                        setDownloading(false);
                      }
                    }}
                  >
                    {downloading ? "Downloading…" : draft.has_modified_file ? "Download original" : "Download"}
                  </button>
                  {draft.has_modified_file && (
                    <button
                      type="button"
                      className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
                      disabled={downloading}
                      onClick={async () => {
                        setDownloadError(null);
                        setDownloading(true);
                        try {
                          await downloadWifModified(draft.id, draft.wif_filename);
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
                  {draft.num_shafts ?? "—"}
                  {draft.metadata_overrides?.num_shafts && (
                    <span className="text-xs text-muted-foreground">(value overwritten)</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">Treadles</dt>
                <dd className="flex items-center gap-1.5">
                  {draft.num_treadles ?? "—"}
                  {draft.metadata_overrides?.num_treadles && (
                    <span className="text-xs text-muted-foreground">(value overwritten)</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">Warp threads</dt>
                <dd>{draft.warp_threads ?? "—"}</dd>
                <dt className="text-muted-foreground">Weft threads</dt>
                <dd>{draft.weft_threads ?? "—"}</dd>
                {draft.wif_source_software && (
                  <>
                    <dt className="text-muted-foreground">Source software</dt>
                    <dd>{draft.wif_source_software}{draft.wif_source_version ? ` ${draft.wif_source_version}` : ""}</dd>
                  </>
                )}
                <dt className="text-muted-foreground">Warp length</dt>
                <dd>
                  {editingWarpLength ? (
                    <form
                      className="flex items-center gap-1.5 flex-wrap"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const v = parseFloat(warpLengthInput);
                        if (!isNaN(v) && v > 0) {
                          warpLengthMutation.mutate({ length: v, unit: warpLengthUnit });
                        }
                      }}
                    >
                      <input
                        type="number"
                        min={0}
                        step="0.1"
                        className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                        value={warpLengthInput}
                        onChange={(e) => setWarpLengthInput(e.target.value)}
                        placeholder="e.g. 500"
                        autoFocus
                        required
                      />
                      <select
                        className="rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                        value={warpLengthUnit}
                        onChange={(e) => setWarpLengthUnit(e.target.value as "cm" | "in")}
                      >
                        <option value="cm">cm</option>
                        <option value="in">in</option>
                      </select>
                      <Button type="submit" size="sm" disabled={warpLengthMutation.isPending}>
                        {warpLengthMutation.isPending ? "Saving…" : "Save"}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => { setEditingWarpLength(false); setWarpLengthInput(""); }}
                        disabled={warpLengthMutation.isPending}
                      >
                        Cancel
                      </Button>
                      {warpLengthMutation.isError && (
                        <span className="text-xs text-destructive">
                          {warpLengthMutation.error instanceof Error ? warpLengthMutation.error.message : "Save failed"}
                        </span>
                      )}
                    </form>
                  ) : (
                    <div className="flex items-center gap-2 flex-wrap">
                      {draft.warp_length_cm != null ? (
                        <>
                          <span>{formatLength(convertLength(draft.warp_length_cm, "cm", displayUnit), displayUnit)}</span>
                          {draft.wif_measurements?.warp_length != null && !draft.warp_length_overridden && (
                            <span className="text-xs text-muted-foreground">
                              ({draft.wif_measurements.warp_length_original} {draft.wif_measurements.warp_length_unit} in WIF)
                            </span>
                          )}
                          {draft.warp_length_overridden && draft.wif_measurements?.warp_length != null && (
                            <span className="text-xs text-muted-foreground">
                              (WIF: {draft.wif_measurements.warp_length_original} {draft.wif_measurements.warp_length_unit}, overridden)
                            </span>
                          )}
                          <button
                            type="button"
                            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                            onClick={() => {
                              const v = convertLength(draft.warp_length_cm!, "cm", displayUnit);
                              setWarpLengthInput(parseFloat(v.toFixed(1)).toString());
                              setWarpLengthUnit(displayUnit);
                              setEditingWarpLength(true);
                            }}
                          >
                            Edit
                          </button>
                        </>
                      ) : (
                        <>
                          <span className="text-muted-foreground">Not set</span>
                          <button
                            type="button"
                            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                            onClick={() => { setWarpLengthInput(""); setWarpLengthUnit(displayUnit); setEditingWarpLength(true); }}
                          >
                            Set
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </dd>
                {draft.warp_length_cm == null && !editingWarpLength && (
                  <>
                    <dt />
                    <dd className="text-xs text-subdued">
                      Warp calculations unavailable until warp length is set.
                    </dd>
                  </>
                )}
                <dt className="text-muted-foreground">Weaving width</dt>
                <dd>
                  {editingWeavingWidth ? (
                    <div className="flex items-center gap-1 flex-wrap">
                      <input
                        type="number"
                        min="0"
                        step="0.1"
                        className="w-20 rounded border border-border bg-input px-2 py-0.5 text-sm"
                        value={weavingWidthInput}
                        onChange={(e) => setWeavingWidthInput(e.target.value)}
                      />
                      <select
                        className="rounded border border-border bg-input px-1 py-0.5 text-sm"
                        value={weavingWidthUnit}
                        onChange={(e) => setWeavingWidthUnit(e.target.value as "cm" | "in")}
                      >
                        <option value="cm">cm</option>
                        <option value="in">in</option>
                      </select>
                      <button
                        type="button"
                        className="text-xs text-accent underline underline-offset-2"
                        onClick={() => {
                          const v = parseFloat(weavingWidthInput);
                          if (!isNaN(v) && v > 0) weavingWidthMutation.mutate({ width: v, unit: weavingWidthUnit });
                        }}
                      >Save</button>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2"
                        onClick={() => { setEditingWeavingWidth(false); setWeavingWidthInput(""); }}
                      >Cancel</button>
                    </div>
                  ) : weavingWidthCm != null ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span>{formatLength(convertLength(weavingWidthCm, "cm", displayUnit), displayUnit)}</span>
                      {weavingWidthSource === "wif" && draft.wif_measurements?.weft_length_unit !== displayUnit && (
                        <span className="text-xs text-muted-foreground">
                          ({draft.wif_measurements!.weft_length_original} {draft.wif_measurements!.weft_length_unit} in WIF)
                        </span>
                      )}
                      {weavingWidthSource === "calculated" && (
                        <span className="text-xs text-muted-foreground">(thread count × spacing)</span>
                      )}
                      {weavingWidthSource === "override" && (
                        <span className="text-xs text-muted-foreground">(manually set)</span>
                      )}
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => {
                          setWeavingWidthInput(String(Math.round(convertLength(weavingWidthCm, "cm", displayUnit) * 10) / 10));
                          setWeavingWidthUnit(displayUnit);
                          setEditingWeavingWidth(true);
                        }}
                      >Edit</button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">Not set</span>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => { setWeavingWidthInput(""); setWeavingWidthUnit(displayUnit); setEditingWeavingWidth(true); }}
                      >Set</button>
                    </div>
                  )}
                </dd>
                <dt className="text-muted-foreground">EPI</dt>
                <dd>
                  {editingEpi ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min="0"
                        step="0.5"
                        className="w-20 rounded border border-border bg-input px-2 py-0.5 text-sm"
                        value={epiInput}
                        onChange={(e) => setEpiInput(e.target.value)}
                      />
                      <span className="text-sm text-muted-foreground">ends/in</span>
                      <button
                        type="button"
                        className="text-xs text-accent underline underline-offset-2"
                        onClick={() => {
                          const v = parseFloat(epiInput);
                          if (!isNaN(v) && v > 0) epiMutation.mutate({ epi: v });
                        }}
                      >Save</button>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2"
                        onClick={() => { setEditingEpi(false); setEpiInput(""); }}
                      >Cancel</button>
                    </div>
                  ) : resolvedEpi != null ? (
                    <div className="flex items-center gap-2">
                      <span>{resolvedEpi} ends/in</span>
                      {epiSource === "calculated" && (
                        <span className="text-xs text-muted-foreground">(width ÷ thread count)</span>
                      )}
                      {epiSource === "spacing" && (
                        <span className="text-xs text-muted-foreground">(from WIF spacing)</span>
                      )}
                      {epiSource === "override" && (
                        <span className="text-xs text-muted-foreground">(manually set)</span>
                      )}
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => { setEpiInput(String(resolvedEpi)); setEditingEpi(true); }}
                      >Edit</button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">Not set</span>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => { setEpiInput(""); setEditingEpi(true); }}
                      >Set</button>
                    </div>
                  )}
                </dd>
              </dl>

              {draft.wif_colors && draft.wif_colors.length > 0 && (
                <div className="mt-4 space-y-2">
                  <h3 className="text-sm font-medium">Color palette</h3>
                  <div className="flex flex-wrap gap-2">
                    {draft.wif_colors.map((c) => (
                      <div key={c.index} className="flex flex-col items-center gap-1 w-16" title={`#${c.index}: RGB(${c.r}, ${c.g}, ${c.b}) — ${c.hex}`}>
                        <div
                          className="h-8 w-16 rounded border border-border flex-shrink-0"
                          style={{ backgroundColor: c.hex }}
                        />
                        <span className="text-[10px] text-muted-foreground font-mono leading-none">{c.hex}</span>
                        <span className="text-[10px] text-subdued leading-none text-center">{nearestColorName(c.hex)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-3 border-t pt-4">
              <h2 className="text-base font-semibold">Features</h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {(
                  [
                    ["Threading diagram", draft.has_threading],
                    ["Tie-up grid", draft.has_tieup],
                    ["Treadle-tracking", draft.has_treadling],
                    ["Color palette", draft.has_color_palette],
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
                  {draft.has_liftplan ? (
                    <span className="text-foreground">
                      ✓ Available
                      {draft.liftplan_generated && (
                        <span className="ml-1.5 text-xs text-muted-foreground">(computed)</span>
                      )}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">✗ Not in file</span>
                  )}
                </dd>
              </dl>

              {!draft.has_liftplan && draft.has_treadling && draft.has_tieup && (
                <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2.5 text-sm">
                  <p className="font-medium text-copper-on-subtle">Lift plan not in file</p>
                  <p className="mt-0.5 text-copper-on-subtle text-xs">
                    This WIF has treadling and tie-up data. A lift plan can be computed algorithmically and added to the draft.
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
              {draft.effective_num_treadles != null &&
                draft.num_treadles != null &&
                draft.effective_num_treadles !== draft.num_treadles && (
                <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
                  <p className="font-medium text-foreground">Treadle metadata mismatch</p>
                  <p className="mt-0.5 text-subdued text-xs">
                    [WEAVING] declares {draft.num_treadles} treadles but the treadling data only uses {draft.effective_num_treadles}.
                    {draft.metadata_overrides?.num_treadles
                      ? ` (overridden from ${draft.metadata_overrides.num_treadles.original})`
                      : " Override to fix loom compatibility checks and correct the exported file."}
                  </p>
                  {overrideMutation.isError && overrideMutation.variables?.field === "num_treadles" && (
                    <p className="mt-1 text-xs text-destructive">
                      {overrideMutation.error instanceof Error ? overrideMutation.error.message : "Override failed"}
                    </p>
                  )}
                  {!draft.metadata_overrides?.num_treadles && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={() => overrideMutation.mutate({ field: "num_treadles", value: draft.effective_num_treadles! })}
                      disabled={overrideMutation.isPending}
                    >
                      {overrideMutation.isPending && overrideMutation.variables?.field === "num_treadles"
                        ? "Overriding…"
                        : `Set treadles to ${draft.effective_num_treadles}`}
                    </Button>
                  )}
                </div>
              )}

              {/* Shaft metadata mismatch — offer override */}
              {draft.effective_num_shafts != null &&
                draft.num_shafts != null &&
                draft.effective_num_shafts !== draft.num_shafts && (
                <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
                  <p className="font-medium text-foreground">Shaft metadata mismatch</p>
                  <p className="mt-0.5 text-subdued text-xs">
                    [WEAVING] declares {draft.num_shafts} shafts but the lift plan only uses {draft.effective_num_shafts}.
                    {draft.metadata_overrides?.num_shafts
                      ? ` (overridden from ${draft.metadata_overrides.num_shafts.original})`
                      : " Override to fix loom compatibility checks and correct the exported file."}
                  </p>
                  {overrideMutation.isError && overrideMutation.variables?.field === "num_shafts" && (
                    <p className="mt-1 text-xs text-destructive">
                      {overrideMutation.error instanceof Error ? overrideMutation.error.message : "Override failed"}
                    </p>
                  )}
                  {!draft.metadata_overrides?.num_shafts && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      onClick={() => overrideMutation.mutate({ field: "num_shafts", value: draft.effective_num_shafts! })}
                      disabled={overrideMutation.isPending}
                    >
                      {overrideMutation.isPending && overrideMutation.variables?.field === "num_shafts"
                        ? "Overriding…"
                        : `Set shafts to ${draft.effective_num_shafts}`}
                    </Button>
                  )}
                </div>
              )}
            </div>

            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold">Projects</h2>
                <div className="flex items-center gap-3">
                  <Button size="sm" onClick={() => setShowCreateProject(true)}>New project</Button>
                  <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground">
                    All projects →
                  </Link>
                </div>
              </div>
              <ProjectSummaryList projects={draftProjects} />
            </div>
          </div>

          {/* Right column: Preview */}
          <div>
            <h2 className="text-base font-semibold mb-3">Design Preview</h2>
            {draft.wif_filename ? (
              <button
                type="button"
                className="group w-full overflow-auto rounded-lg border bg-card p-2 cursor-zoom-in text-left"
                onClick={() => setShowPreviewModal(true)}
                title="Click to open interactive preview"
              >
                <AuthedImage
                  src={previewSvgUrl(draft.id)}
                  alt={`Draft preview for ${draft.name}`}
                  className="max-w-full group-hover:opacity-90 transition-opacity"
                  data-testid="draft-preview-img"
                />
                <p className="mt-1.5 text-xs text-muted-foreground text-center opacity-0 group-hover:opacity-100 transition-opacity">
                  Click to zoom
                </p>
              </button>
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
                <p className="text-sm font-medium">Delete draft</p>
                <p className="text-xs text-muted-foreground mt-0.5">Permanently removes this draft and its WIF file. Projects are not deleted.</p>
              </div>
              <div className="flex gap-2 shrink-0">
                {!confirmDelete ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setConfirmDelete(true)}
                  >
                    Delete draft
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

      {showCreateProject && (
        <CreateProjectModal
          defaultDraftId={id}
          onSuccess={(newId) => {
            setShowCreateProject(false);
            queryClient.invalidateQueries({ queryKey: ["projects", { draftId: id }] });
            queryClient.invalidateQueries({ queryKey: ["projects"] });
            navigate(`/projects/${newId}`);
          }}
          onClose={() => setShowCreateProject(false)}
        />
      )}

      {showPreviewModal && (
        <DraftPreviewModal
          draftId={draft.id}
          draftName={draft.name}
          onClose={() => setShowPreviewModal(false)}
        />
      )}
    </div>
  );
}
