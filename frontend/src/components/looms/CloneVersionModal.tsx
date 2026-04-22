import { useState } from "react";
import { cloneVersion, type LoomVersion, type CloneVersionPayload } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  loomId: string;
  source: LoomVersion;
  onSuccess: (v: LoomVersion) => void;
  onClose: () => void;
}

const today = () => new Date().toISOString().slice(0, 10);

export function CloneVersionModal({ loomId, source, onSuccess, onClose }: Props) {
  const [name, setName] = useState("");
  const [effectiveDate, setEffectiveDate] = useState(today());
  const [description, setDescription] = useState("");
  const [includeAccessories, setIncludeAccessories] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const sourceName = source.name || `v${source.version_number}`;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const payload: CloneVersionPayload = {
        name: name || undefined,
        effective_date: effectiveDate,
        description: description || undefined,
        include_accessories: includeAccessories,
      };
      const created = await cloneVersion(loomId, source.id, payload);
      onSuccess(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clone");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="mb-1 text-lg font-semibold">Clone configuration</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Copying spec from <span className="font-medium">{sourceName}</span>
          {source.accessories.length > 0 && ` (${source.accessories.length} accessor${source.accessories.length === 1 ? "y" : "ies"})`}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Configuration name (optional)</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Without second warp beam"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Effective date</label>
            <input
              type="date"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Description (optional)</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What changed?"
            />
          </div>

          {source.accessories.length > 0 && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeAccessories}
                onChange={(e) => setIncludeAccessories(e.target.checked)}
              />
              Copy accessories from {sourceName}
            </label>
          )}

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Cloning…" : "Create clone"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
