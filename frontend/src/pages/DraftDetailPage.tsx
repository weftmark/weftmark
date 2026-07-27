import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useParams, useNavigate, Link } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { useQuery, useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { getDraft, deleteDraft, archiveDraft, unarchiveDraft, generateLiftplan, overrideDraftMetadata, setDraftWarpLength, setDraftWeavingWidth, setDraftEpi, updateDraft, previewUrl, previewSvgUrl, downloadWif, downloadWifModified, type ColorStat, type DeleteConflict, type DraftDetail } from "@/api/drafts";
import { TagInput } from "@/components/ui/TagInput";
import { TagChips } from "@/components/ui/TagChips";
import { addDraftToCollection, removeDraftFromCollection } from "@/api/collections";
import { AddToCollectionModal } from "@/components/collections/AddToCollectionModal";
import { listProjects, type ProjectSummary } from "@/api/projects";
import { ProjectSummaryList } from "@/components/projects/ProjectSummaryList";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { DraftPreviewModal } from "@/components/drafts/DraftPreviewModal";
import { DeleteConflictPanel } from "@/components/DeleteConflictPanel";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit, convertLength, formatLength, formatApproxLength, type LengthUnit } from "@/lib/units";
import { nearestColorName } from "@/lib/colorName";
import { getReedRecommendation } from "@/lib/reedRecommendation";
import { SuperuserInspectionBanner } from "@/components/ui/SuperuserInspectionBanner";

// ---------------------------------------------------------------------------
// Pure derived-value helpers
// ---------------------------------------------------------------------------

interface WeavingWidthInfo {
  weavingWidthCm: number | null;
  weavingWidthSource: "override" | "wif" | "calculated" | null;
}

function computeWeavingWidth(draft: DraftDetail): WeavingWidthInfo {
  const weavingWidthCm =
    draft.weaving_width_override_cm ??
    draft.wif_measurements?.weft_length ??
    (draft.warp_threads != null && draft.wif_measurements?.warp_spacing != null
      ? draft.warp_threads * draft.wif_measurements.warp_spacing
      : null);

  let weavingWidthSource: WeavingWidthInfo["weavingWidthSource"] = null;
  if (draft.weaving_width_override_cm != null) weavingWidthSource = "override";
  else if (draft.wif_measurements?.weft_length != null) weavingWidthSource = "wif";
  else if (draft.warp_threads != null && draft.wif_measurements?.warp_spacing != null) weavingWidthSource = "calculated";

  return { weavingWidthCm, weavingWidthSource };
}

interface EpiInfo {
  resolvedEpi: number | null;
  epiSource: "override" | "spacing" | "calculated" | null;
}

function computeEpi(draft: DraftDetail, weavingWidthCm: number | null): EpiInfo {
  const epiFromSpacing =
    draft.wif_measurements?.warp_spacing != null && draft.wif_measurements.warp_spacing > 0
      ? Math.round((2.54 / draft.wif_measurements.warp_spacing) * 10) / 10
      : null;
  const epiFromWidthAndCount =
    weavingWidthCm != null && weavingWidthCm > 0 && draft.warp_threads != null
      ? Math.round((draft.warp_threads / (weavingWidthCm / 2.54)) * 10) / 10
      : null;
  const resolvedEpi = draft.epi_override ?? epiFromSpacing ?? epiFromWidthAndCount;

  let epiSource: EpiInfo["epiSource"] = null;
  if (draft.epi_override != null) epiSource = "override";
  else if (epiFromSpacing != null) epiSource = "spacing";
  else if (epiFromWidthAndCount != null) epiSource = "calculated";

  return { resolvedEpi, epiSource };
}

// ---------------------------------------------------------------------------
// Header / tags
// ---------------------------------------------------------------------------

function DraftTagsEditor({
  draftId,
  tags,
  isReadOnly,
}: {
  readonly draftId: string;
  readonly tags: string[] | null;
  readonly isReadOnly: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editingTags, setEditingTags] = useState(false);
  const [pendingTags, setPendingTags] = useState<string[]>([]);

  const tagsMutation = useMutation({
    mutationFn: (next: string[]) => updateDraft(draftId, { tags: next }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditingTags(false);
    },
  });

  if (editingTags) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-64">
          <TagInput tags={pendingTags} onChange={setPendingTags} />
        </div>
        <Button size="sm" onClick={() => tagsMutation.mutate(pendingTags)} disabled={tagsMutation.isPending}>
          {tagsMutation.isPending ? t("draftDetailPage.saving") : t("common.save")}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setEditingTags(false)}>
          {t("common.cancel")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {tags && tags.length > 0 && <TagChips tags={tags} max={10} />}
      {!isReadOnly && (
        <button
          type="button"
          onClick={() => { setPendingTags(tags ?? []); setEditingTags(true); }}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {tags && tags.length > 0 ? t("draftDetailPage.editTags") : t("draftDetailPage.addTags")}
        </button>
      )}
    </div>
  );
}

function LintStatus({ errors, warnings }: { readonly errors: string[]; readonly warnings: string[] }) {
  const { t } = useTranslation();
  return (
    <>
      {errors.length > 0 && (
        <div className="rounded-md bg-destructive/10 p-4 space-y-1">
          <p className="text-sm font-medium text-destructive">{t("draftDetailPage.lintErrors")}</p>
          {errors.map((e) => (
            <p key={e} className="text-sm text-destructive">{e}</p>
          ))}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="rounded-md bg-muted p-4 space-y-1">
          <p className="text-sm font-medium">{t("draftDetailPage.lintWarnings")}</p>
          {warnings.map((w) => (
            <p key={w} className="text-sm text-muted-foreground">{w}</p>
          ))}
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Design info fields
// ---------------------------------------------------------------------------

function FileDownloadField({ draft }: { readonly draft: DraftDetail }) {
  const { t } = useTranslation();
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  async function doDownload(fn: (id: string, filename: string) => Promise<void>) {
    setDownloadError(null);
    setDownloading(true);
    try {
      await fn(draft.id, draft.wif_filename);
    } catch {
      setDownloadError(t("draftDetailPage.downloadFailed"));
    } finally {
      setDownloading(false);
    }
  }

  const originalLabel = draft.has_modified_file ? t("draftDetailPage.downloadOriginal") : t("draftDetailPage.download");

  return (
    <>
      <dt className="text-muted-foreground">{t("draftDetailPage.file")}</dt>
      <dd className="flex flex-wrap items-center gap-2">
        <span>{draft.wif_filename}</span>
        <button
          type="button"
          className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
          disabled={downloading}
          onClick={() => doDownload(downloadWif)}
        >
          {downloading ? t("draftDetailPage.downloading") : originalLabel}
        </button>
        {draft.has_modified_file && (
          <button
            type="button"
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:opacity-50"
            disabled={downloading}
            onClick={() => doDownload(downloadWifModified)}
          >
            {t("draftDetailPage.downloadModified")}
          </button>
        )}
      </dd>
      {downloadError && <dd className="col-span-2 text-xs text-destructive">{downloadError}</dd>}
    </>
  );
}

function WarpLengthField({
  draftId,
  draft,
  displayUnit,
}: {
  readonly draftId: string;
  readonly draft: DraftDetail;
  readonly displayUnit: LengthUnit;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState("");
  const [unit, setUnit] = useState<LengthUnit>(displayUnit);

  const mutation = useMutation({
    mutationFn: ({ length, unit: u }: { length: number; unit: LengthUnit }) => setDraftWarpLength(draftId, length, u),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditing(false);
      setInput("");
    },
  });

  return (
    <>
      <dt className="text-muted-foreground">{t("draftDetailPage.warpLength")}</dt>
      <dd>
        {editing ? (
          <form
            className="flex items-center gap-1.5 flex-wrap"
            onSubmit={(e) => {
              e.preventDefault();
              const v = Number.parseFloat(input);
              if (!Number.isNaN(v) && v > 0) mutation.mutate({ length: v, unit });
            }}
          >
            <input
              type="number"
              min={0}
              step="0.1"
              className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="e.g. 500"
              autoFocus
              required
            />
            <select
              className="rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={unit}
              onChange={(e) => setUnit(e.target.value as LengthUnit)}
            >
              <option value="cm">cm</option>
              <option value="in">in</option>
            </select>
            <Button type="submit" size="sm" disabled={mutation.isPending}>
              {mutation.isPending ? t("draftDetailPage.saving") : t("common.save")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => { setEditing(false); setInput(""); }}
              disabled={mutation.isPending}
            >
              {t("common.cancel")}
            </Button>
            {mutation.isError && (
              <span className="text-xs text-destructive">
                {mutation.error instanceof Error ? mutation.error.message : t("draftDetailPage.saveFailed")}
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
                    setInput(Number.parseFloat(v.toFixed(1)).toString());
                    setUnit(displayUnit);
                    setEditing(true);
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
                  onClick={() => { setInput(""); setUnit(displayUnit); setEditing(true); }}
                >
                  {t("draftDetailPage.set")}
                </button>
              </>
            )}
          </div>
        )}
      </dd>
      {draft.warp_length_cm == null && !editing && (
        <>
          <dt />
          <dd className="text-xs text-subdued">{t("draftDetailPage.warpLengthRequired")}</dd>
        </>
      )}
    </>
  );
}

function WeavingWidthDisplay({
  draft,
  displayUnit,
  weavingWidthCm,
  weavingWidthSource,
  onEdit,
}: {
  readonly draft: DraftDetail;
  readonly displayUnit: LengthUnit;
  readonly weavingWidthCm: number;
  readonly weavingWidthSource: WeavingWidthInfo["weavingWidthSource"];
  readonly onEdit: () => void;
}) {
  const { t } = useTranslation();
  return (
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
        onClick={onEdit}
      >
        {t("draftDetailPage.edit")}
      </button>
    </div>
  );
}

function WeavingWidthField({
  draftId,
  draft,
  displayUnit,
  weavingWidthCm,
  weavingWidthSource,
}: {
  readonly draftId: string;
  readonly draft: DraftDetail;
  readonly displayUnit: LengthUnit;
  readonly weavingWidthCm: number | null;
  readonly weavingWidthSource: WeavingWidthInfo["weavingWidthSource"];
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState("");
  const [unit, setUnit] = useState<LengthUnit>(displayUnit);

  const mutation = useMutation({
    mutationFn: ({ width, unit: u }: { width: number; unit: LengthUnit }) => setDraftWeavingWidth(draftId, width, u),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditing(false);
      setInput("");
    },
  });

  const startEdit = () => {
    if (weavingWidthCm != null) {
      setInput(String(Math.round(convertLength(weavingWidthCm, "cm", displayUnit) * 10) / 10));
    } else {
      setInput("");
    }
    setUnit(displayUnit);
    setEditing(true);
  };

  let body: ReactNode;
  if (editing) {
    body = (
      <div className="flex items-center gap-1 flex-wrap">
        <input
          type="number"
          min="0"
          step="0.1"
          className="w-20 rounded border border-border bg-input px-2 py-0.5 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <select
          className="rounded border border-border bg-input px-1 py-0.5 text-sm"
          value={unit}
          onChange={(e) => setUnit(e.target.value as LengthUnit)}
        >
          <option value="cm">cm</option>
          <option value="in">in</option>
        </select>
        <button
          type="button"
          className="text-xs text-accent underline underline-offset-2"
          onClick={() => {
            const v = Number.parseFloat(input);
            if (!Number.isNaN(v) && v > 0) mutation.mutate({ width: v, unit });
          }}
        >
          {t("common.save")}
        </button>
        <button
          type="button"
          className="text-xs text-muted-foreground underline underline-offset-2"
          onClick={() => { setEditing(false); setInput(""); }}
        >
          {t("common.cancel")}
        </button>
      </div>
    );
  } else if (weavingWidthCm != null) {
    body = (
      <WeavingWidthDisplay
        draft={draft}
        displayUnit={displayUnit}
        weavingWidthCm={weavingWidthCm}
        weavingWidthSource={weavingWidthSource}
        onEdit={startEdit}
      />
    );
  } else {
    body = (
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">{t("draftDetailPage.notSet")}</span>
        <button type="button" className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground" onClick={startEdit}>
          {t("draftDetailPage.set")}
        </button>
      </div>
    );
  }

  return (
    <>
      <dt className="text-muted-foreground">{t("draftDetailPage.weavingWidth")}</dt>
      <dd>{body}</dd>
    </>
  );
}

function ReedRecommendationRow({ resolvedEpi }: { readonly resolvedEpi: number }) {
  const { t } = useTranslation();
  const rec = getReedRecommendation(resolvedEpi);

  let body: ReactNode;
  if (rec.matches.length > 0) {
    body = (
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
    );
  } else if (rec.nearest) {
    body = (
      <p className="text-sm text-muted-foreground">
        {t("draftDetailPage.reedNoMatch", { epi: resolvedEpi, near1: rec.nearest[0], near2: rec.nearest[1] })}
      </p>
    );
  } else {
    body = <span className="text-sm text-muted-foreground">{t("draftDetailPage.reedNotFound")}</span>;
  }

  return (
    <>
      <dt className="text-muted-foreground">{t("draftDetailPage.reed")}</dt>
      <dd>{body}</dd>
    </>
  );
}

function EpiDisplay({
  resolvedEpi,
  epiSource,
  onEdit,
}: {
  readonly resolvedEpi: number;
  readonly epiSource: EpiInfo["epiSource"];
  readonly onEdit: () => void;
}) {
  const { t } = useTranslation();
  return (
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
      <button type="button" className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground" onClick={onEdit}>
        {t("draftDetailPage.edit")}
      </button>
    </div>
  );
}

function EpiField({
  draftId,
  resolvedEpi,
  epiSource,
}: {
  readonly draftId: string;
  readonly resolvedEpi: number | null;
  readonly epiSource: EpiInfo["epiSource"];
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState("");

  const mutation = useMutation({
    mutationFn: ({ epi }: { epi: number }) => setDraftEpi(draftId, epi),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
      setEditing(false);
      setInput("");
    },
  });

  let body: ReactNode;
  if (editing) {
    body = (
      <div className="flex items-center gap-1">
        <input
          type="number"
          min="0"
          step="0.5"
          className="w-20 rounded border border-border bg-input px-2 py-0.5 text-sm"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <span className="text-sm text-muted-foreground">{t("draftDetailPage.endsPerIn")}</span>
        <button
          type="button"
          className="text-xs text-accent underline underline-offset-2"
          onClick={() => {
            const v = Number.parseFloat(input);
            if (!Number.isNaN(v) && v > 0) mutation.mutate({ epi: v });
          }}
        >
          {t("common.save")}
        </button>
        <button
          type="button"
          className="text-xs text-muted-foreground underline underline-offset-2"
          onClick={() => { setEditing(false); setInput(""); }}
        >
          {t("common.cancel")}
        </button>
      </div>
    );
  } else if (resolvedEpi != null) {
    body = (
      <EpiDisplay
        resolvedEpi={resolvedEpi}
        epiSource={epiSource}
        onEdit={() => { setInput(String(resolvedEpi)); setEditing(true); }}
      />
    );
  } else {
    body = (
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">{t("draftDetailPage.notSet")}</span>
        <button
          type="button"
          className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          onClick={() => { setInput(""); setEditing(true); }}
        >
          {t("draftDetailPage.set")}
        </button>
      </div>
    );
  }

  return (
    <>
      <dt className="text-muted-foreground">{t("draftDetailPage.epi")}</dt>
      <dd>{body}</dd>
      {resolvedEpi != null && <ReedRecommendationRow resolvedEpi={resolvedEpi} />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------

function visibleWifColors(draft: DraftDetail) {
  const bothStatsPresent = draft.warp_color_stats !== null && draft.weft_color_stats !== null;
  if (!bothStatsPresent) return draft.wif_colors ?? [];
  return (draft.wif_colors ?? []).filter(
    (c) =>
      draft.weft_color_stats!.some((s) => s.hex === c.hex) ||
      draft.warp_color_stats!.some((s) => s.hex === c.hex),
  );
}

function ColorCountCell({ stat }: { readonly stat: ColorStat | undefined }) {
  if (!stat) return <span className="text-muted-foreground">—</span>;
  return <>{stat.count} <span className="text-muted-foreground">({stat.percentage}%)</span></>;
}

function ColorPaletteRow({
  color,
  weftStat,
  warpStat,
  weavingWidthCm,
  displayUnit,
}: {
  readonly color: NonNullable<DraftDetail["wif_colors"]>[number];
  readonly weftStat: ColorStat | undefined;
  readonly warpStat: ColorStat | undefined;
  readonly weavingWidthCm: number | null;
  readonly displayUnit: LengthUnit;
}) {
  const approxLengthCm = weftStat && weavingWidthCm != null ? weftStat.count * weavingWidthCm : null;
  return (
    <tr className="border-t border-border" title={`#${color.index}: RGB(${color.r}, ${color.g}, ${color.b})`}>
      <td className="py-1.5 pr-3">
        <div className="flex items-center gap-1.5">
          <div className="h-4 w-6 rounded-sm border border-border flex-shrink-0" style={{ backgroundColor: color.hex }} />
          <span className="font-mono text-muted-foreground">{color.hex}</span>
        </div>
      </td>
      <td className="py-1.5 pr-3 text-subdued">{nearestColorName(color.hex)}</td>
      <td className="py-1.5 pr-3 text-right tabular-nums"><ColorCountCell stat={warpStat} /></td>
      <td className="py-1.5 pr-3 text-right tabular-nums"><ColorCountCell stat={weftStat} /></td>
      {weavingWidthCm != null && (
        <td className="py-1.5 text-right tabular-nums text-subdued">
          {approxLengthCm != null ? `~${formatApproxLength(approxLengthCm, displayUnit)}` : <span className="text-muted-foreground">—</span>}
        </td>
      )}
    </tr>
  );
}

function ColorPaletteSection({
  draft,
  weavingWidthCm,
  displayUnit,
}: {
  readonly draft: DraftDetail;
  readonly weavingWidthCm: number | null;
  readonly displayUnit: LengthUnit;
}) {
  const { t } = useTranslation();
  if (!draft.wif_colors || draft.wif_colors.length === 0) return null;

  // When both stat arrays are populated, drop colors that appear in neither —
  // they are defined-as-default colors fully overridden by per-thread/per-pick assignments.
  const colors = visibleWifColors(draft);
  if (colors.length === 0) return null;

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
          {colors.map((c) => (
            <ColorPaletteRow
              key={c.index}
              color={c}
              weftStat={draft.weft_color_stats?.find((s) => s.hex === c.hex)}
              warpStat={draft.warp_color_stats?.find((s) => s.hex === c.hex)}
              weavingWidthCm={weavingWidthCm}
              displayUnit={displayUnit}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Features
// ---------------------------------------------------------------------------

function LiftTrackingRow({ draft }: { readonly draft: DraftDetail }) {
  const { t } = useTranslation();
  return (
    <>
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
    </>
  );
}

function GenerateLiftPlanBanner({
  draft,
  generateMutation,
}: {
  readonly draft: DraftDetail;
  readonly generateMutation: UseMutationResult<DraftDetail, Error, void, unknown>;
}) {
  const { t } = useTranslation();
  if (draft.has_liftplan || !draft.has_treadling || !draft.has_tieup) return null;
  return (
    <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2.5 text-sm">
      <p className="font-medium text-copper-on-subtle">{t("draftDetailPage.liftPlanNotInFile")}</p>
      <p className="mt-0.5 text-copper-on-subtle text-xs">{t("draftDetailPage.liftPlanCanBeComputed")}</p>
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
  );
}

type OverrideField = "num_treadles" | "num_shafts";

function MetadataMismatchBanner({
  field,
  declared,
  used,
  overrideInfo,
  overrideMutation,
}: {
  readonly field: OverrideField;
  readonly declared: number;
  readonly used: number;
  readonly overrideInfo: { original: number | null } | undefined;
  readonly overrideMutation: UseMutationResult<DraftDetail, Error, { field: OverrideField; value: number }, unknown>;
}) {
  const { t } = useTranslation();
  const isTreadles = field === "num_treadles";
  const title = isTreadles ? t("draftDetailPage.treadleMismatch") : t("draftDetailPage.shaftMismatch");
  const desc = isTreadles
    ? t("draftDetailPage.treadleMismatchDesc", { numDeclared: declared, numUsed: used })
    : t("draftDetailPage.shaftMismatchDesc", { numDeclared: declared, numUsed: used });
  const setLabel = isTreadles ? t("draftDetailPage.setTreadles", { count: used }) : t("draftDetailPage.setShafts", { count: used });
  const isPendingThisField = overrideMutation.isPending && overrideMutation.variables?.field === field;

  return (
    <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-0.5 text-subdued text-xs">
        {desc}
        {overrideInfo
          ? " " + t("draftDetailPage.overriddenFrom", { original: overrideInfo.original })
          : " " + t("draftDetailPage.overrideToFix")}
      </p>
      {overrideMutation.isError && overrideMutation.variables?.field === field && (
        <p className="mt-1 text-xs text-destructive">
          {overrideMutation.error instanceof Error ? overrideMutation.error.message : t("draftDetailPage.overrideFailed")}
        </p>
      )}
      {!overrideInfo && (
        <Button
          size="sm"
          variant="outline"
          className="mt-2"
          onClick={() => overrideMutation.mutate({ field, value: used })}
          disabled={overrideMutation.isPending}
        >
          {isPendingThisField ? t("draftDetailPage.overriding") : setLabel}
        </Button>
      )}
    </div>
  );
}

function FeaturesSection({ draftId, draft }: { readonly draftId: string; readonly draft: DraftDetail }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const generateMutation = useMutation({
    mutationFn: () => generateLiftplan(draftId),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const overrideMutation = useMutation({
    mutationFn: ({ field, value }: { field: OverrideField; value: number }) => overrideDraftMetadata(draftId, field, value),
    onSuccess: (updated) => {
      queryClient.setQueryData(["draft", draftId], updated);
      queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  const featureRows: [string, boolean][] = [
    [t("draftDetailPage.threadingDiagram"), draft.has_threading],
    [t("draftDetailPage.tieUpGrid"), draft.has_tieup],
    [t("draftDetailPage.treadleTracking"), draft.has_treadling],
    [t("draftDetailPage.colorPalette"), draft.has_color_palette],
  ];

  const treadleMismatch =
    draft.effective_num_treadles != null && draft.num_treadles != null && draft.effective_num_treadles !== draft.num_treadles;
  const shaftMismatch =
    draft.effective_num_shafts != null && draft.num_shafts != null && draft.effective_num_shafts !== draft.num_shafts;

  return (
    <div className="space-y-3 border-t pt-4">
      <h2 className="text-base font-semibold">{t("draftDetailPage.features")}</h2>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        {featureRows.map(([label, available]) => (
          <>
            <dt key={`${label}-dt`} className="text-muted-foreground">{label}</dt>
            <dd key={`${label}-dd`} className={available ? "text-foreground" : "text-muted-foreground"}>
              {available ? t("draftDetailPage.featureAvailable") : t("draftDetailPage.featureNotInFile")}
            </dd>
          </>
        ))}
        <LiftTrackingRow draft={draft} />
      </dl>

      <GenerateLiftPlanBanner draft={draft} generateMutation={generateMutation} />

      {treadleMismatch && (
        <MetadataMismatchBanner
          field="num_treadles"
          declared={draft.num_treadles!}
          used={draft.effective_num_treadles!}
          overrideInfo={draft.metadata_overrides?.num_treadles}
          overrideMutation={overrideMutation}
        />
      )}

      {shaftMismatch && (
        <MetadataMismatchBanner
          field="num_shafts"
          declared={draft.num_shafts!}
          used={draft.effective_num_shafts!}
          overrideInfo={draft.metadata_overrides?.num_shafts}
          overrideMutation={overrideMutation}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Projects / preview
// ---------------------------------------------------------------------------

function ProjectsSection({
  projects,
  isReadOnly,
  onNewProject,
}: {
  readonly projects: ProjectSummary[];
  readonly isReadOnly: boolean;
  readonly onNewProject: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="border-t pt-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold">{t("draftDetailPage.projects")}</h2>
        <div className="flex items-center gap-3">
          {!isReadOnly && <Button size="sm" onClick={onNewProject}>{t("draftDetailPage.newProject")}</Button>}
          <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground">
            {t("draftDetailPage.allProjects")}
          </Link>
        </div>
      </div>
      <ProjectSummaryList projects={projects} />
    </div>
  );
}

function PreviewColumn({ draft, onOpenPreview }: { readonly draft: DraftDetail; readonly onOpenPreview: () => void }) {
  const { t } = useTranslation();
  return (
    <div>
      <h2 className="text-base font-semibold mb-3">{t("draftDetailPage.designPreview")}</h2>
      {draft.wif_filename ? (
        <button
          type="button"
          className="group w-full overflow-hidden rounded-lg border bg-card p-2 cursor-zoom-in text-left"
          onClick={onOpenPreview}
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
          <p className="text-sm text-muted-foreground">{t("draftDetailPage.previewUnavailable")}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Danger zone
// ---------------------------------------------------------------------------

function ArchiveControl({
  draft,
  draftId,
}: {
  readonly draft: DraftDetail;
  readonly draftId: string;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [confirmArchive, setConfirmArchive] = useState(false);

  const archiveMutation = useMutation({
    mutationFn: () => archiveDraft(draftId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft", draftId] }),
  });
  const unarchiveMutation = useMutation({
    mutationFn: () => unarchiveDraft(draftId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["draft", draftId] }),
  });

  return (
    <div className="rounded-md border border-border p-4 flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium">{draft.archived_at ? t("draftDetailPage.unarchiveDraft") : t("draftDetailPage.archiveDraft")}</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {draft.archived_at ? t("draftDetailPage.unarchiveNote") : t("draftDetailPage.archiveNote")}
        </p>
      </div>
      <div className="flex gap-2 shrink-0">
        {!confirmArchive ? (
          <Button variant="outline" size="sm" onClick={() => setConfirmArchive(true)}>
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
  );
}

function DeleteControl({ draftId }: { readonly draftId: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteConflict, setDeleteConflict] = useState<DeleteConflict | null>(null);
  const [confirmForceDelete, setConfirmForceDelete] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: (force: boolean) => deleteDraft(draftId, force),
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

  return (
    <div className="rounded-md border border-destructive/30 p-4 space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium">{t("draftDetailPage.deleteDraft")}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{t("draftDetailPage.deleteNote")}</p>
        </div>
        <div className="flex gap-2 shrink-0">
          {!confirmDelete && !deleteConflict && (
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => setConfirmDelete(true)}
            >
              {t("draftDetailPage.deleteDraft")}
            </Button>
          )}
          {confirmDelete && (
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
          )}
        </div>
      </div>

      {deleteConflict && (
        <DeleteConflictPanel
          conflict={deleteConflict}
          usedByMessage={t("draftDetailPage.usedByConflict", { count: deleteConflict.projects.length })}
          conflictNote={t("draftDetailPage.conflictNote")}
          confirmForceDelete={confirmForceDelete}
          onRequestForceDelete={() => setConfirmForceDelete(true)}
          forceDeleteLabel={t("draftDetailPage.forceDelete", { count: deleteConflict.projects.length })}
          triggerButtonClassName="text-destructive hover:text-destructive"
          onConfirmForceDelete={() => deleteMutation.mutate(true)}
          confirmForceDeleteLabel={t("draftDetailPage.confirmForceDelete")}
          busy={deleteMutation.isPending}
          onCancel={() => { setDeleteConflict(null); setConfirmForceDelete(false); }}
        />
      )}
    </div>
  );
}

function DangerZoneSection({ draft, draftId }: { readonly draft: DraftDetail; readonly draftId: string }) {
  const { t } = useTranslation();
  const [showDangerZone, setShowDangerZone] = useState(false);

  return (
    <div className="border-t pt-4">
      <button
        type="button"
        onClick={() => setShowDangerZone((v) => !v)}
        className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-destructive transition-colors"
      >
        <span>{t("draftDetailPage.dangerZone")}</span>
        <span>{showDangerZone ? "▲" : "▼"}</span>
      </button>
      {showDangerZone && (
        <div className="mt-3 space-y-3">
          <ArchiveControl draft={draft} draftId={draftId} />
          <DeleteControl draftId={draftId} />
        </div>
      )}
    </div>
  );
}

export function DraftDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthContext();
  const displayUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const [showCreateProject, setShowCreateProject] = useState(false);
  const [showAddToCollection, setShowAddToCollection] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);

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

  const { weavingWidthCm, weavingWidthSource } = computeWeavingWidth(draft);
  const { resolvedEpi, epiSource } = computeEpi(draft, weavingWidthCm);

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
            <AppIcons.ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium text-foreground">{draft.name}</span>
          </div>
          <DraftTagsEditor draftId={draft.id} tags={draft.tags} isReadOnly={isReadOnly} />
        </div>
        {!isReadOnly && (
          <Button size="sm" variant="outline" onClick={() => setShowAddToCollection(true)}>
            <AppIcons.Collections className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
            {t("draftDetailPage.addToCollection")}
          </Button>
        )}
      </div>

        <LintStatus errors={draft.lint_errors} warnings={draft.lint_warnings} />

        <div className="grid gap-6 lg:grid-cols-2">
          {/* Left column: Info + Features + Activities */}
          <div className="space-y-6">
            <div className="space-y-4">
              <h2 className="text-base font-semibold">{t("draftDetailPage.designInfo")}</h2>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                <FileDownloadField draft={draft} />
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
                <WarpLengthField draftId={draft.id} draft={draft} displayUnit={displayUnit} />
                <WeavingWidthField
                  draftId={draft.id}
                  draft={draft}
                  displayUnit={displayUnit}
                  weavingWidthCm={weavingWidthCm}
                  weavingWidthSource={weavingWidthSource}
                />
                <EpiField draftId={draft.id} resolvedEpi={resolvedEpi} epiSource={epiSource} />
              </dl>

              <ColorPaletteSection draft={draft} weavingWidthCm={weavingWidthCm} displayUnit={displayUnit} />
            </div>

            <FeaturesSection draftId={draft.id} draft={draft} />

            <ProjectsSection
              projects={draftProjects}
              isReadOnly={isReadOnly}
              onNewProject={() => setShowCreateProject(true)}
            />
          </div>

          {/* Right column: Preview */}
          <PreviewColumn draft={draft} onOpenPreview={() => setShowPreviewModal(true)} />
        </div>

        {!isReadOnly && <DangerZoneSection draft={draft} draftId={draft.id} />}

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
          warpThreads={draft.warp_threads ?? 0}
          weftThreads={draft.weft_threads ?? 0}
          onClose={() => setShowPreviewModal(false)}
        />
      )}
      </div>
    </div>
  );
}
