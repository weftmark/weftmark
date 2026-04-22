import { useState } from "react";
import { createLoom, type CreateLoomPayload } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

const today = () => new Date().toISOString().slice(0, 10);

export function NewLoomModal({ onSuccess, onClose }: Props) {
  const [manufacturer, setManufacturer] = useState("");
  const [modelName, setModelName] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [numShafts, setNumShafts] = useState(4);
  const [numTreadles, setNumTreadles] = useState(4);
  const [weavingWidth, setWeavingWidth] = useState("");
  const [weavingWidthUnit, setWeavingWidthUnit] = useState("cm");
  const [warpWaste, setWarpWaste] = useState("");
  const [warpWasteUnit, setWarpWasteUnit] = useState("cm");
  const [effectiveDate, setEffectiveDate] = useState(today());
  const [notes, setNotes] = useState("");
  const [supportsLift, setSupportsLift] = useState(false);
  const [supportsTreadle, setSupportsTreadle] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const payload: CreateLoomPayload = {
        manufacturer,
        model_name: modelName,
        serial_number: serialNumber || undefined,
        supports_lift_tracking: supportsLift,
        supports_treadle_tracking: supportsTreadle,
        notes: notes || undefined,
        effective_date: effectiveDate,
        num_shafts: numShafts,
        num_treadles: numTreadles,
        weaving_width: weavingWidth ? parseFloat(weavingWidth) : undefined,
        weaving_width_unit: weavingWidthUnit,
        warp_waste_allowance: warpWaste ? parseFloat(warpWaste) : undefined,
        warp_waste_unit: warpWasteUnit,
      };
      await createLoom(payload);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create loom");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg overflow-y-auto max-h-screen">
        <h2 className="mb-4 text-lg font-semibold">New Loom</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-muted-foreground">Identity</legend>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Manufacturer</label>
                <input
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={manufacturer}
                  onChange={(e) => setManufacturer(e.target.value)}
                  placeholder="Ashford"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Model</label>
                <input
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  placeholder="Table Loom 8"
                  required
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Serial number (optional)</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={serialNumber}
                onChange={(e) => setSerialNumber(e.target.value)}
                placeholder="SN-12345"
              />
            </div>
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-muted-foreground">Initial configuration</legend>
            <div>
              <label className="mb-1 block text-sm font-medium">As of date</label>
              <input
                type="date"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={effectiveDate}
                onChange={(e) => setEffectiveDate(e.target.value)}
                required
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
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-muted-foreground">Activity tracking</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={supportsLift}
                onChange={(e) => setSupportsLift(e.target.checked)}
              />
              Supports lift tracking
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={supportsTreadle}
                onChange={(e) => setSupportsTreadle(e.target.checked)}
              />
              Supports treadle tracking
            </label>
          </fieldset>

          <div>
            <label className="mb-1 block text-sm font-medium">Notes (optional)</label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              placeholder="Any additional notes…"
            />
          </div>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "Creating…" : "Create loom"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
