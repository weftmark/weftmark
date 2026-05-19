import { useState, useRef, useEffect } from "react";
import {
  searchLoomCatalog,
  updateLoom,
  linkLoomReference,
  updateVersion,
  type LoomDetail,
  type LoomReferenceSummary,
  type LoomType,
  type UpdateVersionPayload,
  LOOM_TYPE_LABELS,
} from "@/api/looms";
import { Button } from "@/components/ui/button";

type Step = "search" | "configure" | "confirm";

// ---------- helpers ----------

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

function showsShafts(t: LoomType) {
  return ["floor_loom", "table_loom", "dobby_floor_loom", "other"].includes(t);
}

function showsTreadles(t: LoomType) {
  return t === "floor_loom" || t === "dobby_floor_loom";
}

interface WidthOption {
  label: string;
  value: string;
  unit: "cm" | "in";
}

function buildWidthOptions(ref: LoomReferenceSummary): WidthOption[] {
  const cm = ref.weaving_width_options_cm;
  const inches = ref.weaving_width_options_inches;
  if (!cm?.length && !inches?.length) return [];
  if (cm?.length) {
    const inArr =
      inches?.length === cm.length
        ? inches
        : cm.map((c) => Math.round((c / 2.54) * 10) / 10);
    return cm.map((c, i) => ({
      label: `${c} cm (${inArr[i]} in)`,
      value: String(c),
      unit: "cm",
    }));
  }
  const cmArr = inches!.map((i) => Math.round(i * 2.54 * 10) / 10);
  return inches!.map((inch, i) => ({
    label: `${inch} in (${cmArr[i]} cm)`,
    value: String(inch),
    unit: "in",
  }));
}

function closestIdx(options: number[], target: number | null | undefined): number {
  if (!options.length || target == null) return 0;
  let best = 0;
  let bestDiff = Math.abs(options[0] - target);
  for (let i = 1; i < options.length; i++) {
    const diff = Math.abs(options[i] - target);
    if (diff < bestDiff) {
      best = i;
      bestDiff = diff;
    }
  }
  return best;
}

function deriveTreadles(
  shaftVal: number | null,
  shaftOptions: number[],
  treadleOptions: number[],
  loomType: LoomType,
): number | null {
  if (!showsTreadles(loomType) || shaftVal == null) return null;
  if (treadleOptions.length > 0 && shaftOptions.length > 0) {
    const idx = shaftOptions.indexOf(shaftVal);
    if (idx !== -1 && treadleOptions[idx] != null) return treadleOptions[idx];
  }
  return shaftVal + 2;
}

// ---------- component ----------

interface Props {
  loom: LoomDetail;
  onSuccess: () => void;
  onClose: () => void;
}

export function LinkToCatalogModal({ loom, onSuccess, onClose }: Props) {
  const [step, setStep] = useState<Step>("search");

  // Search state — displayQuery shown in input, searchQuery triggers API
  const [displayQuery, setDisplayQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<LoomReferenceSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const [selectedRef, setSelectedRef] = useState<LoomReferenceSummary | null>(null);
  const [selectedShaftIdx, setSelectedShaftIdx] = useState(0);
  const [selectedWidthIdx, setSelectedWidthIdx] = useState(0);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchContainerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived values from selection
  const newLoomType: LoomType = selectedRef
    ? categoryToLoomType(selectedRef.loom_category)
    : loom.loom_type;
  const shaftOptions: number[] = selectedRef?.shaft_count_options ?? [];
  const treadleOptions: number[] = selectedRef?.treadle_count ?? [];
  const widthOptions: WidthOption[] = selectedRef ? buildWidthOptions(selectedRef) : [];
  const selectedShafts: number | null = shaftOptions[selectedShaftIdx] ?? null;
  const derivedTreadles = deriveTreadles(
    selectedShafts,
    shaftOptions,
    treadleOptions,
    newLoomType,
  );
  const selectedWidthOpt: WidthOption | null = widthOptions[selectedWidthIdx] ?? null;

  // Debounced search — only fires when searchQuery changes (not displayQuery).
  // Clearing results when the query is short is handled in handleInputChange.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!searchQuery.trim() || searchQuery.length < 2) return;
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await searchLoomCatalog(searchQuery);
        setResults(data);
        setShowResults(true);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setShowResults(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  function handleInputChange(val: string) {
    setDisplayQuery(val);
    setSearchQuery(val); // triggers search effect
    if (selectedRef) setSelectedRef(null);
    if (!val.trim() || val.length < 2) {
      setResults([]);
      setShowResults(false);
    }
  }

  function handleSelectRef(ref: LoomReferenceSummary) {
    setSelectedRef(ref);
    // Update display only — do NOT set searchQuery so the useEffect doesn't re-fire
    setDisplayQuery(`${ref.brand} ${ref.model_name}`);
    setShowResults(false);

    const lt = categoryToLoomType(ref.loom_category);
    const sOpts = ref.shaft_count_options ?? [];
    const wOpts = buildWidthOptions(ref);

    // Auto-match shaft to current version
    setSelectedShaftIdx(closestIdx(sOpts, loom.current_version?.num_shafts));

    // Auto-match width to current version (convert units if needed)
    if (wOpts.length > 0 && loom.current_version?.weaving_width) {
      const curVal = parseFloat(loom.current_version.weaving_width);
      const curUnit = loom.current_version.weaving_width_unit as "cm" | "in";
      const targetUnit = wOpts[0].unit;
      const converted =
        curUnit === targetUnit
          ? curVal
          : curUnit === "cm"
            ? curVal / 2.54
            : curVal * 2.54;
      setSelectedWidthIdx(closestIdx(wOpts.map((o) => parseFloat(o.value)), converted));
    } else {
      setSelectedWidthIdx(0);
    }

    // Skip configure step if nothing to configure
    const hasDropdowns =
      (showsShafts(lt) && sOpts.length > 1) || wOpts.length > 1;
    setStep(hasDropdowns ? "configure" : "confirm");
  }

  // Diff rows for confirm step
  const cv = loom.current_version;

  interface DiffRow {
    label: string;
    oldVal: string;
    newVal: string;
    changed: boolean;
  }

  const diffRows: DiffRow[] = selectedRef
    ? [
        {
          label: "Manufacturer",
          oldVal: loom.manufacturer,
          newVal: selectedRef.brand,
          changed: loom.manufacturer !== selectedRef.brand,
        },
        {
          label: "Model",
          oldVal: loom.model_name,
          newVal: selectedRef.model_name,
          changed: loom.model_name !== selectedRef.model_name,
        },
        {
          label: "Loom type",
          oldVal: LOOM_TYPE_LABELS[loom.loom_type] ?? loom.loom_type,
          newVal: LOOM_TYPE_LABELS[newLoomType] ?? newLoomType,
          changed: loom.loom_type !== newLoomType,
        },
        ...(cv && showsShafts(newLoomType) && selectedShafts != null
          ? [
              {
                label: "Shafts",
                oldVal: cv.num_shafts != null ? String(cv.num_shafts) : "—",
                newVal: String(selectedShafts),
                changed: cv.num_shafts !== selectedShafts,
              },
            ]
          : []),
        ...(cv && showsTreadles(newLoomType) && derivedTreadles != null
          ? [
              {
                label: "Treadles",
                oldVal: cv.num_treadles != null ? String(cv.num_treadles) : "—",
                newVal: String(derivedTreadles),
                changed: cv.num_treadles !== derivedTreadles,
              },
            ]
          : []),
        ...(cv && selectedWidthOpt != null
          ? [
              {
                label: "Weaving width",
                oldVal: cv.weaving_width
                  ? `${parseFloat(cv.weaving_width)} ${cv.weaving_width_unit}`
                  : "—",
                newVal: selectedWidthOpt.label,
                changed:
                  !cv.weaving_width ||
                  parseFloat(cv.weaving_width) !== parseFloat(selectedWidthOpt.value) ||
                  cv.weaving_width_unit !== selectedWidthOpt.unit,
              },
            ]
          : []),
      ]
    : [];

  const hasChanges = diffRows.some((r) => r.changed);

  async function handleSave() {
    if (!selectedRef) return;
    setSaving(true);
    setError(null);
    try {
      await updateLoom(loom.id, {
        manufacturer: selectedRef.brand,
        model_name: selectedRef.model_name,
        loom_type: newLoomType,
      });
      await linkLoomReference(loom.id, selectedRef.id);

      if (cv) {
        const versionPayload: UpdateVersionPayload = {};
        if (showsShafts(newLoomType) && selectedShafts != null) {
          versionPayload.num_shafts = selectedShafts;
        }
        if (showsTreadles(newLoomType) && derivedTreadles != null) {
          versionPayload.num_treadles = derivedTreadles;
        }
        if (selectedWidthOpt != null) {
          versionPayload.weaving_width = parseFloat(selectedWidthOpt.value);
          versionPayload.weaving_width_unit = selectedWidthOpt.unit;
        }
        if (Object.keys(versionPayload).length > 0) {
          await updateVersion(loom.id, cv.id, versionPayload);
        }
      }

      onSuccess();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg overflow-y-auto max-h-[90vh]">
        <div className="flex items-start justify-between mb-5">
          <div>
            <h2 className="text-lg font-semibold">
              {loom.loom_reference_id ? "Change catalog link" : "Link to catalog"}
            </h2>
            <p className="text-sm text-muted-foreground">
              {loom.manufacturer} {loom.model_name}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors ml-4"
          >
            ✕
          </button>
        </div>

        {/* ── Step: search ── */}
        {step === "search" && (
          <div ref={searchContainerRef} className="relative">
            <label className="mb-1 block text-sm font-medium">Search loom catalog</label>
            <input
              type="search"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              value={displayQuery}
              onChange={(e) => handleInputChange(e.target.value)}
              placeholder="Schacht Baby Wolf, Louet Spring…"
              autoFocus
              autoComplete="off"
            />
            {searching && (
              <p className="mt-1 text-xs text-muted-foreground">Searching…</p>
            )}
            {showResults && results.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md max-h-60 overflow-y-auto">
                {results.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    className="w-full px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground flex flex-col"
                    onMouseDown={() => handleSelectRef(r)}
                  >
                    <span className="font-medium">
                      {r.brand} {r.model_name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {LOOM_TYPE_LABELS[categoryToLoomType(r.loom_category)]}
                      {r.shaft_count_options?.length
                        ? ` · ${r.shaft_count_options.join("/")} shafts`
                        : ""}
                      {r.origin_country ? ` · ${r.origin_country}` : ""}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {showResults &&
              results.length === 0 &&
              !searching &&
              displayQuery.length >= 2 && (
                <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover px-3 py-2 text-sm text-muted-foreground shadow-md">
                  No results found.
                </div>
              )}
            <div className="mt-4 flex justify-end">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* ── Step: configure ── */}
        {step === "configure" && selectedRef && (
          <div className="space-y-4">
            <div className="rounded-md border bg-muted/30 px-3 py-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold">
                    {selectedRef.brand} {selectedRef.model_name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {LOOM_TYPE_LABELS[newLoomType]}
                    {selectedRef.origin_country ? ` · ${selectedRef.origin_country}` : ""}
                  </p>
                </div>
                <button
                  type="button"
                  className="shrink-0 text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setSelectedRef(null);
                    setStep("search");
                  }}
                >
                  Change
                </button>
              </div>
            </div>

            {showsShafts(newLoomType) && shaftOptions.length > 0 && (
              <div>
                <label className="mb-1 block text-sm font-medium">Shafts</label>
                {shaftOptions.length > 1 ? (
                  <select
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={selectedShaftIdx}
                    onChange={(e) => setSelectedShaftIdx(Number(e.target.value))}
                  >
                    {shaftOptions.map((s, i) => (
                      <option key={s} value={i}>
                        {s}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
                    {shaftOptions[0]}
                  </p>
                )}
              </div>
            )}

            {showsTreadles(newLoomType) && derivedTreadles != null && (
              <div>
                <label className="mb-1 block text-sm font-medium">Treadles</label>
                <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
                  {derivedTreadles}
                </p>
              </div>
            )}

            {widthOptions.length > 0 && (
              <div>
                <label className="mb-1 block text-sm font-medium">Weaving width</label>
                {widthOptions.length > 1 ? (
                  <select
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                    value={selectedWidthIdx}
                    onChange={(e) => setSelectedWidthIdx(Number(e.target.value))}
                  >
                    {widthOptions.map((o, i) => (
                      <option key={o.value} value={i}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
                    {widthOptions[0].label}
                  </p>
                )}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setSelectedRef(null);
                  setStep("search");
                }}
              >
                Back
              </Button>
              <Button type="button" onClick={() => setStep("confirm")}>
                Review changes
              </Button>
            </div>
          </div>
        )}

        {/* ── Step: confirm ── */}
        {step === "confirm" && selectedRef && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Review the changes below. The loom identity and current configuration will be
              updated to match the catalog entry.
            </p>

            <div className="rounded-md border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30">
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground w-28">
                      Field
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
                      Current
                    </th>
                    <th className="px-3 py-2 text-center text-xs text-muted-foreground w-6">→</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">
                      New
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {diffRows.map((row) => (
                    <tr
                      key={row.label}
                      className={`border-b last:border-0 ${row.changed ? "" : "opacity-40"}`}
                    >
                      <td className="px-3 py-2 text-xs text-muted-foreground">{row.label}</td>
                      <td className="px-3 py-2">{row.oldVal}</td>
                      <td className="px-3 py-2 text-center text-muted-foreground">→</td>
                      <td
                        className={`px-3 py-2 ${row.changed ? "font-medium text-foreground" : ""}`}
                      >
                        {row.newVal}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!hasChanges && (
              <p className="text-sm text-muted-foreground italic">
                No fields will change — only the catalog link will be set.
              </p>
            )}

            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  setStep(
                    shaftOptions.length > 1 || widthOptions.length > 1
                      ? "configure"
                      : "search",
                  )
                }
                disabled={saving}
              >
                Back
              </Button>
              <Button type="button" onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : "Confirm & save"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
