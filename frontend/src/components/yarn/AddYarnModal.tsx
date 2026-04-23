import { useState } from "react";
import { createYarn, weightBothUnits, type CreateYarnPayload } from "@/api/yarn";
import { Button } from "@/components/ui/button";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

export function AddYarnModal({ onSuccess, onClose }: Props) {
  const [brand, setBrand] = useState("");
  const [name, setName] = useState("");
  const [weightNotation, setWeightNotation] = useState("");
  const [fiberContent, setFiberContent] = useState("");
  const [colorName, setColorName] = useState("");
  const [colorHex, setColorHex] = useState("#ffffff");
  const [hasColor, setHasColor] = useState(false);
  const [unitYardage, setUnitYardage] = useState("");
  const [unitWeight, setUnitWeight] = useState("");
  const [unitWeightUnit, setUnitWeightUnit] = useState<"oz" | "g">("oz");
  const [yardsPerPound, setYardsPerPound] = useState("");
  const [settMin, setSettMin] = useState("");
  const [settMax, setSettMax] = useState("");
  const [purchaseSource, setPurchaseSource] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");
  const [purchaseDate, setPurchaseDate] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { oz, g } = weightBothUnits(unitWeight, unitWeightUnit);
      const payload: CreateYarnPayload = {
        brand: brand.trim(),
        name: name.trim(),
        weight_notation: weightNotation.trim() || undefined,
        fiber_content: fiberContent.trim() || undefined,
        color_name: colorName.trim() || undefined,
        color_hex: hasColor ? colorHex : undefined,
        unit_yardage: unitYardage ? parseFloat(unitYardage) : undefined,
        unit_weight_oz: oz,
        unit_weight_g: g,
        yards_per_pound: yardsPerPound ? parseFloat(yardsPerPound) : undefined,
        sett_min: settMin ? parseInt(settMin, 10) : undefined,
        sett_max: settMax ? parseInt(settMax, 10) : undefined,
        purchase_source: purchaseSource.trim() || undefined,
        purchase_price: purchasePrice ? parseFloat(purchasePrice) : undefined,
        purchase_date: purchaseDate || undefined,
        notes: notes.trim() || undefined,
      };
      await createYarn(payload);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add yarn");
    } finally {
      setLoading(false);
    }
  };

  const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="px-6 pt-6 pb-4 border-b">
          <h2 className="text-lg font-semibold">Add yarn</h2>
        </div>

        <form onSubmit={handleSubmit} className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Brand / Manufacturer <span className="text-destructive">*</span></label>
              <input className={f} value={brand} onChange={(e) => setBrand(e.target.value)} placeholder="Maurice Brassard" required />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Product name <span className="text-destructive">*</span></label>
              <input className={f} value={name} onChange={(e) => setName(e.target.value)} placeholder="Cotton 8/2" required />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Weight notation</label>
              <input className={f} value={weightNotation} onChange={(e) => setWeightNotation(e.target.value)} placeholder="8/2" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Fiber content</label>
              <input className={f} value={fiberContent} onChange={(e) => setFiberContent(e.target.value)} placeholder="100% Cotton" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Color name</label>
              <input className={f} value={colorName} onChange={(e) => setColorName(e.target.value)} placeholder="Natural" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Color swatch</label>
              <div className="flex items-center gap-2 pt-1">
                <input type="checkbox" id="has-color" checked={hasColor} onChange={(e) => setHasColor(e.target.checked)} />
                <label htmlFor="has-color" className="text-sm">Set color</label>
                {hasColor && (
                  <input type="color" value={colorHex} onChange={(e) => setColorHex(e.target.value)} className="h-8 w-12 rounded border border-input cursor-pointer" />
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Yardage / unit</label>
              <input type="number" min={0} step="1" className={f} value={unitYardage} onChange={(e) => setUnitYardage(e.target.value)} placeholder="1680" />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium">Weight / unit</label>
              <div className="flex gap-2">
                <input type="number" min={0} step="0.1" className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={unitWeight} onChange={(e) => setUnitWeight(e.target.value)} placeholder={unitWeightUnit === "oz" ? "8.0" : "227"} />
                <select className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring" value={unitWeightUnit} onChange={(e) => setUnitWeightUnit(e.target.value as "oz" | "g")}>
                  <option value="oz">oz</option>
                  <option value="g">g</option>
                </select>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Yards / pound</label>
              <input type="number" min={0} step="1" className={f} value={yardsPerPound} onChange={(e) => setYardsPerPound(e.target.value)} placeholder="3360" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Sett min (epi)</label>
              <input type="number" min={1} className={f} value={settMin} onChange={(e) => setSettMin(e.target.value)} placeholder="20" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Sett max (epi)</label>
              <input type="number" min={1} className={f} value={settMax} onChange={(e) => setSettMax(e.target.value)} placeholder="30" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium">Purchase source</label>
              <input className={f} value={purchaseSource} onChange={(e) => setPurchaseSource(e.target.value)} placeholder="The Woolery" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Price / unit</label>
              <input type="number" min={0} step="0.01" className={f} value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} placeholder="12.00" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Purchase date</label>
            <input type="date" className={f} value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Notes</label>
            <textarea className={`${f} resize-none`} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </form>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={loading || !brand.trim() || !name.trim()}>
            {loading ? "Saving…" : "Add yarn"}
          </Button>
        </div>
      </div>
    </div>
  );
}
