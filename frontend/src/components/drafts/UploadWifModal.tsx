import { useRef, useState } from "react";
import { uploadDraft } from "@/api/drafts";
import { Button } from "@/components/ui/button";
import { TagInput } from "@/components/ui/TagInput";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

export function UploadWifModal({ onSuccess, onClose }: Props) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setLoading(true);
    try {
      await uploadDraft(name, file, description || undefined, tags.length ? tags : undefined);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="mb-4 text-lg font-semibold">New Draft</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Draft name</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Weaving Draft"
              required
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Description (optional)</label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Notes about this design…"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Tags <span className="text-muted-foreground font-normal">(optional)</span></label>
            <TagInput tags={tags} onChange={setTags} placeholder="twill, cotton…" />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">WIF file</label>
            <input
              ref={fileRef}
              type="file"
              accept=".wif"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="w-full rounded-md border-2 border-dashed border-input bg-background px-4 py-5 text-sm transition-colors hover:border-ring hover:bg-muted focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {file ? (
                <span className="font-medium text-foreground">{file.name}</span>
              ) : (
                <span className="text-muted-foreground">
                  Drop a <span className="font-medium text-foreground">.wif</span> file here, or{" "}
                  <span className="font-medium text-primary underline underline-offset-2">browse</span>
                </span>
              )}
            </button>
          </div>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={!file || !name || loading}>
              {loading ? "Uploading…" : "Upload"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
