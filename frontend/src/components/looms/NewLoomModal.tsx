import { useState } from "react";
import { createLoom, type CreateLoomPayload, type LoomType, LOOM_TYPE_LABELS } from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

const today = () => new Date().toISOString().slice(0, 10);

const LOOM_TYPES: LoomType[] = ["floor_loom", "table_loom", "rigid_heddle", "inkle", "other"];

function showsShafts(t: LoomType) { return t === "floor_loom" || t === "table_loom" || t === "other"; }
function showsTreadles(t: LoomType) { return t === "floor_loom" || t === "other"; }
function showsHeddles(t: LoomType) { return t === "rigid_heddle" || t === "other"; }

export function NewLoomModal({ onSuccess, onClose }: Props) {
  const [loomType, setLoomType] = useState<LoomType>("floor_loom");
  const [manufacturer, setManufacturer] = useState("");
  const [modelName, setModelName] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [numShafts, setNumShafts] = useState("4");
  const [numTreadles, setNumTreadles] = useState("4");
  const [numHeddles, setNumHeddles] = useState("");
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
        loom_type: loomType,
        manufacturer,
        model_name: modelName,
        serial_number: serialNumber || undefined,
        supports_lift_tracking: supportsLift,
        supports_treadle_tracking: supportsTreadle,
        notes: notes || undefined,
        effective_date: effectiveDate,
        num_shafts: showsShafts(loomType) && numShafts ? parseInt(numShafts, 10) : undefined,
        num_treadles: showsTreadles(loomType) && numTreadles !== "" ? parseInt(numTreadles, 10) : undefined,
        num_heddles: showsHeddles(loomType) && numHeddles ? parseInt(numHeddles, 10) : undefined,
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
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg overflow-y-auto max-h-[90vh]">
        <h2 className="mb-4 text-lg font-semibold">New Loom</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Loom type */}
          <div>
            <label className="mb-1 block text-sm font-medium">Loom type</label>
            <select
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={loomType}
              onChange={(e) => setLoomType(e.target.value as LoomType)}
            >
              {LOOM_TYPES.map((t) => (
                <option key={t} value={t}>{LOOM_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>

          {/* Identity */}
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

          {/* Initial configuration */}
          <div>
            <label className="mb-1 block text-sm font-medium">Configuration as of</label>
            <input
              type="date"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={effectiveDate}
              onChange={(e) => setEffectiveDate(e.target.value)}
              required
            />
          </div>

          {/* Type-specific spec fields */}
          {(showsShafts(loomType) || showsTreadles(loomType) || showsHeddles(loomType)) && (
            <div className="grid grid-cols-2 gap-3">
              {showsShafts(loomType) && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Shafts</label>
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={numShafts}
                    onChange={(e) => setNumShafts(e.target.value)}
                    required={loomType !== "other"}
                  />
                </div>
              )}
              {showsTreadles(loomType) && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Treadles</label>
                  <input
                    type="number"
                    min={0}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={numTreadles}
                    onChange={(e) => setNumTreadles(e.target.value)}
                    required={loomType !== "other"}
                  />
                </div>
              )}
              {showsHeddles(loomType) && (
                <div>
                  <label className="mb-1 block text-sm font-medium">Heddles (optional)</label>
                  <input
                    type="number"
                    min={1}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={numHeddles}
                    onChange={(e) => setNumHeddles(e.target.value)}
                  />
                </div>
              )}
            </div>
          )}

          {/* Dimensions — available for all types except inkle */}
          {loomType !== "inkle" && (
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
          )}

          {/* Activity tracking */}
          <div className="space-y-2">
            <p className="text-sm font-medium">Activity tracking</p>
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
          </div>

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
