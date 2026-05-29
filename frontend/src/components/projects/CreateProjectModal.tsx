import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { createProject, completeProject, abandonProject, listProjects, ApiError, type ProjectSummary } from "@/api/projects";
import { listLooms, getLoom, SUPPORTED_LOOM_TYPES } from "@/api/looms";
import { Button } from "@/components/ui/button";
import { TagInput } from "@/components/ui/TagInput";
import { useTranslation } from "react-i18next";

interface Props {
  readonly onSuccess: (id: string) => void;
  readonly onClose: () => void;
}

const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

export function CreateProjectModal({ onSuccess, onClose }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [loomId, setLoomId] = useState("");
  const [loomVersionId, setLoomVersionId] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflictProject, setConflictProject] = useState<ProjectSummary | null>(null);

  const { data: looms = [] } = useQuery({ queryKey: ["looms"], queryFn: () => listLooms() });
  const { data: loomDetail } = useQuery({
    queryKey: ["loom", loomId],
    queryFn: () => getLoom(loomId),
    enabled: !!loomId,
  });

  const selectedLoom = looms.find((l) => l.id === loomId);
  const loomVersions = loomDetail?.versions ?? [];

  const handleLoomChange = (newLoomId: string) => {
    setLoomId(newLoomId);
    setLoomVersionId("");
    setConflictProject(null);
    setError(null);
  };

  const _buildPayload = () => ({
    name: name.trim(),
    loom_id: loomId || undefined,
    loom_version_id: loomVersionId || undefined,
    tags: tags.length ? tags : undefined,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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
        setError(err instanceof Error ? err.message : t("createProject.error.failed"));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResolveAndCreate = async (resolve: "complete" | "abandon") => {
    if (!conflictProject) return;
    setError(null);
    setLoading(true);
    try {
      if (resolve === "complete") {
        await completeProject(conflictProject.id, true);
      } else {
        await abandonProject(conflictProject.id);
      }
      const created = await createProject(_buildPayload());
      onSuccess(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("createProject.error.failed"));
      setConflictProject(null);
    } finally {
      setLoading(false);
    }
  };

  const canSubmit = name.trim() && !loading;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="px-6 pt-6 pb-4 border-b">
          <h2 className="text-lg font-semibold">{t("createProject.title")}</h2>
        </div>

        <form onSubmit={handleSubmit} className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          <div>
            <label className="mb-1 block text-sm font-medium">{t("createProject.name")} <span className="text-destructive">*</span></label>
            <input className={f} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("createProject.namePlaceholder")} required />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">{t("createProject.tags")} <span className="text-muted-foreground font-normal">({t("common.optional")})</span></label>
            <TagInput tags={tags} onChange={setTags} placeholder={t("createProject.tagsPlaceholder")} />
          </div>

          <div className="rounded-md border border-border bg-muted px-3 py-2.5 text-sm">
            <p className="font-medium text-foreground">{t("createProject.sequenceHint.title")}</p>
            <p className="mt-0.5 text-xs text-subdued">{t("createProject.sequenceHint.body")}</p>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">{t("createProject.loom")} <span className="text-muted-foreground font-normal">({t("common.optional")})</span></label>
            <select className={f} value={loomId} onChange={(e) => handleLoomChange(e.target.value)}>
              <option value="">{t("createProject.noLoom")}</option>
              {looms.filter((l) => SUPPORTED_LOOM_TYPES.has(l.loom_type)).map((l) => (
                <option key={l.id} value={l.id}>{l.manufacturer} {l.model_name}</option>
              ))}
            </select>
            {looms.some((l) => !SUPPORTED_LOOM_TYPES.has(l.loom_type)) && (
              <p className="mt-1 text-xs text-muted-foreground">{t("createProject.unsupportedLoomsHidden")}</p>
            )}
          </div>

          {selectedLoom && loomVersions.length > 1 && (
            <div>
              <label className="mb-1 block text-sm font-medium">{t("createProject.loomConfig")}</label>
              <select className={f} value={loomVersionId} onChange={(e) => setLoomVersionId(e.target.value)}>
                <option value="">{t("createProject.loomConfigLatest", { name: loomVersions.at(-1)?.name ?? `v${loomVersions.at(-1)?.version_number}` })}</option>
                {loomVersions.map((v) => (
                  <option key={v.id} value={v.id}>{v.name ?? `Version ${v.version_number}`}</option>
                ))}
              </select>
            </div>
          )}

          {conflictProject && (
            <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-3 text-sm space-y-2">
              <p className="font-medium text-copper-on-subtle">
                {t("createProject.conflict.title", { name: conflictProject.name })}
              </p>
              <p className="text-copper-on-subtle text-xs">
                {t("createProject.conflict.body")}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button type="button" size="sm" onClick={() => handleResolveAndCreate("complete")} disabled={loading}>
                  {loading ? t("common.working") : t("createProject.conflict.complete")}
                </Button>
                <Button type="button" size="sm" variant="outline" onClick={() => handleResolveAndCreate("abandon")} disabled={loading}>
                  {loading ? t("common.working") : t("createProject.conflict.abandon")}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => handleLoomChange("")} disabled={loading}>
                  {t("createProject.conflict.clearLoom")}
                </Button>
              </div>
            </div>
          )}
          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </form>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>{t("common.cancel")}</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {loading ? t("common.creating") : t("createProject.submit")}
          </Button>
        </div>
      </div>
    </div>
  );
}
