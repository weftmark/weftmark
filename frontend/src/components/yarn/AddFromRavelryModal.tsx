import { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  searchRavelryCompanies,
  searchRavelryYarns,
  getRavelryYarnDetail,
  importRavelryYarn,
  formatColorwayLabel,
  getPopularRavelryCompanies,
  getPopularRavelryYarns,
  type RavelryCompany,
  type RavelryYarnResult,
  type RavelryColorway,
} from "@/api/ravelry";
import { listYarn } from "@/api/yarn";
import { ColorPicker } from "@/components/ui/ColorPicker";
import { Button } from "@/components/ui/button";

interface Props {
  onSuccess: () => void;
  onClose: () => void;
}

type Step = "company" | "yarn" | "colorway";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function AddFromRavelryModal({ onSuccess, onClose }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>("company");

  // Company step
  const [companyQuery, setCompanyQuery] = useState("");
  const [companies, setCompanies] = useState<RavelryCompany[]>([]);
  const [companyLoading, setCompanyLoading] = useState(false);
  const [selectedCompany, setSelectedCompany] = useState<RavelryCompany | null>(null);

  // Yarn step
  const [yarnQuery, setYarnQuery] = useState("");
  const [yarns, setYarns] = useState<RavelryYarnResult[]>([]);
  const [yarnLoading, setYarnLoading] = useState(false);
  const [selectedYarn, setSelectedYarn] = useState<RavelryYarnResult | null>(null);

  // Colorway step
  const [colorways, setColorways] = useState<RavelryColorway[]>([]);
  const [colorwaysLoading, setColorwaysLoading] = useState(false);
  const [selectedColorway, setSelectedColorway] = useState<RavelryColorway | null>(null);
  const [colorwayFilter, setColorwayFilter] = useState("");
  const [colorName, setColorName] = useState("");
  const [colorHex, setColorHex] = useState("#808080");
  const [hasColor, setHasColor] = useState(false);

  // Import
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debouncedCompanyQuery = useDebounce(companyQuery, 400);
  const debouncedYarnQuery = useDebounce(yarnQuery, 400);

  const { data: inventoryYarns = [] } = useQuery({
    queryKey: ["yarn", { includeArchived: false }],
    queryFn: () => listYarn(false),
    staleTime: 60_000,
  });

  const { data: popularCompanies = [], isFetching: popularFetching } = useQuery({
    queryKey: ["ravelry-popular-companies"],
    queryFn: () => getPopularRavelryCompanies(10),
    staleTime: 5 * 60_000,
  });

  const { data: popularYarns = [], isFetching: popularYarnsFetching } = useQuery({
    queryKey: ["ravelry-popular-yarns", selectedCompany?.id],
    queryFn: () => getPopularRavelryYarns(selectedCompany!.id, selectedCompany!.name),
    enabled: step === "yarn" && !!selectedCompany,
    staleTime: 5 * 60_000,
  });

  const MAX_PRESEEDS = 8;

  const inventoryBrands = useMemo(() => {
    const seen = new Set<string>();
    const brands: string[] = [];
    for (const y of inventoryYarns) {
      if (y.brand && !seen.has(y.brand)) {
        seen.add(y.brand);
        brands.push(y.brand);
      }
    }
    return brands.slice(0, MAX_PRESEEDS);
  }, [inventoryYarns]);

  const popularFill = useMemo(() => {
    const remaining = MAX_PRESEEDS - inventoryBrands.length;
    if (remaining <= 0) return [];
    const invNamesLower = new Set(inventoryBrands.map((b) => b.toLowerCase()));
    return popularCompanies
      .filter((c) => !invNamesLower.has(c.name.toLowerCase()))
      .slice(0, remaining);
  }, [inventoryBrands, popularCompanies]);

  const inventoryYarnLines = useMemo(() => {
    if (!selectedCompany) return [];
    const companyLower = selectedCompany.name.toLowerCase();
    const seen = new Set<string>();
    const lines: string[] = [];
    for (const y of inventoryYarns) {
      if (y.brand?.toLowerCase() === companyLower && y.name && !seen.has(y.name)) {
        seen.add(y.name);
        lines.push(y.name);
      }
    }
    return lines.slice(0, MAX_PRESEEDS);
  }, [inventoryYarns, selectedCompany]);

  const popularYarnsFill = useMemo(() => {
    const remaining = MAX_PRESEEDS - inventoryYarnLines.length;
    if (remaining <= 0) return [];
    const invNamesLower = new Set(inventoryYarnLines.map((n) => n.toLowerCase()));
    return popularYarns
      .filter((y) => !invNamesLower.has(y.name.toLowerCase()))
      .slice(0, remaining);
  }, [inventoryYarnLines, popularYarns]);

  const inStashIds = useMemo(
    () => new Set(inventoryYarns.map((y) => y.ravelry_yarn_id).filter((id): id is number => id !== null)),
    [inventoryYarns],
  );

  const sortedYarns = useMemo(
    () => [...yarns].sort((a, b) => Number(inStashIds.has(b.id)) - Number(inStashIds.has(a.id))),
    [yarns, inStashIds],
  );

  const inventoryColorways = useMemo(() => {
    if (!selectedYarn) return [];
    const seen = new Set<string>();
    const names: string[] = [];
    for (const y of inventoryYarns) {
      if (y.ravelry_yarn_id === selectedYarn.id && y.color_name && !seen.has(y.color_name)) {
        seen.add(y.color_name);
        names.push(y.color_name);
      }
    }
    return names;
  }, [inventoryYarns, selectedYarn]);

  const filteredColorways = useMemo(() => {
    if (!colorwayFilter.trim()) return colorways;
    const q = colorwayFilter.toLowerCase();
    return colorways.filter((cw) => cw.name.toLowerCase().includes(q) || (cw.code ?? "").toLowerCase().includes(q));
  }, [colorways, colorwayFilter]);

  // Company search
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!debouncedCompanyQuery.trim()) { setCompanies([]); return; }
    setCompanyLoading(true);
    searchRavelryCompanies(debouncedCompanyQuery)
      .then(setCompanies)
      .catch(() => setCompanies([]))
      .finally(() => setCompanyLoading(false));
  }, [debouncedCompanyQuery]);

  // Yarn search (fires when step changes to yarn OR query changes)
  useEffect(() => {
    if (step !== "yarn") return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!debouncedYarnQuery.trim()) { setYarns([]); return; }
    setYarnLoading(true);
    searchRavelryYarns(debouncedYarnQuery, selectedCompany?.id)
      .then(setYarns)
      .catch(() => setYarns([]))
      .finally(() => setYarnLoading(false));
  }, [debouncedYarnQuery, step, selectedCompany?.id]);

  // Colorways are preloaded in pickYarn — no step-change effect needed

  async function pickInventoryBrand(brand: string) {
    setCompanyQuery(brand);
    setCompanyLoading(true);
    try {
      const results = await searchRavelryCompanies(brand);
      if (results.length === 1) {
        pickCompany(results[0]);
      } else {
        setCompanies(results);
      }
    } catch {
      setCompanies([]);
    } finally {
      setCompanyLoading(false);
    }
  }

  async function pickInventoryYarnLine(yarnName: string) {
    setYarnQuery(yarnName);
    setYarnLoading(true);
    try {
      const results = await searchRavelryYarns(yarnName, selectedCompany?.id);
      if (results.length === 1) {
        pickYarn(results[0]);
      } else {
        setYarns(results);
      }
    } catch {
      setYarns([]);
    } finally {
      setYarnLoading(false);
    }
  }

  function pickCompany(company: RavelryCompany) {
    setSelectedCompany(company);
    setYarnQuery("");
    setYarns([]);
    setStep("yarn");
  }

  async function pickYarn(yarn: RavelryYarnResult) {
    setSelectedYarn(yarn);
    setColorName("");
    setColorHex("#808080");
    setHasColor(false);
    setSelectedColorway(null);
    setColorways([]);
    setColorwayFilter("");
    setColorwaysLoading(true);
    setStep("colorway");
    try {
      const resp = await getRavelryYarnDetail(yarn.id);
      const cws: RavelryColorway[] = resp.colorways ?? [];
      const active = cws.filter((c) => c.current_status !== "discontinued").slice(0, 60);
      setColorways(active);
      if (active.length === 1) {
        setSelectedColorway(active[0]);
        setColorName(formatColorwayLabel(active[0]));
      }
    } catch {
      setColorways([]);
    } finally {
      setColorwaysLoading(false);
    }
  }

  function pickColorway(cw: RavelryColorway) {
    setSelectedColorway(cw);
    setColorName(formatColorwayLabel(cw));
  }

  async function handleImport() {
    if (!selectedYarn) return;
    setImporting(true);
    setError(null);
    try {
      const result = await importRavelryYarn({
        ravelry_yarn_id: selectedYarn.id,
        color_name: colorName.trim() || undefined,
        color_hex: hasColor ? colorHex : undefined,
      });
      onSuccess();
      navigate(`/yarn/${result.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("addFromRavelryModal.importError"));
      setImporting(false);
    }
  }

  const inputCls = "w-full rounded-md border border-input bg-background px-3 py-2 pr-8 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring";
  const clearBtnCls = "absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground leading-none p-0.5";

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-16 px-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-card-foreground">{t("addFromRavelryModal.title")}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {step === "company" && t("addFromRavelryModal.stepCompany")}
              {step === "yarn" && t("addFromRavelryModal.stepYarn", { company: selectedCompany?.name })}
              {step === "colorway" && t("addFromRavelryModal.stepColorway", { yarn: selectedYarn?.name })}
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">✕</button>
        </div>

        <div className={`px-5 py-4 space-y-3 ${step !== "colorway" ? "max-h-[60vh] overflow-y-auto" : ""}`}>

          {/* ── Step 1: Company ── */}
          {step === "company" && (
            <>
              <div className="relative">
                <input
                  autoFocus
                  className={inputCls}
                  placeholder={t("addFromRavelryModal.searchCompanyPlaceholder")}
                  value={companyQuery}
                  onChange={(e) => setCompanyQuery(e.target.value)}
                />
                {companyQuery && (
                  <button type="button" className={clearBtnCls} aria-label={t("common.clear")} onClick={() => setCompanyQuery("")}>✕</button>
                )}
              </div>
              {!companyQuery.trim() ? (
                inventoryBrands.length > 0 || popularFill.length > 0 ? (
                  <>
                    {inventoryBrands.length > 0 && (
                      <p className="text-xs text-muted-foreground">{t("addFromRavelryModal.fromInventoryLabel")}</p>
                    )}
                    <ul className="space-y-1">
                      {inventoryBrands.map((brand) => (
                        <li key={`inv-${brand}`}>
                          <button
                            className="w-full text-left rounded-md px-3 py-2 text-sm hover:bg-accent/10 transition-colors text-card-foreground"
                            onClick={() => pickInventoryBrand(brand)}
                          >
                            {brand}
                          </button>
                        </li>
                      ))}
                      {popularFill.map((c) => (
                        <li key={`pop-${c.id}`}>
                          <button
                            className="w-full text-left rounded-md px-3 py-2 text-sm hover:bg-accent/10 transition-colors text-muted-foreground"
                            onClick={() => pickCompany(c)}
                          >
                            {c.name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : popularFetching ? (
                  <p className="text-xs text-muted-foreground">{t("common.loading")}</p>
                ) : null
              ) : (
                <>
                  {companyLoading && <p className="text-xs text-muted-foreground">{t("common.loading")}</p>}
                  {!companyLoading && companies.length === 0 && (
                    <p className="text-xs text-muted-foreground">{t("addFromRavelryModal.noResults")}</p>
                  )}
                  <ul className="space-y-1">
                    {companies.map((c) => (
                      <li key={c.id}>
                        <button
                          className="w-full text-left rounded-md px-3 py-2 text-sm hover:bg-accent/10 transition-colors text-card-foreground"
                          onClick={() => pickCompany(c)}
                        >
                          {c.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}

          {/* ── Step 2: Yarn ── */}
          {step === "yarn" && (
            <>
              <div className="relative">
                <input
                  autoFocus
                  className={inputCls}
                  placeholder={t("addFromRavelryModal.searchYarnPlaceholder")}
                  value={yarnQuery}
                  onChange={(e) => setYarnQuery(e.target.value)}
                />
                {yarnQuery && (
                  <button type="button" className={clearBtnCls} aria-label={t("common.clear")} onClick={() => setYarnQuery("")}>✕</button>
                )}
              </div>
              {!yarnQuery.trim() ? (
                inventoryYarnLines.length > 0 || popularYarnsFill.length > 0 ? (
                  <>
                    {inventoryYarnLines.length > 0 && (
                      <p className="text-xs text-muted-foreground">{t("addFromRavelryModal.fromInventoryLabel")}</p>
                    )}
                    <ul className="space-y-1">
                      {inventoryYarnLines.map((name) => (
                        <li key={`inv-${name}`}>
                          <button
                            className="w-full text-left rounded-md px-3 py-2 text-sm hover:bg-accent/10 transition-colors text-card-foreground"
                            onClick={() => pickInventoryYarnLine(name)}
                          >
                            {name}
                          </button>
                        </li>
                      ))}
                      {popularYarnsFill.map((y) => (
                        <li key={`pop-${y.id}`}>
                          <button
                            className="w-full text-left flex items-center gap-3 rounded-md px-3 py-2 hover:bg-accent/10 transition-colors"
                            onClick={() => pickYarn(y)}
                          >
                            {y.photo_url && (
                              <img src={y.photo_url} alt={y.name} className="h-10 w-10 rounded object-cover shrink-0" />
                            )}
                            <div className="min-w-0">
                              <p className="text-sm text-muted-foreground truncate">{y.name}</p>
                              <p className="text-xs text-muted-foreground">{y.weight_name ?? ""}</p>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </>
                ) : popularYarnsFetching ? (
                  <p className="text-xs text-muted-foreground">{t("common.loading")}</p>
                ) : null
              ) : (
                <>
                  {yarnLoading && <p className="text-xs text-muted-foreground">{t("common.loading")}</p>}
                  {!yarnLoading && yarns.length === 0 && (
                    <p className="text-xs text-muted-foreground">{t("addFromRavelryModal.noResults")}</p>
                  )}
                  <ul className="space-y-1">
                    {sortedYarns.map((y) => (
                      <li key={y.id}>
                        <button
                          className="w-full text-left flex items-center gap-3 rounded-md px-3 py-2 hover:bg-accent/10 transition-colors"
                          onClick={() => pickYarn(y)}
                        >
                          {y.photo_url && (
                            <img src={y.photo_url} alt={y.name} className="h-10 w-10 rounded object-cover shrink-0" />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <p className="text-sm text-card-foreground truncate">{y.name}</p>
                              {inStashIds.has(y.id) && (
                                <span className="shrink-0 rounded px-1.5 py-0.5 text-[10px] bg-accent/10 text-accent">
                                  {t("addFromRavelryModal.inStash")}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground">{y.weight_name ?? ""}</p>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}

          {/* ── Step 3: Colorway ── */}
          {step === "colorway" && (
            <>
              {/* Yarn summary */}
              <div className="flex items-center gap-3 rounded-md bg-muted px-3 py-2">
                {selectedYarn?.photo_url && (
                  <img src={selectedYarn.photo_url} alt={selectedYarn.name} className="h-10 w-10 rounded object-cover shrink-0" />
                )}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-card-foreground truncate">{selectedYarn?.name}</p>
                  <p className="text-xs text-muted-foreground">{selectedCompany?.name}</p>
                </div>
              </div>

              {/* Inventory colorway pre-seeds */}
              {inventoryColorways.length > 0 && (
                <div>
                  <p className="mb-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">{t("addFromRavelryModal.fromInventoryLabel")}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {inventoryColorways.map((name) => (
                      <button
                        key={name}
                        className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                          colorName === name
                            ? "border-ring bg-accent/10 text-accent"
                            : "border-border hover:border-ring text-card-foreground"
                        }`}
                        onClick={() => { setColorName(name); setSelectedColorway(null); }}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Ravelry colorway picker */}
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{t("addFromRavelryModal.colorwayLabel")}</p>
              {colorwaysLoading && <p className="text-xs text-muted-foreground">{t("common.loading")}</p>}
              {!colorwaysLoading && colorways.length === 0 && (
                <p className="text-xs text-muted-foreground">{t("addFromRavelryModal.colorwayCustomHint")}</p>
              )}
              {!colorwaysLoading && colorways.length > 6 && (
                <div className="relative">
                  <input
                    className={inputCls}
                    placeholder={t("addFromRavelryModal.colorwayFilterPlaceholder")}
                    value={colorwayFilter}
                    onChange={(e) => setColorwayFilter(e.target.value)}
                  />
                  {colorwayFilter && (
                    <button className={clearBtnCls} onClick={() => setColorwayFilter("")}>✕</button>
                  )}
                </div>
              )}
              {!colorwaysLoading && filteredColorways.length > 0 && (
                <div className="grid grid-cols-3 gap-1.5 max-h-44 overflow-y-auto">
                  {filteredColorways.map((cw) => (
                    <button
                      key={cw.id}
                      className={`text-left rounded-md border p-1.5 text-xs transition-colors ${
                        selectedColorway?.id === cw.id
                          ? "border-ring bg-accent/10 text-accent"
                          : "border-border hover:border-ring text-card-foreground"
                      }`}
                      onClick={() => pickColorway(cw)}
                    >
                      {cw.photos?.[0]?.square_url && (
                        <img src={cw.photos[0].square_url} alt={cw.name} className="h-10 w-full rounded object-cover mb-1" />
                      )}
                      <span className="truncate block leading-tight">{formatColorwayLabel(cw)}</span>
                    </button>
                  ))}
                </div>
              )}

              {/* Color hex */}
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="ravelry-has-color"
                  checked={hasColor}
                  onChange={(e) => setHasColor(e.target.checked)}
                  className="shrink-0"
                />
                <label htmlFor="ravelry-has-color" className="text-sm text-card-foreground">{t("addFromRavelryModal.setColorLabel")}</label>
                {hasColor && <ColorPicker value={colorHex} onChange={setColorHex} />}
              </div>

              {/* Color name input */}
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">{t("addFromRavelryModal.colorNameLabel")}</label>
                <input
                  className={inputCls}
                  placeholder={t("addFromRavelryModal.colorNamePlaceholder")}
                  value={colorName}
                  onChange={(e) => setColorName(e.target.value)}
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <div className="flex gap-2">
            {step !== "company" && (
              <Button variant="ghost" size="sm" onClick={() => setStep(step === "colorway" ? "yarn" : "company")}>
                {t("common.back")}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}>{t("common.cancel")}</Button>
          </div>
          {step === "colorway" && (
            <Button size="sm" disabled={importing} onClick={handleImport}>
              {importing ? t("common.loading") : t("addFromRavelryModal.importButton")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
