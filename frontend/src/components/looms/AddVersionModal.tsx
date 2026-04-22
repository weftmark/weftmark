import { useState } from "react";
import { addLoomVersion, type AddVersionPayload } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  loomId: string;
  onSuccess: () => void;
  onClose: () => void;
}

const today = () => new Date().toISOString().slice(0, 10);

export function AddVersionModal({ loomId, onSuccess, onClose }: Props) {
  const [numShafts, setNumShafts] = useState(4);
  const [numTreadles, setNumTreadles] = useState(4);
  const [weavingWidth, setWeavingWidth] = useState("");
  const [weavingWidthUnit, setWeavingWidthUnit] = useState("cm");
  const [warpWaste, setWarpWaste] = useState("");
  const [warpWasteUnit, setWarpWasteUnit] = useState("cm");
  const [effectiveDate, setEffectiveDate] = useState(today());
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const payload: AddVersionPayload = {
        effective_date: effectiveDate,
        description: description || undefined,
        num_shafts: numShafts,
        num_treadles: numTreadles,
        weaving_width: weavingWidth ? parseFloat(weavingWidth) : undefined,
        weaving_width_unit: weavingWidthUnit,
        warp_waste_allowance: warpWaste ? parseFloat(warpWaste) : undefined,
        warp_waste_unit: warpWasteUnit,
      };
      await addLoomVersion(loomId, payload);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add version");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="mb-4 text-lg font-semibold">Add configuration version</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
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
              placeholder="Added 4 shafts via expansion kit"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Shafts</label>
              <input
                type="number"
                min={1}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={numShafts}
                onChange={(e) => setNumShafts(parseInt(e.target.value, 10))}
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Treadles</label>
              <input
                type="number"
                min={0}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={numTreadles}
                onChange={(e) => setNumTreadles(parseInt(e.target.value, 10))}
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Weaving width (optional)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={weavingWidth}
                  onChange={(e) => setWeavingWidth(e.target.value)}
                  placeholder="60"
                />
                <select
                  className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={weavingWidthUnit}
                  onChange={(e) => setWeavingWidthUnit(e.target.value)}
                >
                  <option value="cm">cm</option>
                  <option value="in">in</option>
                </select>
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Warp waste (optional)</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  min={0}
                  step="0.1"
                  className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={warpWaste}
                  onChange={(e) => setWarpWaste(e.target.value)}
                  placeholder="30"
                />
                <select
                  className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={warpWasteUnit}
                  onChange={(e) => setWarpWasteUnit(e.target.value)}
                >
                  <option value="cm">cm</option>
                  <option value="in">in</option>
                </select>
              </div>
            </div>
          </div>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Saving…" : "Add version"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
