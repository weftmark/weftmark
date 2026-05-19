import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listCollections, createCollection, type CollectionSummary } from "@/api/collections";
import { AppIcons } from "@/lib/icons";
import { Button } from "@/components/ui/button";

function NewCollectionModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addTag(raw: string) {
    const trimmed = raw.trim();
    if (trimmed && !tags.includes(trimmed)) setTags((t) => [...t, trimmed]);
    setTagInput("");
  }

  function handleTagKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(tagInput);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const finalTags = tagInput.trim() ? [...tags, tagInput.trim()] : tags;
      await createCollection({ name: name.trim(), description: description.trim() || undefined, tags: finalTags });
      onSuccess();
    } catch {
      setError("Failed to create collection.");
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold">New collection</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Spring scarves…"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description <span className="text-muted-foreground font-normal">(optional)</span></label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              rows={2}
              placeholder="A series of experiments…"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tags <span className="text-muted-foreground font-normal">(press Enter or comma to add)</span></label>
            <div className="flex flex-wrap gap-1.5 mb-1.5">
              {tags.map((t) => (
                <span key={t} className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs">
                  {t}
                  <button type="button" onClick={() => setTags((prev) => prev.filter((x) => x !== t))} className="text-muted-foreground hover:text-foreground">×</button>
                </span>
              ))}
            </div>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="Add a tag…"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleTagKey}
              onBlur={() => { if (tagInput.trim()) addTag(tagInput); }}
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
            <Button type="submit" size="sm" disabled={saving || !name.trim()}>
              {saving ? "Creating…" : "Create"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function CollectionCard({ collection }: { collection: CollectionSummary }) {
  return (
    <Link
      to={`/collections/${collection.id}`}
      className="rounded-lg border border-border hover:border-ring transition-colors block p-5"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium truncate">{collection.name}</p>
          {collection.description && (
            <p className="mt-0.5 text-sm text-muted-foreground line-clamp-2">{collection.description}</p>
          )}
        </div>
        <AppIcons.collections className="h-4 w-4 shrink-0 mt-0.5 text-muted-foreground" strokeWidth={1.75} />
      </div>
      {collection.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {collection.tags.map((t) => (
            <span key={t} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{t}</span>
          ))}
        </div>
      )}
      <div className="mt-3 flex gap-3 text-xs text-muted-foreground border-t border-border pt-2.5">
        <span>{collection.draft_count} {collection.draft_count === 1 ? "draft" : "drafts"}</span>
        <span>{collection.project_count} {collection.project_count === 1 ? "project" : "projects"}</span>
      </div>
    </Link>
  );
}

export function CollectionsPage() {
  const queryClient = useQueryClient();
  const [showNew, setShowNew] = useState(false);

  const { data: collections = [], isLoading, error } = useQuery({
    queryKey: ["collections"],
    queryFn: () => listCollections(),
  });

  function handleCreated() {
    setShowNew(false);
    queryClient.invalidateQueries({ queryKey: ["collections"] });
  }

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Collections</h1>
        <Button size="sm" onClick={() => setShowNew(true)}>New collection</Button>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">Failed to load collections.</p>}

      {!isLoading && collections.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">No collections yet. Group your drafts and projects into named explorations.</p>
          <Button className="mt-4" onClick={() => setShowNew(true)}>New collection</Button>
        </div>
      )}

      {collections.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {collections.map((c) => (
            <CollectionCard key={c.id} collection={c} />
          ))}
        </div>
      )}

      {showNew && (
        <NewCollectionModal onClose={() => setShowNew(false)} onSuccess={handleCreated} />
      )}
    </div>
  );
}
