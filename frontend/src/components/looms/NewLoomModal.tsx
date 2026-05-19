import { useState, useEffect, useRef } from "react";
import {
  createLoom,
  searchLoomCatalog,
  type CreateLoomPayload,
  type LoomType,
  type LoomReferenceSummary,
  LOOM_TYPE_LABELS,
  SUPPORTED_LOOM_TYPES,
} from "@/api/looms";
import { Button } from "@/components/ui/button";
import { useAuthContext } from "@/context/AuthContext";
import { measurementSystemToUnit } from "@/lib/units";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

const ALL_LOOM_TYPES: LoomType[] = [
  "floor_loom", "table_loom", "rigid_heddle", "inkle",
  "dobby_floor_loom", "tapestry_loom", "rug_loom", "frame_loom", "other",
];

function showsShafts(t: LoomType) {
  return ["floor_loom", "table_loom", "dobby_floor_loom", "other"].includes(t);
}
function showsTreadles(t: LoomType) { return t === "floor_loom" || t === "dobby_floor_loom"; }
function showsHeddles(t: LoomType) { return t === "rigid_heddle" || t === "other"; }

function categoryToLoomType(cat: string): LoomType {
  const map: Record<string, LoomType> = {
    floor_loom: "floor_loom",
    table_loom: "table_loom",
    rigid_heddle: "rigid_heddle",
    inkle_loom: "inkle",
    dobby_floor_loom: "dobby_floor_loom",
    tapestry_loom: "tapestry_loom",
    rug_loom: "rug_loom",
    frame_loom: "frame_loom",
  };
  return map[cat] ?? "other";
}

export function NewLoomModal({ onSuccess, onClose }: Props) {
  const { user } = useAuthContext();
  const defaultUnit = measurementSystemToUnit(user?.measurement_system ?? "metric");
  const useInches = defaultUnit === "in";

  // Catalog search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<LoomReferenceSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [selectedRef, setSelectedRef] = useState<LoomReferenceSummary | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Form state
  const [loomType, setLoomType] = useState<LoomType>("floor_loom");
  const [manufacturer, setManufacturer] = useState("");
  const [modelName, setModelName] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [numShafts, setNumShafts] = useState("4");
  const [numTreadles, setNumTreadles] = useState("6");
  const [treadlesManuallySet, setTreadlesManuallySet] = useState(false);
  const [numHeddles, setNumHeddles] = useState("");
  const [weavingWidth, setWeavingWidth] = useState("");
  const [weavingWidthUnit, setWeavingWidthUnit] = useState<string>(defaultUnit);
  const [warpWaste, setWarpWaste] = useState("");
  const [warpWasteUnit, setWarpWasteUnit] = useState<string>(defaultUnit);
  const [effectiveDate, setEffectiveDate] = useState(today());
  const [notes, setNotes] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // When a ref is selected: available shaft/width options for pickers
  const shaftOptions = selectedRef?.shaft_count_options ?? null;
  const widthOptionsIn = selectedRef?.weaving_width_options_inches ?? null;
  const widthOptionsCm = selectedRef?.weaving_width_options_cm ?? null;
  const activeWidthOptions = useInches ? widthOptionsIn : (widthOptionsCm ?? widthOptionsIn);
  const treadleOptions = selectedRef?.treadle_count ?? null;

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Debounced catalog search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!searchQuery.trim() || searchQuery.length < 2) return;
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await searchLoomCatalog(searchQuery);
        setSearchResults(results);
        setShowResults(true);
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQuery]);

  const applyReference = (ref: LoomReferenceSummary) => {
    setSelectedRef(ref);
    setSearchQuery(`${ref.brand} ${ref.model_name}`);
    setShowResults(false);
    setManufacturer(ref.brand);
    setModelName(ref.model_name);
    const lt = categoryToLoomType(ref.loom_category);
    setLoomType(lt);
    setAcknowledged(false);
    setTreadlesManuallySet(false);

    // Pre-fill shaft/treadle: pick first option from arrays
    if (ref.shaft_count_options?.length) {
      const first = String(ref.shaft_count_options[0]);
      setNumShafts(first);
      if (ref.treadle_count?.length) {
        setNumTreadles(String(ref.treadle_count[0]));
      } else if (showsTreadles(lt)) {
        const s = parseInt(first, 10);
        setNumTreadles(String(s + 2));
      }
    }

    // Pre-fill width: pick first option
    if (useInches && ref.weaving_width_options_inches?.length) {
      setWeavingWidth(String(ref.weaving_width_options_inches[0]));
      setWeavingWidthUnit("in");
    } else if (!useInches && ref.weaving_width_options_cm?.length) {
      setWeavingWidth(String(ref.weaving_width_options_cm[0]));
      setWeavingWidthUnit("cm");
    } else if (ref.weaving_width_options_inches?.length) {
      setWeavingWidth(String(ref.weaving_width_options_inches[0]));
      setWeavingWidthUnit("in");
    }
  };

  const clearReference = () => {
    setSelectedRef(null);
    setSearchQuery("");
    setManufacturer("");
    setModelName("");
    setLoomType("floor_loom");
    setNumShafts("4");
    setNumTreadles("6");
    setWeavingWidth("");
    setAcknowledged(false);
    setTreadlesManuallySet(false);
  };

  const handleShaftOptionChange = (val: string) => {
    setNumShafts(val);
    if (!treadlesManuallySet && treadleOptions && shaftOptions) {
      const idx = shaftOptions.indexOf(parseInt(val, 10));
      if (idx !== -1 && treadleOptions[idx] != null) {
        setNumTreadles(String(treadleOptions[idx]));
        return;
      }
    }
    if (!treadlesManuallySet && showsTreadles(loomType)) {
      const s = parseInt(val, 10);
      if (!isNaN(s)) setNumTreadles(String(s + 2));
    }
  };

  const handleShaftsManual = (val: string) => {
    setNumShafts(val);
    if (loomType === "floor_loom" && !treadlesManuallySet) {
      const s = parseInt(val, 10);
      if (!isNaN(s)) setNumTreadles(String(s + 2));
    }
  };

  const handleTypeChange = (newType: LoomType) => {
    setLoomType(newType);
    setAcknowledged(false);
    setTreadlesManuallySet(false);
    if (newType === "floor_loom") {
      const s = parseInt(numShafts, 10);
      if (!isNaN(s)) setNumTreadles(String(s + 2));
    }
  };

  const isUnsupported = !SUPPORTED_LOOM_TYPES.has(loomType);

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
        loom_reference_id: selectedRef?.id,
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

          {/* Catalog typeahead */}
          <div ref={searchRef} className="relative">
            <label className="mb-1 block text-sm font-medium">
              Find your loom{" "}
              <span className="font-normal text-muted-foreground">(optional — start typing brand or model)</span>
            </label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={searchQuery}
              onChange={(e) => { const v = e.target.value; setSearchQuery(v); if (selectedRef) setSelectedRef(null); if (!v.trim() || v.length < 2) { setSearchResults([]); setShowResults(false); } }}
              placeholder="Schacht Baby Wolf, Ashford Jack Loom…"
              autoComplete="off"
            />
            {searching && (
              <p className="mt-1 text-xs text-muted-foreground">Searching…</p>
            )}
            {showResults && searchResults.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md max-h-56 overflow-y-auto">
                {searchResults.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className="w-full px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground flex flex-col"
                    onMouseDown={() => applyReference(r)}
                  >
                    <span className="font-medium">{r.brand} {r.model_name}</span>
                    <span className="text-xs text-muted-foreground">
                      {r.loom_category.replace(/_/g, " ")}
                      {r.shaft_count_options?.length ? ` · ${r.shaft_count_options.join("/")} shafts` : ""}
                      {r.origin_country ? ` · ${r.origin_country}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {showResults && searchResults.length === 0 && !searching && searchQuery.length >= 2 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md px-3 py-2">
                <p className="text-sm text-muted-foreground">No results — enter details manually below.</p>
              </div>
            )}
          </div>

          {selectedRef && (
            <div className="flex items-center justify-between rounded-md bg-muted px-3 py-2 text-sm">
              <span className="text-muted-foreground">
                Linked to catalog: <span className="font-medium text-foreground">{selectedRef.brand} {selectedRef.model_name}</span>
              </span>
              <button type="button" className="text-xs text-muted-foreground hover:text-foreground ml-2" onClick={clearReference}>
                Clear
              </button>
            </div>
          )}

          {/* Loom type */}
          <div>
            <label className="mb-1 block text-sm font-medium">Loom type</label>
            <select
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={loomType}
              onChange={(e) => handleTypeChange(e.target.value as LoomType)}
            >
              {ALL_LOOM_TYPES.map((t) => (
                <option key={t} value={t}>{LOOM_TYPE_LABELS[t]}</option>
              ))}
            </select>
          </div>

          {/* Unsupported type warning + acknowledgement */}
          {isUnsupported && (
            <div className="rounded-md border border-copper-subtle bg-copper-subtle px-3 py-3 text-sm space-y-2">
              <p className="font-medium text-copper-on-subtle">Project tracking not supported</p>
              <p className="text-xs text-copper-on-subtle">
                This loom type is not currently supported for project tracking. You can save it for documentation
                and it will be available if support is added later.
              </p>
              <label className="flex items-center gap-2 text-xs text-copper-on-subtle cursor-pointer">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(e) => setAcknowledged(e.target.checked)}
                />
                I understand this loom cannot be used for project tracking
              </label>
            </div>
          )}

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
                  {shaftOptions && shaftOptions.length > 1 ? (
                    <select
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={numShafts}
                      onChange={(e) => handleShaftOptionChange(e.target.value)}
                    >
                      {shaftOptions.map((s) => (
                        <option key={s} value={String(s)}>{s}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="number"
                      min={1}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={numShafts}
                      onChange={(e) => handleShaftsManual(e.target.value)}
                      required={loomType !== "other" && loomType !== "dobby_floor_loom"}
                    />
                  )}
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
                    onChange={(e) => { setNumTreadles(e.target.value); setTreadlesManuallySet(true); }}
                    required
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

          {/* Weaving width */}
          {loomType !== "inkle" && (
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Weaving width (optional)</label>
                {activeWidthOptions && activeWidthOptions.length > 1 ? (
                  <div className="flex gap-2">
                    <select
                      className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                      value={weavingWidth}
                      onChange={(e) => setWeavingWidth(e.target.value)}
                    >
                      <option value="">— select —</option>
                      {activeWidthOptions.map((w) => (
                        <option key={w} value={String(w)}>{w}</option>
                      ))}
                    </select>
                    <span className="flex items-center px-2 text-sm text-muted-foreground">
                      {useInches ? "in" : "cm"}
                    </span>
                  </div>
                ) : (
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
                )}
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
            <Button type="submit" disabled={loading || (isUnsupported && !acknowledged)}>
              {loading ? "Creating…" : "Create loom"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
