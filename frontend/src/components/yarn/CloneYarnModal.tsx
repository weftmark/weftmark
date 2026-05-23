import { useState } from "react";
import { cloneYarn, type YarnDetail } from "@/api/yarn";
import { Button } from "@/components/ui/button";
import { ColorPicker } from "@/components/ui/ColorPicker";

interface Props {
  yarn: YarnDetail;
  onSuccess: (newId: string) => void;
  onClose: () => void;
}

export function CloneYarnModal({ yarn, onSuccess, onClose }: Props) {
  const [colorName, setColorName] = useState(yarn.color_name ?? "");
  const [colorHex, setColorHex] = useState(yarn.color_hex ?? "#ffffff");
  const [hasColor, setHasColor] = useState(!!yarn.color_hex);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const created = await cloneYarn(yarn.id, {
        color_name: colorName.trim() || undefined,
        color_hex: hasColor ? colorHex : undefined,
      });
      onSuccess(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clone failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="mb-1 text-lg font-semibold">Clone yarn</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Copying all details from <span className="font-medium">{yarn.brand} — {yarn.name}</span>. Change the color below, then save.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Color name</label>
            <input
              className={f}
              value={colorName}
              onChange={(e) => setColorName(e.target.value)}
              placeholder="e.g. Indigo"
              autoFocus
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Color swatch</label>
            <div className="flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                id="clone-has-color"
                checked={hasColor}
                onChange={(e) => setHasColor(e.target.checked)}
              />
              <label htmlFor="clone-has-color" className="text-sm">Set color</label>
              {hasColor && (
                <ColorPicker value={colorHex} onChange={setColorHex} />
              )}
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
            <Button type="submit" disabled={loading}>{loading ? "Cloning…" : "Create clone"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
