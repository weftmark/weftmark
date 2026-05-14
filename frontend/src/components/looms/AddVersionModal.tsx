import { useState } from "react";
import { addLoomVersion, type AddVersionPayload, type LoomType } from "@/api/looms";
import { Button } from "@/components/ui/button";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit } from "@/lib/units";

interface Props {
  loomId: string;
  loomType: LoomType;
  onSuccess: () => void;
  onClose: () => void;
}

const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

function showsShafts(t: LoomType) { return t === "floor_loom" || t === "table_loom" || t === "other"; }
function showsTreadles(t: LoomType) { return t === "floor_loom" || t === "other"; }
function showsHeddles(t: LoomType) { return t === "rigid_heddle" || t === "other"; }
function showsWarpWaste(t: LoomType) { return t !== "inkle"; }

export function AddVersionModal({ loomId, loomType, onSuccess, onClose }: Props) {
  const { user } = useAuthContext();
  const [versionName, setVersionName] = useState("");
  const [numShafts, setNumShafts] = useState("4");
  const [numTreadles, setNumTreadles] = useState("4");
  const [numHeddles, setNumHeddles] = useState("");
  const [warpWaste, setWarpWaste] = useState("");
  const [warpWasteUnit, setWarpWasteUnit] = useState<string>(measurementSystemToUnit(user?.measurement_system ?? "metric"));
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
        name: versionName || undefined,
        effective_date: effectiveDate,
        description: description || undefined,
        num_shafts: showsShafts(loomType) && numShafts ? parseInt(numShafts, 10) : undefined,
        num_treadles: showsTreadles(loomType) && numTreadles !== "" ? parseInt(numTreadles, 10) : undefined,
        num_heddles: showsHeddles(loomType) && numHeddles ? parseInt(numHeddles, 10) : undefined,
        warp_waste_allowance: showsWarpWaste(loomType) && warpWaste ? parseFloat(warpWaste) : undefined,
        warp_waste_unit: warpWasteUnit,
        weaving_width_unit: "cm",
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
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="mb-4 text-lg font-semibold">Add configuration version</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Configuration name (optional)</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={versionName}
              onChange={(e) => setVersionName(e.target.value)}
              placeholder="e.g. With second warp beam"
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
              placeholder="Added 4 shafts via expansion kit"
            />
          </div>

          {(showsShafts(loomType) || showsTreadles(loomType) || showsHeddles(loomType)) && (
            <div className="grid grid-cols-3 gap-3">
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

          {showsWarpWaste(loomType) && (
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
          )}

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
