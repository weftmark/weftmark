import { useState, useEffect, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";
import { listLoomCatalog, type LoomReferenceSummary } from "@/api/looms";

function ShaftBadge({ options }: { options: number[] | null }) {
  if (!options || options.length === 0) return <span className="text-stone-400">—</span>;
  return <span>{options.map((n) => Math.round(n)).join(" / ")}</span>;
}

function WidthBadge({ loom }: { loom: LoomReferenceSummary }) {
  const cm = loom.weaving_width_options_cm ?? [];
  const inches = loom.weaving_width_options_inches ?? [];
  if (inches.length === 0 && cm.length === 0) {
    return <span className="text-stone-400">—</span>;
  }
  const count = Math.max(inches.length, cm.length);
  const parts = Array.from({ length: count }, (_, i) => {
    const inPart = inches[i] != null ? `${Math.round(inches[i])}"` : null;
    const cmPart = cm[i] != null ? `${Math.round(cm[i])} cm` : null;
    if (inPart && cmPart) return `${inPart} (${cmPart})`;
    return inPart ?? cmPart ?? "";
  });
  return <span>{parts.join(" / ")}</span>;
}

function LoomCard({ loom }: { loom: LoomReferenceSummary }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5 space-y-3 hover:border-amber-300 transition-colors">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium text-amber-700 uppercase tracking-wide">{loom.brand}</p>
          <h3 className="font-semibold text-stone-900 leading-snug">{loom.model_name}</h3>
          {loom.model_series && (
            <p className="text-xs text-stone-500">{loom.model_series}</p>
          )}
        </div>
        <span className="shrink-0 text-xs rounded-full bg-stone-100 text-stone-600 px-2.5 py-1 font-medium">
          {t(`loomCatalogPage.loomTypes.${loom.loom_category}`, { defaultValue: loom.loom_category })}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm text-stone-700">
        {loom.shaft_count_options && loom.shaft_count_options.length > 0 && (
          <>
            <span className="text-stone-500">{t("loomCatalogPage.shafts")}</span>
            <ShaftBadge options={loom.shaft_count_options} />
          </>
        )}
        {(loom.weaving_width_options_cm?.length || loom.weaving_width_options_inches?.length) ? (
          <>
            <span className="text-stone-500">{t("loomCatalogPage.width")}</span>
            <WidthBadge loom={loom} />
          </>
        ) : null}
        {loom.shedding_mechanism && (
          <>
            <span className="text-stone-500">{t("loomCatalogPage.shedding")}</span>
            <span>{loom.shedding_mechanism.replace(/_/g, " ")}</span>
          </>
        )}
        {loom.foldable !== null && (
          <>
            <span className="text-stone-500">{t("loomCatalogPage.foldable")}</span>
            <span>{loom.foldable ? t("loomCatalogPage.yes") : t("loomCatalogPage.no")}</span>
          </>
        )}
        {loom.origin_country && (
          <>
            <span className="text-stone-500">{t("loomCatalogPage.origin")}</span>
            <span>{loom.origin_country}</span>
          </>
        )}
      </div>
    </div>
  );
}

export function LoomCatalogPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [loomType, setLoomType] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [shaftCount, setShaftCount] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [search]);

  // Load all looms; only text search is server-side. Other filters are client-side
  // so dropdown options stay stable as you filter.
  const { data: allLooms = [], isLoading } = useQuery({
    queryKey: ["loom-catalog-public", debouncedSearch],
    queryFn: () => listLoomCatalog({ q: debouncedSearch || undefined }),
  });

  // Derive dropdown options from the full server result (stable across client filters)
  const manufacturerOptions = useMemo(
    () => [...new Set(allLooms.map((l) => l.brand))].sort(),
    [allLooms],
  );

  const shaftCountOptions = useMemo(() => {
    const counts = new Set<number>();
    for (const l of allLooms) {
      for (const n of l.shaft_count_options ?? []) counts.add(Math.round(n));
    }
    return [...counts].sort((a, b) => a - b);
  }, [allLooms]);

  // Apply client-side filters
  const looms = useMemo(() => {
    return allLooms.filter((l) => {
      if (loomType && l.loom_category !== loomType) return false;
      if (manufacturer && l.brand !== manufacturer) return false;
      if (shaftCount) {
        const n = Number(shaftCount);
        if (!(l.shaft_count_options ?? []).some((s) => Math.round(s) === n)) return false;
      }
      return true;
    });
  }, [allLooms, loomType, manufacturer, shaftCount]);

  const brands = [...new Set(looms.map((l) => l.brand))].sort();
  const grouped = Object.fromEntries(
    brands.map((brand) => [brand, looms.filter((l) => l.brand === brand)]),
  );

  const hasFilters = search || loomType || manufacturer || shaftCount;

  const loomTypeKeys = [
    "floor_loom", "table_loom", "rigid_heddle", "inkle",
    "dobby_floor_loom", "tapestry_loom", "rug_loom", "frame_loom", "other",
  ];

  const selectClass =
    "rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400";

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-stone-50 px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span
              className="text-lg font-semibold tracking-tight"
              style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}
            >
              weftmark
            </span>
          </Link>
          <Link to="/login" className="text-sm text-stone-600 hover:text-stone.900 transition-colors">
            {t("loomCatalogPage.signIn")}
          </Link>
        </div>
      </header>

      <main className="flex-1 px-4 py-12">
        <div className="mx-auto max-w-5xl space-y-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">{t("loomCatalogPage.title")}</h1>
            <p className="text-stone-600">
              {t("loomCatalogPage.intro")}
              {allLooms.length > 0 && (
                <span className="ml-1 text-stone-500">
                  {t("loomCatalogPage.count", { count: allLooms.length })}
                </span>
              )}
            </p>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <input
              type="search"
              placeholder={t("loomCatalogPage.searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 w-56"
            />

            <select
              value={loomType}
              onChange={(e) => setLoomType(e.target.value)}
              className={selectClass}
            >
              <option value="">{t("loomCatalogPage.allTypes")}</option>
              {loomTypeKeys.map((key) => (
                <option key={key} value={key}>
                  {t(`loomCatalogPage.loomTypes.${key}`, { defaultValue: key })}
                </option>
              ))}
            </select>

            <select
              value={manufacturer}
              onChange={(e) => setManufacturer(e.target.value)}
              className={selectClass}
              disabled={manufacturerOptions.length === 0}
            >
              <option value="">{t("loomCatalogPage.allManufacturers")}</option>
              {manufacturerOptions.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>

            <select
              value={shaftCount}
              onChange={(e) => setShaftCount(e.target.value)}
              className={selectClass}
              disabled={shaftCountOptions.length === 0}
            >
              <option value="">{t("loomCatalogPage.anyShaftCount")}</option>
              {shaftCountOptions.map((n) => (
                <option key={n} value={n}>{t("loomCatalogPage.shaftCountOption", { count: n })}</option>
              ))}
            </select>

            {hasFilters && (
              <button
                onClick={() => {
                  setSearch("");
                  setLoomType("");
                  setManufacturer("");
                  setShaftCount("");
                }}
                className="text-sm text-stone-500 hover:text-stone-700 transition-colors"
              >
                {t("loomCatalogPage.clearFilters")}
              </button>
            )}
          </div>

          {isLoading ? (
            <div className="text-center py-16 text-stone-400">{t("loomCatalogPage.loading")}</div>
          ) : looms.length === 0 ? (
            <div className="text-center py-16 text-stone-400">
              {hasFilters ? t("loomCatalogPage.noFilters") : t("loomCatalogPage.empty")}
            </div>
          ) : (
            <div className="space-y-8">
              {Object.entries(grouped).map(([brand, entries]) => (
                <section key={brand}>
                  <h2 className="text-lg font-semibold text-stone-700 mb-3">{brand}</h2>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {entries.map((loom) => (
                      <LoomCard key={loom.id} loom={loom} />
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
