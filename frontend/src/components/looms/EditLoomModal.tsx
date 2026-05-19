import { useState } from "react";
import {
  updateLoom, type LoomDetail, type UpdateLoomPayload, type LoomType, LOOM_TYPE_LABELS, SUPPORTED_LOOM_TYPES,
} from "@/api/looms";
import { Button } from "@/components/ui/button";

interface Props {
  loom: LoomDetail;
  onSuccess: (updated: LoomDetail) => void;
  onClose: () => void;
}

const LOOM_TYPES: LoomType[] = ["floor_loom", "table_loom", "rigid_heddle", "inkle", "dobby_floor_loom", "tapestry_loom", "rug_loom", "frame_loom", "other"];

export function EditLoomModal({ loom, onSuccess, onClose }: Props) {
  const [loomType, setLoomType] = useState<LoomType>(loom.loom_type);
  const [manufacturer, setManufacturer] = useState(loom.manufacturer);
  const [modelName, setModelName] = useState(loom.model_name);
  const [serialNumber, setSerialNumber] = useState(loom.serial_number ?? "");
  const [purchaseDate, setPurchaseDate] = useState(loom.purchase_date ?? "");
  const [purchasePrice, setPurchasePrice] = useState(loom.purchase_price ?? "");
  const [vendor, setVendor] = useState(loom.vendor ?? "");
  const [notes, setNotes] = useState(loom.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const isUnsupported = !SUPPORTED_LOOM_TYPES.has(loomType);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const payload: UpdateLoomPayload = {
        loom_type: loomType,
        manufacturer,
        model_name: modelName,
        serial_number: serialNumber || undefined,
        purchase_date: purchaseDate || undefined,
        purchase_price: purchasePrice ? parseFloat(String(purchasePrice)) : undefined,
        vendor: vendor || undefined,
        notes: notes || undefined,
      };
      const updated = await updateLoom(loom.id, payload);
      onSuccess(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg overflow-y-auto max-h-[90vh]">
        <h2 className="mb-4 text-lg font-semibold">Edit loom</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
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

          {/* Unsupported type info banner */}
          {isUnsupported && (
            <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-2 text-xs text-copper-on-subtle">
              This loom type is not currently supported for project tracking. Projects cannot be created using this loom.
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Manufacturer</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={manufacturer}
                onChange={(e) => setManufacturer(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Model</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Serial number</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={serialNumber}
              onChange={(e) => setSerialNumber(e.target.value)}
              placeholder="optional"
            />
          </div>

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-muted-foreground">Purchase info</legend>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Purchase date</label>
                <input
                  type="date"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={purchaseDate}
                  onChange={(e) => setPurchaseDate(e.target.value)}
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Purchase price</label>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={purchasePrice}
                  onChange={(e) => setPurchasePrice(e.target.value)}
                  placeholder="0.00"
                />
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Purchased from</label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                value={vendor}
                onChange={(e) => setVendor(e.target.value)}
                placeholder="Vendor or store name"
              />
            </div>
          </fieldset>

          <div>
            <label className="mb-1 block text-sm font-medium">Notes</label>
            <textarea
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
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
              {loading ? "Saving…" : "Save changes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
