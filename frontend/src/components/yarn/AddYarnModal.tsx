import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { createYarn, getYarnProperties, weightBothUnits, type CreateYarnPayload } from "@/api/yarn";
import { Button } from "@/components/ui/button";
import { ColorPicker } from "@/components/ui/ColorPicker";

const WEIGHT_CATEGORIES = [
  "thread", "lace", "fingering", "sport", "dk",
  "worsted", "aran", "bulky", "super_bulky",
] as const;

const WEIGHT_LABELS: Record<string, string> = {
  thread: "Thread", lace: "Lace", fingering: "Fingering", sport: "Sport",
  dk: "DK", worsted: "Worsted", aran: "Aran", bulky: "Bulky", super_bulky: "Super Bulky",
};

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

export function AddYarnModal({ onSuccess, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [brand, setBrand] = useState("");
  const [name, setName] = useState("");
  const [weightCategory, setWeightCategory] = useState("");
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
  const [machineWashable, setMachineWashable] = useState<boolean | null>(null);
  const [selectedAttributeIds, setSelectedAttributeIds] = useState<Set<number>>(new Set());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const { data: propertyGroups = [] } = useQuery({
    queryKey: ["yarnProperties"],
    queryFn: getYarnProperties,
    staleTime: 60 * 60 * 1000,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const { oz, g } = weightBothUnits(unitWeight, unitWeightUnit);
      const payload: CreateYarnPayload = {
        brand: brand.trim(),
        name: name.trim(),
        weight_category: weightCategory || undefined,
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
        machine_washable: machineWashable,
        yarn_attribute_ids: selectedAttributeIds.size > 0 ? Array.from(selectedAttributeIds) : undefined,
      };
      const created = await createYarn(payload);
      onSuccess();
      navigate(`/yarn/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("addYarnModal.errorMessage"));
    } finally {
      setLoading(false);
    }
  };

  const toggleAttr = (id: number) => {
    setSelectedAttributeIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const f = "w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg border bg-background shadow-lg flex flex-col max-h-[90vh]">
        <div className="px-6 pt-6 pb-4 border-b">
          <h2 className="text-lg font-semibold">{t("addYarnModal.title")}</h2>
        </div>

        <form onSubmit={handleSubmit} className="overflow-y-auto px-6 py-4 space-y-4 flex-1">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">
                {t("addYarnModal.brandLabel")} <span className="text-destructive">*</span>
              </label>
              <input className={f} value={brand} onChange={(e) => setBrand(e.target.value)} placeholder={t("addYarnModal.brandPlaceholder")} required />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">
                {t("addYarnModal.nameLabel")} <span className="text-destructive">*</span>
              </label>
              <input className={f} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("addYarnModal.namePlaceholder")} required />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.weightCategoryLabel")}</label>
              <select className={f} value={weightCategory} onChange={(e) => setWeightCategory(e.target.value)}>
                <option value="">{t("addYarnModal.weightCategoryPlaceholder")}</option>
                {WEIGHT_CATEGORIES.map((w) => (
                  <option key={w} value={w}>{WEIGHT_LABELS[w]}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.weightNotationLabel")}</label>
              <input className={f} value={weightNotation} onChange={(e) => setWeightNotation(e.target.value)} placeholder={t("addYarnModal.weightNotationPlaceholder")} />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">{t("addYarnModal.fiberLabel")}</label>
            <input className={f} value={fiberContent} onChange={(e) => setFiberContent(e.target.value)} placeholder={t("addYarnModal.fiberPlaceholder")} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.colorNameLabel")}</label>
              <input className={f} value={colorName} onChange={(e) => setColorName(e.target.value)} placeholder={t("addYarnModal.colorNamePlaceholder")} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.colorSwatchLabel")}</label>
              <div className="flex items-center gap-2 pt-1">
                <input type="checkbox" id="has-color" checked={hasColor} onChange={(e) => setHasColor(e.target.checked)} />
                <label htmlFor="has-color" className="text-sm">{t("addYarnModal.setColorLabel")}</label>
                {hasColor && <ColorPicker value={colorHex} onChange={setColorHex} />}
              </div>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">{t("addYarnModal.machineWashableLabel")}</label>
            <div className="flex gap-4 pt-1">
              {([["yes", true], ["no", false], ["unknown", null]] as const).map(([labelKey, val]) => (
                <label key={labelKey} className="flex items-center gap-1.5 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="machine_washable"
                    checked={machineWashable === val}
                    onChange={() => setMachineWashable(val)}
                    className="accent-accent"
                  />
                  {t(`addYarnModal.machineWashable${labelKey.charAt(0).toUpperCase() + labelKey.slice(1)}`)}
                </label>
              ))}
            </div>
          </div>

          {propertyGroups.length > 0 && (
            <div>
              <label className="mb-2 block text-sm font-medium">{t("addYarnModal.propertiesLabel")}</label>
              <div className="space-y-2">
                {propertyGroups.map((group) => (
                  <div key={group.id}>
                    <p className="mb-1 text-xs font-medium text-muted-foreground uppercase tracking-wide">{group.name}</p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1">
                      {group.attributes.map((attr) => (
                        <label key={attr.id} className="flex items-center gap-1.5 text-sm cursor-pointer">
                          <input
                            type="checkbox"
                            checked={selectedAttributeIds.has(attr.id)}
                            onChange={() => toggleAttr(attr.id)}
                            className="accent-accent"
                          />
                          {attr.name}
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.yardageLabel")}</label>
              <input type="number" min={0} step="1" className={f} value={unitYardage} onChange={(e) => setUnitYardage(e.target.value)} placeholder="1680" />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.weightPerUnitLabel")}</label>
              <div className="flex gap-2">
                <input
                  type="number" min={0} step="0.1"
                  className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={unitWeight} onChange={(e) => setUnitWeight(e.target.value)}
                  placeholder={unitWeightUnit === "oz" ? "8.0" : "227"}
                />
                <select
                  className="rounded-md border border-input bg-background px-2 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                  value={unitWeightUnit} onChange={(e) => setUnitWeightUnit(e.target.value as "oz" | "g")}
                >
                  <option value="oz">oz</option>
                  <option value="g">g</option>
                </select>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.yardsPerPoundLabel")}</label>
              <input type="number" min={0} step="1" className={f} value={yardsPerPound} onChange={(e) => setYardsPerPound(e.target.value)} placeholder="3360" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.settMinLabel")}</label>
              <input type="number" min={1} className={f} value={settMin} onChange={(e) => setSettMin(e.target.value)} placeholder="20" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.settMaxLabel")}</label>
              <input type="number" min={1} className={f} value={settMax} onChange={(e) => setSettMax(e.target.value)} placeholder="30" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.purchaseSourceLabel")}</label>
              <input className={f} value={purchaseSource} onChange={(e) => setPurchaseSource(e.target.value)} placeholder={t("addYarnModal.purchaseSourcePlaceholder")} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">{t("addYarnModal.priceLabel")}</label>
              <input type="number" min={0} step="0.01" className={f} value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} placeholder="12.00" />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">{t("addYarnModal.purchaseDateLabel")}</label>
            <input type="date" className={f} value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">{t("addYarnModal.notesLabel")}</label>
            <textarea className={`${f} resize-none`} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          {error && <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
        </form>

        <div className="flex justify-end gap-2 px-6 py-4 border-t">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>{t("common.cancel")}</Button>
          <Button onClick={handleSubmit} disabled={loading || !brand.trim() || !name.trim()}>
            {loading ? t("addYarnModal.savingButton") : t("addYarnModal.saveButton")}
          </Button>
        </div>
      </div>
    </div>
  );
}
