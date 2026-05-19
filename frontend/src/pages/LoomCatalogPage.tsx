import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";
import { listLoomCatalog, type LoomReferenceSummary } from "@/api/looms";

const CATEGORY_LABELS: Record<string, string> = {
  floor_loom: "Floor Loom",
  table_loom: "Table Loom",
  rigid_heddle: "Rigid Heddle",
  inkle: "Inkle",
  dobby_floor_loom: "Dobby Floor Loom",
  tapestry_loom: "Tapestry Loom",
  rug_loom: "Rug Loom",
  frame_loom: "Frame Loom",
  other: "Other",
};

const ALL_CATEGORIES = Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }));

function ShaftBadge({ options }: { options: number[] | null }) {
  if (!options || options.length === 0) return <span className="text-stone-400">—</span>;
  return <span>{options.map((n) => `${n}`).join(" / ")}</span>;
}

function WidthBadge({ options }: { options: number[] | null }) {
  if (!options || options.length === 0) return <span className="text-stone-400">—</span>;
  return <span>{options.map((n) => `${n}"`).join(" / ")}</span>;
}

function LoomCard({ loom }: { loom: LoomReferenceSummary }) {
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
          {CATEGORY_LABELS[loom.loom_category] ?? loom.loom_category}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm text-stone-700">
        {loom.shaft_count_options && loom.shaft_count_options.length > 0 && (
          <>
            <span className="text-stone-500">Shafts</span>
            <ShaftBadge options={loom.shaft_count_options} />
          </>
        )}
        {loom.weaving_width_options_inches && loom.weaving_width_options_inches.length > 0 && (
          <>
            <span className="text-stone-500">Width</span>
            <WidthBadge options={loom.weaving_width_options_inches} />
          </>
        )}
        {loom.shedding_mechanism && (
          <>
            <span className="text-stone-500">Shedding</span>
            <span>{loom.shedding_mechanism.replace(/_/g, " ")}</span>
          </>
        )}
        {loom.foldable !== null && (
          <>
            <span className="text-stone-500">Foldable</span>
            <span>{loom.foldable ? "Yes" : "No"}</span>
          </>
        )}
        {loom.origin_country && (
          <>
            <span className="text-stone-500">Origin</span>
            <span>{loom.origin_country}</span>
          </>
        )}
      </div>
    </div>
  );
}

export function LoomCatalogPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [category, setCategory] = useState("");
  const [foldable, setFoldable] = useState<"" | "true" | "false">("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [search]);

  const { data: looms = [], isLoading } = useQuery({
    queryKey: ["loom-catalog-public", debouncedSearch, category, foldable],
    queryFn: () =>
      listLoomCatalog({
        q: debouncedSearch || undefined,
        category: category || undefined,
        foldable: foldable === "" ? undefined : foldable === "true",
      }),
  });

  const brands = [...new Set(looms.map((l) => l.brand))].sort();

  const grouped = brands.reduce<Record<string, LoomReferenceSummary[]>>((acc, brand) => {
    acc[brand] = looms.filter((l) => l.brand === brand);
    return acc;
  }, {});

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-stone-50 px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span className="text-lg font-semibold tracking-tight" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>weftmark</span>
          </Link>
          <Link to="/login" className="text-sm text-stone-600 hover:text-stone-900 transition-colors">
            Sign in
          </Link>
        </div>
      </header>

      <main className="flex-1 px-4 py-12">
        <div className="mx-auto max-w-5xl space-y-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">Supported looms</h1>
            <p className="text-stone-600">
              Looms in our catalog can be selected during loom setup for automatic spec pre-fill.
              {looms.length > 0 && (
                <span className="ml-1 text-stone-500">{looms.length} {looms.length === 1 ? "loom" : "looms"} in the catalog.</span>
              )}
            </p>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-3">
            <input
              type="search"
              placeholder="Search brand or model…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 w-64"
            />
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            >
              <option value="">All categories</option>
              {ALL_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <select
              value={foldable}
              onChange={(e) => setFoldable(e.target.value as "" | "true" | "false")}
              className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            >
              <option value="">Foldable: any</option>
              <option value="true">Foldable only</option>
              <option value="false">Non-foldable only</option>
            </select>
            {(search || category || foldable) && (
              <button
                onClick={() => { setSearch(""); setCategory(""); setFoldable(""); }}
                className="text-sm text-stone-500 hover:text-stone-700 transition-colors"
              >
                Clear filters
              </button>
            )}
          </div>

          {isLoading ? (
            <div className="text-center py-16 text-stone-400">Loading catalog…</div>
          ) : looms.length === 0 ? (
            <div className="text-center py-16 text-stone-400">
              {debouncedSearch || category || foldable
                ? "No looms match these filters."
                : "The catalog is empty."}
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
