import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate, Link } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDraft, deleteDraft, archiveDraft, unarchiveDraft, generateLiftplan, overrideDraftMetadata, setDraftWarpLength, setDraftWeavingWidth, setDraftEpi, updateDraft, previewUrl, previewSvgUrl, downloadWif, downloadWifModified, type ColorStat, type DeleteConflict } from "@/api/drafts";
import { TagInput } from "@/components/ui/TagInput";
import { TagChips } from "@/components/ui/TagChips";
import { addDraftToCollection, removeDraftFromCollection } from "@/api/collections";
import { AddToCollectionModal } from "@/components/collections/AddToCollectionModal";
import { listProjects } from "@/api/projects";
import { ProjectSummaryList } from "@/components/projects/ProjectSummaryList";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { DraftPreviewModal } from "@/components/drafts/DraftPreviewModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, convertLength, formatLength, formatApproxLength } from "@/lib/units";
import { nearestColorName } from "@/lib/colorName";
import { getReedRecommendation } from "@/lib/reedRecommendation";
import { SuperuserInspectionBanner } from "@/components/ui/SuperuserInspectionBanner";

export function DraftDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthContext();
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteConflict, setDeleteConflict] = useState<DeleteConflict | null>(null);
  const [confirmForceDelete, setConfirmForceDelete] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [showDangerZone, setShowDangerZone] = useState(false);
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [showAddToCollection, setShowAddToCollection] = useState(false);
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
  const [editingTags, setEditingTags] = useState(false);
  const [pendingTags, setPendingTags] = useState<string[]>([]);

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
    mutationFn: (force: boolean) => deleteDraft(id!, force),
    onSuccess: (result) => {
      if (result && "code" in result) {
        setDeleteConflict(result as DeleteConflict);
        setConfirmDelete(false);
        return;
      }
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      navigate("/drafts", { replace: true });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveDraft(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft", id] }),
  });

  const unarchiveMutation = useMutation({
    mutationFn: () => unarchiveDraft(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft", id] }),
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

  const tagsMutation = useMutation({
    mutationFn: (tags: string[]) => updateDraft(id!, { tags }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", id], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditingTags(false);
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-muted-foreground">{t("draftDetailPage.loading")}</span>
      </div>
    );
  }

  if (error || !draft) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-sm text-destructive">{t("draftDetailPage.notFound")}</span>
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

  const isReadOnly = !!user?.is_superuser && draft.owner_id !== user.id;

  return (
    <div className="max-w-5xl mx-auto w-full">
      {isReadOnly && <SuperuserInspectionBanner />}
      {draft.archived_at && (
        <div className="px-6 py-2 bg-muted/50 border-b border-border text-sm text-muted-foreground flex items-center gap-2">
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">{t("draftDetailPage.archivedBadge")}</span>
          {t("draftDetailPage.archivedNote")}
        </div>
      )}
      <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <Link to="/drafts" className="text-muted-foreground hover:text-foreground">{t("draftDetailPage.breadcrumb")}</Link>
            <AppIcons.chevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium text-foreground">{draft.name}</span>
          </div>
          {!editingTags && (
            <div className="flex items-center gap-2 flex-wrap">
              {draft.tags && draft.tags.length > 0 && (
                <TagChips tags={draft.tags} max={10} />
              )}
              {!isReadOnly && (
                <button
                  type="button"
                  onClick={() => { setPendingTags(draft.tags ?? []); setEditingTags(true); }}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  {draft.tags && draft.tags.length > 0 ? t("draftDetailPage.editTags") : t("draftDetailPage.addTags")}
                </button>
              )}
            </div>
          )}
          {editingTags && (
            <div className="flex items-center gap-2">
              <div className="w-64">
                <TagInput tags={pendingTags} onChange={setPendingTags} />
              </div>
              <Button
                size="sm"
                onClick={() => tagsMutation.mutate(pendingTags)}
                disabled={tagsMutation.isPending}
              >
                {tagsMutation.isPending ? t("draftDetailPage.saving") : t("common.save")}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditingTags(false)}>
                {t("common.cancel")}
              </Button>
            </div>
          )}
        </div>
        {!isReadOnly && (
          <Button size="sm" variant="outline" onClick={() => setShowAddToCollection(true)}>
            <AppIcons.collections className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
            {t("draftDetailPage.addToCollection")}
          </Button>
        )}
      </div>

        {/* Lint status */}
        {draft.lint_errors.length > 0 && (
          <div className="rounded-md bg-destructive/10 p-4 space-y-1">
            <p className="text-sm font-medium text-destructive">{t("draftDetailPage.lintErrors")}</p>
            {draft.lint_errors.map((e, i) => (
              <p key={i} className="text-sm text-destructive">{e}</p>
            ))}
          </div>
        )}
        {draft.lint_warnings.length > 0 && (
          <div className="rounded-md bg-muted p-4 space-y-1">
            <p className="text-sm font-medium">{t("draftDetailPage.lintWarnings")}</p>
            {draft.lint_warnings.map((w, i) => (
              <p key={i} className="text-sm text-muted-foreground">{w}</p>
            ))}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left column: Info + Features + Activities */}
          <div className="space-y-6">
            <div className="space-y-4">
              <h2 className="text-base font-semibold">{t("draftDetailPage.designInfo")}</h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">{t("draftDetailPage.file")}</dt>
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
                        setDownloadError(t("draftDetailPage.downloadFailed"));
                      } finally {
                        setDownloading(false);
                      }
                    }}
                  >
                    {downloading ? t("draftDetailPage.downloading") : draft.has_modified_file ? t("draftDetailPage.downloadOriginal") : t("draftDetailPage.download")}
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
                          setDownloadError(t("draftDetailPage.downloadFailed"));
                        } finally {
                          setDownloading(false);
                        }
                      }}
                    >
                      {t("draftDetailPage.downloadModified")}
                    </button>
                  )}
                </dd>
                {downloadError && (
                  <dd className="col-span-2 text-xs text-destructive">{downloadError}</dd>
                )}
                <dt className="text-muted-foreground">{t("draftDetailPage.shafts")}</dt>
                <dd className="flex items-center gap-1.5">
                  {draft.num_shafts ?? "—"}
                  {draft.metadata_overrides?.num_shafts && (
                    <span className="text-xs text-muted-foreground">{t("draftDetailPage.valueOverwritten")}</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">{t("draftDetailPage.treadles")}</dt>
                <dd className="flex items-center gap-1.5">
                  {draft.num_treadles ?? "—"}
                  {draft.metadata_overrides?.num_treadles && (
                    <span className="text-xs text-muted-foreground">{t("draftDetailPage.valueOverwritten")}</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">{t("draftDetailPage.warpThreads")}</dt>
                <dd>{draft.warp_threads ?? "—"}</dd>
                <dt className="text-muted-foreground">{t("draftDetailPage.weftThreads")}</dt>
                <dd>{draft.weft_threads ?? "—"}</dd>
                {draft.wif_source_software && (
                  <>
                    <dt className="text-muted-foreground">{t("draftDetailPage.sourceSoftware")}</dt>
                    <dd>{draft.wif_source_software}{draft.wif_source_version ? ` ${draft.wif_source_version}` : ""}</dd>
                  </>
                )}
                <dt className="text-muted-foreground">{t("draftDetailPage.warpLength")}</dt>
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
                        {warpLengthMutation.isPending ? t("draftDetailPage.saving") : t("common.save")}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => { setEditingWarpLength(false); setWarpLengthInput(""); }}
                        disabled={warpLengthMutation.isPending}
                      >
                        {t("common.cancel")}
                      </Button>
                      {warpLengthMutation.isError && (
                        <span className="text-xs text-destructive">
                          {warpLengthMutation.error instanceof Error ? warpLengthMutation.error.message : t("draftDetailPage.saveFailed")}
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
                              ({draft.wif_measurements.warp_length_original} {draft.wif_measurements.warp_length_unit} {t("draftDetailPage.inWif")})
                            </span>
                          )}
                          {draft.warp_length_overridden && draft.wif_measurements?.warp_length != null && (
                            <span className="text-xs text-muted-foreground">
                              {t("draftDetailPage.wifOverridden", { original: draft.wif_measurements.warp_length_original, unit: draft.wif_measurements.warp_length_unit })}
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
                            {t("draftDetailPage.edit")}
                          </button>
                        </>
                      ) : (
                        <>
                          <span className="text-muted-foreground">{t("draftDetailPage.notSet")}</span>
                          <button
                            type="button"
                            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                            onClick={() => { setWarpLengthInput(""); setWarpLengthUnit(displayUnit); setEditingWarpLength(true); }}
                          >
                            {t("draftDetailPage.set")}
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
                      {t("draftDetailPage.warpLengthRequired")}
                    </dd>
                  </>
                )}
                <dt className="text-muted-foreground">{t("draftDetailPage.weavingWidth")}</dt>
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
                      >{t("common.save")}</button>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2"
                        onClick={() => { setEditingWeavingWidth(false); setWeavingWidthInput(""); }}
                      >{t("common.cancel")}</button>
                    </div>
                  ) : weavingWidthCm != null ? (
                    <div className="flex items-center gap-2 flex-wrap">
                      <span>{formatLength(convertLength(weavingWidthCm, "cm", displayUnit), displayUnit)}</span>
                      {weavingWidthSource === "wif" && draft.wif_measurements?.weft_length_unit !== displayUnit && (
                        <span className="text-xs text-muted-foreground">
                          ({draft.wif_measurements!.weft_length_original} {draft.wif_measurements!.weft_length_unit} {t("draftDetailPage.inWif")})
                        </span>
                      )}
                      {weavingWidthSource === "calculated" && (
                        <span className="text-xs text-muted-foreground">{t("draftDetailPage.threadCountSpacing")}</span>
                      )}
                      {weavingWidthSource === "override" && (
                        <span className="text-xs text-muted-foreground">{t("draftDetailPage.manuallySet")}</span>
                      )}
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => {
                          setWeavingWidthInput(String(Math.round(convertLength(weavingWidthCm, "cm", displayUnit) * 10) / 10));
                          setWeavingWidthUnit(displayUnit);
                          setEditingWeavingWidth(true);
                        }}
                      >{t("draftDetailPage.edit")}</button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">{t("draftDetailPage.notSet")}</span>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => { setWeavingWidthInput(""); setWeavingWidthUnit(displayUnit); setEditingWeavingWidth(true); }}
                      >{t("draftDetailPage.set")}</button>
                    </div>
                  )}
                </dd>
                <dt className="text-muted-foreground">{t("draftDetailPage.epi")}</dt>
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
                      <span className="text-sm text-muted-foreground">{t("draftDetailPage.endsPerIn")}</span>
                      <button
                        type="button"
                        className="text-xs text-accent underline underline-offset-2"
                        onClick={() => {
                          const v = parseFloat(epiInput);
                          if (!isNaN(v) && v > 0) epiMutation.mutate({ epi: v });
                        }}
                      >{t("common.save")}</button>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2"
                        onClick={() => { setEditingEpi(false); setEpiInput(""); }}
                      >{t("common.cancel")}</button>
                    </div>
                  ) : resolvedEpi != null ? (
                    <div className="flex items-center gap-2">
                      <span>{resolvedEpi} {t("draftDetailPage.endsPerIn")}</span>
                      {epiSource === "calculated" && (
                        <span className="text-xs text-muted-foreground">{t("draftDetailPage.widthDivCount")}</span>
                      )}
                      {epiSource === "spacing" && (
                        <span className="text-xs text-muted-foreground">{t("draftDetailPage.fromWifSpacing")}</span>
                      )}
                      {epiSource === "override" && (
                        <span className="text-xs text-muted-foreground">{t("draftDetailPage.manuallySet")}</span>
                      )}
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => { setEpiInput(String(resolvedEpi)); setEditingEpi(true); }}
                      >{t("draftDetailPage.edit")}</button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground">{t("draftDetailPage.notSet")}</span>
                      <button
                        type="button"
                        className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
                        onClick={() => { setEpiInput(""); setEditingEpi(true); }}
                      >{t("draftDetailPage.set")}</button>
                    </div>
                  )}
                </dd>

                {resolvedEpi != null && (() => {
                  const rec = getReedRecommendation(resolvedEpi);
                  return (
                    <>
                      <dt className="text-muted-foreground">{t("draftDetailPage.reed")}</dt>
                      <dd>
                        {rec.matches.length > 0 ? (
                          <ul className="space-y-0.5">
                            {rec.matches.map((m) => (
                              <li key={m.dents} className="text-sm">
                                {t("draftDetailPage.reedSpec", { dents: m.dents, threadsPerDent: m.threadsPerDent })}
                                {m.threadsPerDent === 1 && (
                                  <span className="ml-1 text-xs text-muted-foreground">{t("draftDetailPage.reedIdeal")}</span>
                                )}
                              </li>
                            ))}
                          </ul>
                        ) : rec.nearest ? (
                          <p className="text-sm text-muted-foreground">
                            {t("draftDetailPage.reedNoMatch", { epi: resolvedEpi, near1: rec.nearest[0], near2: rec.nearest[1] })}
                          </p>
                        ) : (
                          <span className="text-sm text-muted-foreground">{t("draftDetailPage.reedNotFound")}</span>
                        )}
                      </dd>
                    </>
                  );
                })()}
              </dl>

              {draft.wif_colors && draft.wif_colors.length > 0 && (() => {
                // When both stat arrays are populated, drop colors that appear in neither —
                // they are defined-as-default colors fully overridden by per-thread/per-pick assignments.
                const bothStatsPresent = draft.warp_color_stats !== null && draft.weft_color_stats !== null;
                const visibleColors = bothStatsPresent
                  ? draft.wif_colors.filter(
                      (c) =>
                        draft.weft_color_stats!.some((s) => s.hex === c.hex) ||
                        draft.warp_color_stats!.some((s) => s.hex === c.hex),
                    )
                  : draft.wif_colors;
                if (visibleColors.length === 0) return null;
                return (
                <div className="mt-4 space-y-2">
                  <h3 className="text-sm font-medium">{t("draftDetailPage.colorPalette")}</h3>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-muted-foreground">
                        <th className="text-left pb-1.5 font-normal pr-3">{t("draftDetailPage.colorPaletteColor")}</th>
                        <th className="text-left pb-1.5 font-normal pr-3">{t("draftDetailPage.colorPaletteName")}</th>
                        <th className="text-right pb-1.5 font-normal pr-3">{t("draftDetailPage.colorPaletteWarpEnds")}</th>
                        <th className="text-right pb-1.5 font-normal pr-3">{t("draftDetailPage.colorPaletteWeftPicks")}</th>
                        {weavingWidthCm != null && (
                          <th className="text-right pb-1.5 font-normal">{t("draftDetailPage.colorPaletteEstWeftLength")}</th>
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {visibleColors.map((c) => {
                        const weftStat: ColorStat | undefined = draft.weft_color_stats?.find(
                          (s) => s.hex === c.hex,
                        );
                        const warpStat: ColorStat | undefined = draft.warp_color_stats?.find(
                          (s) => s.hex === c.hex,
                        );
                        const approxLengthCm =
                          weftStat && weavingWidthCm != null
                            ? weftStat.count * weavingWidthCm
                            : null;
                        return (
                          <tr
                            key={c.index}
                            className="border-t border-border"
                            title={`#${c.index}: RGB(${c.r}, ${c.g}, ${c.b})`}
                          >
                            <td className="py-1.5 pr-3">
                              <div className="flex items-center gap-1.5">
                                <div
                                  className="h-4 w-6 rounded-sm border border-border flex-shrink-0"
                                  style={{ backgroundColor: c.hex }}
                                />
                                <span className="font-mono text-muted-foreground">{c.hex}</span>
                              </div>
                            </td>
                            <td className="py-1.5 pr-3 text-subdued">{nearestColorName(c.hex)}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">
                              {warpStat
                                ? <>{warpStat.count} <span className="text-muted-foreground">({warpStat.percentage}%)</span></>
                                : <span className="text-muted-foreground">—</span>}
                            </td>
                            <td className="py-1.5 pr-3 text-right tabular-nums">
                              {weftStat
                                ? <>{weftStat.count} <span className="text-muted-foreground">({weftStat.percentage}%)</span></>
                                : <span className="text-muted-foreground">—</span>}
                            </td>
                            {weavingWidthCm != null && (
                              <td className="py-1.5 text-right tabular-nums text-subdued">
                                {approxLengthCm != null
                                  ? `~${formatApproxLength(approxLengthCm, displayUnit)}`
                                  : <span className="text-muted-foreground">—</span>}
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                );
              })()}
            </div>

            <div className="space-y-3 border-t pt-4">
              <h2 className="text-base font-semibold">{t("draftDetailPage.features")}</h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {(
                  [
                    [t("draftDetailPage.threadingDiagram"), draft.has_threading],
                    [t("draftDetailPage.tieUpGrid"), draft.has_tieup],
                    [t("draftDetailPage.treadleTracking"), draft.has_treadling],
                    [t("draftDetailPage.colorPalette"), draft.has_color_palette],
                  ] as [string, boolean][]
                ).map(([label, available]) => (
                  <>
                    <dt key={`${label}-dt`} className="text-muted-foreground">{label}</dt>
                    <dd key={`${label}-dd`} className={available ? "text-foreground" : "text-muted-foreground"}>
                      {available ? t("draftDetailPage.featureAvailable") : t("draftDetailPage.featureNotInFile")}
                    </dd>
                  </>
                ))}
                <dt className="text-muted-foreground">{t("draftDetailPage.liftTracking")}</dt>
                <dd>
                  {draft.has_liftplan ? (
                    <span className="text-foreground">
                      {t("draftDetailPage.featureAvailable")}
                      {draft.liftplan_generated && (
                        <span className="ml-1.5 text-xs text-muted-foreground">{t("draftDetailPage.computed")}</span>
                      )}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">{t("draftDetailPage.featureNotInFile")}</span>
                  )}
                </dd>
              </dl>

              {!draft.has_liftplan && draft.has_treadling && draft.has_tieup && (
                <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2.5 text-sm">
                  <p className="font-medium text-copper-on-subtle">{t("draftDetailPage.liftPlanNotInFile")}</p>
                  <p className="mt-0.5 text-copper-on-subtle text-xs">
                    {t("draftDetailPage.liftPlanCanBeComputed")}
                  </p>
                  {generateMutation.isError && (
                    <p className="mt-1 text-xs text-destructive">
                      {generateMutation.error instanceof Error ? generateMutation.error.message : t("draftDetailPage.generationFailed")}
                    </p>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-2"
                    onClick={() => generateMutation.mutate()}
                    disabled={generateMutation.isPending}
                  >
                    {generateMutation.isPending ? t("draftDetailPage.generating") : t("draftDetailPage.generateLiftPlan")}
                  </Button>
                </div>
              )}

              {/* Treadle metadata mismatch — offer override */}
              {draft.effective_num_treadles != null &&
                draft.num_treadles != null &&
                draft.effective_num_treadles !== draft.num_treadles && (
                <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
                  <p className="font-medium text-foreground">{t("draftDetailPage.treadleMismatch")}</p>
                  <p className="mt-0.5 text-subdued text-xs">
                    {t("draftDetailPage.treadleMismatchDesc", { numDeclared: draft.num_treadles, numUsed: draft.effective_num_treadles })}
                    {draft.metadata_overrides?.num_treadles
                      ? " " + t("draftDetailPage.overriddenFrom", { original: draft.metadata_overrides.num_treadles.original })
                      : " " + t("draftDetailPage.overrideToFix")}
                  </p>
                  {overrideMutation.isError && overrideMutation.variables?.field === "num_treadles" && (
                    <p className="mt-1 text-xs text-destructive">
                      {overrideMutation.error instanceof Error ? overrideMutation.error.message : t("draftDetailPage.overrideFailed")}
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
                        ? t("draftDetailPage.overriding")
                        : t("draftDetailPage.setTreadles", { count: draft.effective_num_treadles })}
                    </Button>
                  )}
                </div>
              )}

              {/* Shaft metadata mismatch — offer override */}
              {draft.effective_num_shafts != null &&
                draft.num_shafts != null &&
                draft.effective_num_shafts !== draft.num_shafts && (
                <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
                  <p className="font-medium text-foreground">{t("draftDetailPage.shaftMismatch")}</p>
                  <p className="mt-0.5 text-subdued text-xs">
                    {t("draftDetailPage.shaftMismatchDesc", { numDeclared: draft.num_shafts, numUsed: draft.effective_num_shafts })}
                    {draft.metadata_overrides?.num_shafts
                      ? " " + t("draftDetailPage.overriddenFrom", { original: draft.metadata_overrides.num_shafts.original })
                      : " " + t("draftDetailPage.overrideToFix")}
                  </p>
                  {overrideMutation.isError && overrideMutation.variables?.field === "num_shafts" && (
                    <p className="mt-1 text-xs text-destructive">
                      {overrideMutation.error instanceof Error ? overrideMutation.error.message : t("draftDetailPage.overrideFailed")}
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
                        ? t("draftDetailPage.overriding")
                        : t("draftDetailPage.setShafts", { count: draft.effective_num_shafts })}
                    </Button>
                  )}
                </div>
              )}
            </div>

            <div className="border-t pt-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-semibold">{t("draftDetailPage.projects")}</h2>
                <div className="flex items-center gap-3">
                  {!isReadOnly && <Button size="sm" onClick={() => setShowCreateProject(true)}>{t("draftDetailPage.newProject")}</Button>}
                  <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground">
                    {t("draftDetailPage.allProjects")}
                  </Link>
                </div>
              </div>
              <ProjectSummaryList projects={draftProjects} />
            </div>
          </div>

          {/* Right column: Preview */}
          <div>
            <h2 className="text-base font-semibold mb-3">{t("draftDetailPage.designPreview")}</h2>
            {draft.wif_filename ? (
              <button
                type="button"
                className="group w-full overflow-hidden rounded-lg border bg-card p-2 cursor-zoom-in text-left"
                onClick={() => setShowPreviewModal(true)}
                title={t("draftDetailPage.previewTitle")}
              >
                <AuthedImage
                  src={draft.has_preview ? previewUrl(draft.id) : previewSvgUrl(draft.id)}
                  alt={`Draft preview for ${draft.name}`}
                  className="max-w-full group-hover:opacity-90 transition-opacity"
                  data-testid="draft-preview-img"
                  loadingContent={
                    <div className="w-full min-h-48 animate-pulse rounded-md bg-muted flex items-center justify-center">
                      <span className="text-sm text-muted-foreground">{t("draftDetailPage.loadingPreview")}</span>
                    </div>
                  }
                />
                <p className="mt-1.5 text-xs text-muted-foreground text-center opacity-0 group-hover:opacity-100 transition-opacity">
                  {t("draftDetailPage.clickToZoom")}
                </p>
              </button>
            ) : (
              <div className="rounded-lg border border-dashed p-8 text-center">
                <p className="text-sm text-muted-foreground">
                  {t("draftDetailPage.previewUnavailable")}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Danger zone */}
        {!isReadOnly && <div className="border-t pt-4">
          <button
            type="button"
            onClick={() => { setShowDangerZone((v) => !v); setConfirmDelete(false); setDeleteConflict(null); setConfirmForceDelete(false); }}
            className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-destructive transition-colors"
          >
            <span>{t("draftDetailPage.dangerZone")}</span>
            <span>{showDangerZone ? "▲" : "▼"}</span>
          </button>
          {showDangerZone && (
            <div className="mt-3 space-y-3">
              {/* Archive / Unarchive */}
              <div className="rounded-md border border-border p-4 flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium">{draft.archived_at ? t("draftDetailPage.unarchiveDraft") : t("draftDetailPage.archiveDraft")}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {draft.archived_at ? t("draftDetailPage.unarchiveNote") : t("draftDetailPage.archiveNote")}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  {!confirmArchive ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setConfirmArchive(true)}
                    >
                      {draft.archived_at ? t("draftDetailPage.unarchive") : t("draftDetailPage.archive")}
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setConfirmArchive(false);
                          if (draft.archived_at) unarchiveMutation.mutate(); else archiveMutation.mutate();
                        }}
                        disabled={archiveMutation.isPending || unarchiveMutation.isPending}
                      >
                        {t("draftDetailPage.confirm")}
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setConfirmArchive(false)}>
                        {t("common.cancel")}
                      </Button>
                    </>
                  )}
                </div>
              </div>

              {/* Delete */}
              <div className="rounded-md border border-destructive/30 p-4 space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium">{t("draftDetailPage.deleteDraft")}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{t("draftDetailPage.deleteNote")}</p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    {!confirmDelete && !deleteConflict ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setConfirmDelete(true)}
                      >
                        {t("draftDetailPage.deleteDraft")}
                      </Button>
                    ) : confirmDelete ? (
                      <>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => deleteMutation.mutate(false)}
                          disabled={deleteMutation.isPending}
                        >
                          {t("draftDetailPage.confirmDelete")}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)}>
                          {t("common.cancel")}
                        </Button>
                      </>
                    ) : null}
                  </div>
                </div>

                {/* 409 conflict */}
                {deleteConflict && (
                  <div className="space-y-2">
                    <p className="text-sm text-destructive font-medium">
                      {t("draftDetailPage.usedByConflict", { count: deleteConflict.projects.length })}
                    </p>
                    <ul className="text-xs text-muted-foreground space-y-0.5 pl-3">
                      {deleteConflict.projects.map((p) => <li key={p.id}>· {p.name}</li>)}
                    </ul>
                    <p className="text-xs text-muted-foreground">
                      {t("draftDetailPage.conflictNote")}
                    </p>
                    {!confirmForceDelete ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setConfirmForceDelete(true)}
                      >
                        {t("draftDetailPage.forceDelete", { count: deleteConflict.projects.length })}
                      </Button>
                    ) : (
                      <div className="flex gap-2">
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => deleteMutation.mutate(true)}
                          disabled={deleteMutation.isPending}
                        >
                          {t("draftDetailPage.confirmForceDelete")}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => { setDeleteConflict(null); setConfirmForceDelete(false); }}>
                          {t("common.cancel")}
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>}

      {showAddToCollection && (
        <AddToCollectionModal
          itemId={id!}
          itemType="draft"
          onAdd={addDraftToCollection}
          onRemove={removeDraftFromCollection}
          onClose={() => setShowAddToCollection(false)}
        />
      )}

      {showCreateProject && (
        <CreateProjectModal
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
          warpThreads={draft.warp_threads ?? 0}
          weftThreads={draft.weft_threads ?? 0}
          onClose={() => setShowPreviewModal(false)}
        />
      )}
      </div>
    </div>
  );
}
