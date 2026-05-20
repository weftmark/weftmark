import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  getCollection,
  updateCollection,
  deleteCollection,
  removeDraftFromCollection,
  removeProjectFromCollection,
  addDraftToCollection,
  addProjectToCollection,
  type DraftMember,
  type ProjectMember,
} from "@/api/collections";
import { listDrafts } from "@/api/drafts";
import { listProjects } from "@/api/projects";
import { previewUrl } from "@/api/drafts";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";

type SortKey = "name" | "added";

function SortControl({ value, onChange }: { value: SortKey; onChange: (v: SortKey) => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-1 text-xs text-muted-foreground">
      <span>{t("collectionDetail.sort.label")}</span>
      <button
        className={`px-1.5 py-0.5 rounded transition-colors ${value === "added" ? "bg-accent/20 text-accent font-medium" : "hover:text-foreground"}`}
        onClick={() => onChange("added")}
      >{t("collectionDetail.sort.dateAdded")}</button>
      <button
        className={`px-1.5 py-0.5 rounded transition-colors ${value === "name" ? "bg-accent/20 text-accent font-medium" : "hover:text-foreground"}`}
        onClick={() => onChange("name")}
      >{t("collectionDetail.sort.name")}</button>
    </div>
  );
}

function RemoveButton({ label, onConfirm }: { label: string; onConfirm: () => void }) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  if (confirming) {
    return (
      <div className="flex gap-1 shrink-0">
        <button
          className="rounded px-2 py-0.5 text-xs bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
          onClick={() => { setConfirming(false); onConfirm(); }}
        >{t("collectionDetail.remove.confirm")}</button>
        <button
          className="rounded px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setConfirming(false)}
        >{t("collectionDetail.remove.cancel")}</button>
      </div>
    );
  }
  return (
    <button
      className="shrink-0 text-muted-foreground hover:text-destructive transition-colors"
      title={`Remove ${label}`}
      onClick={() => setConfirming(true)}
    >
      <AppIcons.close className="h-3.5 w-3.5" />
    </button>
  );
}

function AddDraftModal({
  collectionId,
  existingDraftIds,
  onClose,
  onAdded,
}: {
  collectionId: string;
  existingDraftIds: Set<string>;
  onClose: () => void;
  onAdded: () => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const { data: allDrafts = [] } = useQuery({ queryKey: ["drafts"], queryFn: () => listDrafts() });
  const addMutation = useMutation({
    mutationFn: (draftId: string) => addDraftToCollection(collectionId, draftId),
    onSuccess: onAdded,
  });

  const filtered = allDrafts
    .filter((d) => !existingDraftIds.has(d.id))
    .filter((d) => !query || d.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card shadow-lg flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border">
          <h2 className="text-base font-semibold">{t("collectionDetail.drafts.modal.title")}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>
        <div className="px-4 py-3">
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder={t("collectionDetail.drafts.modal.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-1">
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">{t("collectionDetail.drafts.modal.empty")}</p>
          )}
          {filtered.map((d) => (
            <button
              key={d.id}
              className="w-full text-left rounded-md px-3 py-2 text-sm hover:bg-muted transition-colors flex items-center gap-2"
              onClick={() => addMutation.mutate(d.id)}
              disabled={addMutation.isPending}
            >
              <span className="flex-1 truncate">{d.name}</span>
              {d.num_shafts && <span className="text-xs text-muted-foreground shrink-0">{d.num_shafts}S</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function AddProjectModal({
  collectionId,
  existingProjectIds,
  onClose,
  onAdded,
}: {
  collectionId: string;
  existingProjectIds: Set<string>;
  onClose: () => void;
  onAdded: () => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const { data: allProjects = [] } = useQuery({ queryKey: ["projects"], queryFn: () => listProjects() });
  const addMutation = useMutation({
    mutationFn: (projectId: string) => addProjectToCollection(collectionId, projectId),
    onSuccess: onAdded,
  });

  const filtered = allProjects
    .filter((p) => !existingProjectIds.has(p.id))
    .filter((p) => !query || p.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card shadow-lg flex flex-col max-h-[80vh]">
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border">
          <h2 className="text-base font-semibold">{t("collectionDetail.projects.modal.title")}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>
        <div className="px-4 py-3">
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder={t("collectionDetail.projects.modal.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-1">
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">{t("collectionDetail.projects.modal.empty")}</p>
          )}
          {filtered.map((p) => (
            <button
              key={p.id}
              className="w-full text-left rounded-md px-3 py-2 text-sm hover:bg-muted transition-colors flex items-center gap-2"
              onClick={() => addMutation.mutate(p.id)}
              disabled={addMutation.isPending}
            >
              <span className="flex-1 truncate">{p.name}</span>
              <span className={`text-xs shrink-0 rounded px-1.5 py-0.5 ${
                p.status === "active" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                : "bg-muted text-muted-foreground"
              }`}>{p.status}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CollectionDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [draftSort, setDraftSort] = useState<SortKey>("added");
  const [projectSort, setProjectSort] = useState<SortKey>("added");
  const [showAddDraft, setShowAddDraft] = useState(false);
  const [showAddProject, setShowAddProject] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const { data: collection, isLoading, error } = useQuery({
    queryKey: ["collection", id],
    queryFn: () => getCollection(id!),
    enabled: !!id,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["collection", id] });
    queryClient.invalidateQueries({ queryKey: ["collections"] });
  };

  const removeDraftMutation = useMutation({
    mutationFn: (draftId: string) => removeDraftFromCollection(id!, draftId),
    onSuccess: invalidate,
  });

  const removeProjectMutation = useMutation({
    mutationFn: (projectId: string) => removeProjectFromCollection(id!, projectId),
    onSuccess: invalidate,
  });

  const updateMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) =>
      updateCollection(id!, { name: data.name, description: data.description || undefined }),
    onSuccess: () => { setEditing(false); invalidate(); },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteCollection(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections"] });
      navigate("/collections");
    },
  });

  if (isLoading) return <div className="flex h-screen items-center justify-center"><span className="text-sm text-muted-foreground">{t("common.loading")}</span></div>;
  if (error || !collection) return <div className="flex h-screen items-center justify-center"><span className="text-sm text-destructive">{t("collectionDetail.notFound")}</span></div>;

  function sortDrafts(drafts: DraftMember[]): DraftMember[] {
    return [...drafts].sort((a, b) =>
      draftSort === "name"
        ? a.name.localeCompare(b.name)
        : new Date(b.added_at).getTime() - new Date(a.added_at).getTime()
    );
  }

  function sortProjects(projects: ProjectMember[]): ProjectMember[] {
    return [...projects].sort((a, b) =>
      projectSort === "name"
        ? a.name.localeCompare(b.name)
        : new Date(b.added_at).getTime() - new Date(a.added_at).getTime()
    );
  }

  const existingDraftIds = new Set(collection.drafts.map((d) => d.id));
  const existingProjectIds = new Set(collection.projects.map((p) => p.id));

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="mb-1">
        <Link to="/collections" className="text-sm text-muted-foreground hover:text-foreground transition-colors">{t("collectionDetail.backLink")}</Link>
      </div>

      {editing ? (
        <div className="mb-6 space-y-3">
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-ring"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            autoFocus
          />
          <textarea
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            rows={2}
            placeholder={t("collectionDetail.descPlaceholder")}
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={() => updateMutation.mutate({ name: editName, description: editDesc })} disabled={updateMutation.isPending || !editName.trim()}>{t("collectionDetail.edit.save")}</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>{t("collectionDetail.edit.cancel")}</Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-4 mb-6">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold">{collection.name}</h1>
            {collection.description && <p className="mt-1 text-sm text-muted-foreground">{collection.description}</p>}
            {collection.tags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {collection.tags.map((tag) => (
                  <span key={tag} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{tag}</span>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2 shrink-0">
            <Button size="sm" variant="outline" onClick={() => { setEditName(collection.name); setEditDesc(collection.description ?? ""); setEditing(true); }}>
              <AppIcons.edit className="h-3.5 w-3.5" />
            </Button>
            {!confirmDelete ? (
              <Button size="sm" variant="outline" className="border-destructive/40 text-destructive hover:bg-destructive/10" onClick={() => setConfirmDelete(true)}>{t("collectionDetail.delete.button")}</Button>
            ) : (
              <div className="flex gap-1">
                <Button size="sm" variant="outline" className="border-destructive text-destructive hover:bg-destructive/10" onClick={() => deleteMutation.mutate()} disabled={deleteMutation.isPending}>{t("collectionDetail.delete.confirm")}</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>{t("collectionDetail.delete.cancel")}</Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Drafts section */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">{t("collectionDetail.drafts.heading", { count: collection.drafts.length })}</h2>
          <div className="flex items-center gap-3">
            {collection.drafts.length > 1 && <SortControl value={draftSort} onChange={setDraftSort} />}
            <Button size="sm" variant="outline" onClick={() => setShowAddDraft(true)}>{t("collectionDetail.drafts.addButton")}</Button>
          </div>
        </div>
        {collection.drafts.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm text-muted-foreground">{t("collectionDetail.drafts.empty")}</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {sortDrafts(collection.drafts).map((d) => (
              <div key={d.id} className="rounded-lg border border-border overflow-hidden">
                {d.has_preview && (
                  <div className="h-24 bg-muted overflow-hidden">
                    <AuthedImage src={previewUrl(d.id)} alt="" className="w-full h-full object-cover" />
                  </div>
                )}
                <div className="p-3 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link to={`/drafts/${d.id}`} className="text-sm font-medium hover:underline truncate block">{d.name}</Link>
                    {(d.num_shafts || d.num_treadles) && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {d.num_shafts != null && `${d.num_shafts}S`}
                        {d.num_shafts != null && d.num_treadles != null && " / "}
                        {d.num_treadles != null && `${d.num_treadles}T`}
                      </p>
                    )}
                  </div>
                  <RemoveButton label={d.name} onConfirm={() => removeDraftMutation.mutate(d.id)} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Projects section */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">{t("collectionDetail.projects.heading", { count: collection.projects.length })}</h2>
          <div className="flex items-center gap-3">
            {collection.projects.length > 1 && <SortControl value={projectSort} onChange={setProjectSort} />}
            <Button size="sm" variant="outline" onClick={() => setShowAddProject(true)}>{t("collectionDetail.projects.addButton")}</Button>
          </div>
        </div>
        {collection.projects.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm text-muted-foreground">{t("collectionDetail.projects.empty")}</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {sortProjects(collection.projects).map((p) => (
              <div key={p.id} className="rounded-lg border border-border p-3 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link to={`/projects/${p.id}`} className="text-sm font-medium hover:underline truncate block">{p.name}</Link>
                  <span className={`mt-1 inline-block rounded px-1.5 py-0.5 text-xs font-medium ${
                    p.status === "active" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                    : "bg-muted text-muted-foreground"
                  }`}>{p.status}</span>
                </div>
                <RemoveButton label={p.name} onConfirm={() => removeProjectMutation.mutate(p.id)} />
              </div>
            ))}
          </div>
        )}
      </div>

      {showAddDraft && (
        <AddDraftModal
          collectionId={id!}
          existingDraftIds={existingDraftIds}
          onClose={() => setShowAddDraft(false)}
          onAdded={() => { setShowAddDraft(false); invalidate(); }}
        />
      )}
      {showAddProject && (
        <AddProjectModal
          collectionId={id!}
          existingProjectIds={existingProjectIds}
          onClose={() => setShowAddProject(false)}
          onAdded={() => { setShowAddProject(false); invalidate(); }}
        />
      )}
    </div>
  );
}
