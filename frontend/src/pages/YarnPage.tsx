import { useState, useEffect, useRef, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  LayoutList,
  LayoutGrid,
  Table2,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  ArrowUpDown,
} from "lucide-react";
import { listYarn, yarnPhotoUrl, type YarnSummary } from "@/api/yarn";
import { getRavelryStatus, syncRavelryStash, pushBulkToStash } from "@/api/ravelry";
import { AddYarnModal } from "@/components/yarn/AddYarnModal";
import { AddFromRavelryModal } from "@/components/yarn/AddFromRavelryModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { SkeletonCardGrid } from "@/components/ui/skeleton";

// ─── constants ────────────────────────────────────────────────────────────────

const BANNER_KEY = "ravelry_stash_banner_dismissed";
const PREFS_KEY = "yarn_list_prefs";

const WEIGHT_ORDER = [
  "thread", "lace", "fingering", "sport", "dk",
  "worsted", "aran", "bulky", "super_bulky",
];

// ─── types ────────────────────────────────────────────────────────────────────

type ViewMode = "card" | "grid" | "table";
type SortKey =
  | "created_at_desc"
  | "created_at_asc"
  | "brand_asc"
  | "brand_desc"
  | "name_asc"
  | "weight_asc";

interface YarnFilters {
  brands: string[];
  weights: string[];
  missingColor: boolean;
  inRavelryStash: boolean;
  machineWashable: boolean;
}

const DEFAULT_FILTERS: YarnFilters = { brands: [], weights: [], missingColor: false, inRavelryStash: false, machineWashable: false };

interface YarnPrefs {
  view: ViewMode;
  sort: SortKey;
  filters: YarnFilters;
}

// ─── localStorage helpers ─────────────────────────────────────────────────────

function loadPrefs(): YarnPrefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) return { view: "card", sort: "created_at_desc", filters: DEFAULT_FILTERS, ...JSON.parse(raw) };
  } catch { /* ignore */ }
  return { view: "card", sort: "created_at_desc", filters: DEFAULT_FILTERS };
}

function savePrefs(prefs: YarnPrefs) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

// ─── filter + sort logic ──────────────────────────────────────────────────────

function countActiveFilters(f: YarnFilters): number {
  return (f.brands.length > 0 ? 1 : 0) + (f.weights.length > 0 ? 1 : 0) + (f.missingColor ? 1 : 0) + (f.inRavelryStash ? 1 : 0) + (f.machineWashable ? 1 : 0);
}

function applySort(yarns: YarnSummary[], sort: SortKey): YarnSummary[] {
  return [...yarns].sort((a, b) => {
    switch (sort) {
      case "created_at_desc":
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      case "created_at_asc":
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      case "brand_asc":  return a.brand.localeCompare(b.brand);
      case "brand_desc": return b.brand.localeCompare(a.brand);
      case "name_asc":   return a.name.localeCompare(b.name);
      case "weight_asc": {
        const ai = a.weight_category ? WEIGHT_ORDER.indexOf(a.weight_category) : -1;
        const bi = b.weight_category ? WEIGHT_ORDER.indexOf(b.weight_category) : -1;
        if (ai === -1 && bi === -1) return 0;
        if (ai === -1) return 1;
        if (bi === -1) return -1;
        return ai - bi;
      }
      default: return 0;
    }
  });
}

function applyFilters(yarns: YarnSummary[], f: YarnFilters): YarnSummary[] {
  return yarns.filter((y) => {
    if (f.brands.length > 0 && !f.brands.includes(y.brand)) return false;
    if (f.weights.length > 0 && (!y.weight_category || !f.weights.includes(y.weight_category))) return false;
    if (f.missingColor && y.color_hex) return false;
    if (f.inRavelryStash && !(y.ravelry_stash_id !== null && !y.out_of_stash)) return false;
    if (f.machineWashable && !y.machine_washable) return false;
    return true;
  });
}

// ─── shared photo cell ────────────────────────────────────────────────────────

function YarnPhoto({ yarn, className }: { yarn: YarnSummary; className: string }) {
  const ravelryUrl =
    yarn.ravelry_colorway_thumbnail_url ??
    yarn.ravelry_colorway_photo_url ??
    yarn.ravelry_thumbnail_url ??
    yarn.ravelry_photo_url;
  if (ravelryUrl) {
    return <img src={ravelryUrl} alt="" className={className} />;
  }
  if (yarn.has_photo) {
    return <AuthedImage src={yarnPhotoUrl(yarn.id)} alt="" className={className} />;
  }
  if (yarn.color_hex) {
    return <div className={className} style={{ backgroundColor: yarn.color_hex }} />;
  }
  return (
    <div className={`${className} flex items-center justify-center bg-muted`}>
      <span className="text-xs text-muted-foreground">?</span>
    </div>
  );
}

// ─── card view ────────────────────────────────────────────────────────────────

function isStashPushEligible(yarn: YarnSummary) {
  return yarn.ravelry_yarn_id !== null && yarn.ravelry_stash_id === null && !yarn.out_of_stash && !yarn.archived;
}

function YarnCard({ yarn, connected }: { yarn: YarnSummary; connected: boolean }) {
  const { t } = useTranslation();
  const skeinLabel =
    yarn.skein_count === 0
      ? t("yarnPage.noSkeins")
      : yarn.available_count === yarn.skein_count
        ? t("yarnPage.allAvailable", { count: yarn.skein_count })
        : t("yarnPage.someAvailable", { available: yarn.available_count, total: yarn.skein_count });

  return (
    <Link
      to={`/yarn/${yarn.id}`}
      className="relative flex items-start gap-3 rounded-lg border p-4 hover:border-ring transition-colors"
    >
      <div className="shrink-0 flex rounded-md overflow-hidden border border-border h-14">
        <YarnPhoto yarn={yarn} className="h-14 w-14 object-cover" />
        {yarn.color_hex ? (
          <div className="h-14 w-7 shrink-0 border-l border-border" style={{ backgroundColor: yarn.color_hex }} />
        ) : (
          <div className="h-14 w-7 shrink-0 flex items-center justify-center bg-muted border-l border-border">
            <span className="text-[9px] text-muted-foreground text-center leading-tight px-0.5">{t("yarnPage.colorNotSet")}</span>
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <p className="text-sm font-medium truncate">{yarn.brand}</p>
          {yarn.ravelry_discontinued && (
            <span className="shrink-0 rounded px-1.5 py-0.5 text-xs bg-destructive/10 text-destructive">
              {t("yarnPage.discontinued")}
            </span>
          )}
          {yarn.out_of_stash && (
            <span className="shrink-0 rounded px-1.5 py-0.5 text-xs bg-muted text-muted-foreground">
              {t("yarnPage.outOfStash")}
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground truncate">{yarn.name}</p>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          {yarn.weight_notation && <span>{yarn.weight_notation}</span>}
          {yarn.fiber_content && <span>{yarn.fiber_content}</span>}
          {yarn.color_name && <span>{yarn.color_name}</span>}
        </div>
      </div>

      <div className="text-right shrink-0">
        <p className="text-xs text-muted-foreground">{skeinLabel}</p>
        {yarn.unit_yardage && (
          <p className="text-xs text-muted-foreground">{yarn.unit_yardage} {t("yarnPage.yardsPerUnit")}</p>
        )}
      </div>
      <div className="absolute bottom-2 right-2 flex gap-1">
        {yarn.ravelry_stash_id !== null && !yarn.out_of_stash && (
          <span className="rounded px-1.5 py-0.5 text-[10px] bg-accent/10 text-accent">
            {t("yarnPage.inStash")}
          </span>
        )}
        {connected && isStashPushEligible(yarn) && (
          <span className="rounded px-1.5 py-0.5 text-[10px] bg-muted/60 text-muted-foreground" title={t("yarnPage.notInRavelryStash")}>
            r↗
          </span>
        )}
        <span className="rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground">
          {yarn.ravelry_yarn_id ? t("yarnPage.sourceRavelry") : t("yarnPage.sourceWeftmark")}
        </span>
      </div>
    </Link>
  );
}

// ─── grid view ────────────────────────────────────────────────────────────────

function YarnGridTile({ yarn, connected }: { yarn: YarnSummary; connected: boolean }) {
  const { t } = useTranslation();
  const skeinLabel =
    yarn.skein_count === 0
      ? t("yarnPage.noSkeins")
      : String(yarn.skein_count);

  return (
    <Link
      to={`/yarn/${yarn.id}`}
      className="group relative flex flex-col rounded-lg border overflow-hidden hover:border-ring transition-colors"
    >
      <div className="relative aspect-square bg-muted overflow-hidden">
        <YarnPhoto yarn={yarn} className="w-full h-full object-cover" />
        <span className="absolute top-1.5 right-1.5 rounded-full bg-background/80 px-1.5 py-0.5 text-[10px] font-medium text-foreground leading-none">
          {skeinLabel}
        </span>
      </div>
      <div className="p-2 space-y-1">
        <p className="text-xs font-medium truncate">{yarn.brand}</p>
        <p className="text-xs text-muted-foreground truncate">{yarn.name}</p>
        <div className="flex flex-wrap gap-1">
          {yarn.ravelry_stash_id !== null && !yarn.out_of_stash && (
            <span className="rounded px-1 py-0.5 text-[9px] bg-accent/10 text-accent leading-none">
              {t("yarnPage.inStash")}
            </span>
          )}
          {connected && isStashPushEligible(yarn) && (
            <span className="rounded px-1 py-0.5 text-[9px] bg-muted/60 text-muted-foreground leading-none" title={t("yarnPage.notInRavelryStash")}>
              r↗
            </span>
          )}
          <span className="rounded px-1 py-0.5 text-[9px] bg-muted text-muted-foreground leading-none">
            {yarn.ravelry_yarn_id ? t("yarnPage.sourceRavelry") : t("yarnPage.sourceWeftmark")}
          </span>
        </div>
      </div>
    </Link>
  );
}

// ─── table view ───────────────────────────────────────────────────────────────

function SortHeader({
  label, currentSort, ascKey, descKey, onSort,
}: {
  label: string;
  currentSort: SortKey;
  ascKey: SortKey;
  descKey?: SortKey;
  onSort: (key: SortKey) => void;
}) {
  const isActive = currentSort === ascKey || currentSort === descKey;
  const isAsc = currentSort === ascKey;
  return (
    <button
      onClick={() => onSort(isActive && descKey && isAsc ? descKey : ascKey)}
      className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
    >
      {label}
      {isActive
        ? (isAsc ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)
        : <ArrowUpDown className="h-3 w-3 opacity-40" />}
    </button>
  );
}

function YarnTable({
  yarns, sort, onSort,
}: {
  yarns: YarnSummary[];
  sort: SortKey;
  onSort: (key: SortKey) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="rounded-lg border overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/40">
            <th className="px-3 py-2 w-10" />
            <th className="px-3 py-2 text-left">
              <SortHeader label={t("yarnPage.colBrand")} currentSort={sort} ascKey="brand_asc" descKey="brand_desc" onSort={onSort} />
            </th>
            <th className="px-3 py-2 text-left">
              <SortHeader label={t("yarnPage.colName")} currentSort={sort} ascKey="name_asc" onSort={onSort} />
            </th>
            <th className="px-3 py-2 text-left hidden sm:table-cell text-xs font-medium text-muted-foreground">
              {t("yarnPage.colColorway")}
            </th>
            <th className="px-3 py-2 text-left hidden md:table-cell">
              <SortHeader label={t("yarnPage.colWeight")} currentSort={sort} ascKey="weight_asc" onSort={onSort} />
            </th>
            <th className="px-3 py-2 text-left hidden lg:table-cell text-xs font-medium text-muted-foreground">
              {t("yarnPage.colFiber")}
            </th>
            <th className="px-3 py-2 text-left hidden sm:table-cell text-xs font-medium text-muted-foreground">
              {t("yarnPage.colSource")}
            </th>
            <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">
              {t("yarnPage.colSkeins")}
            </th>
            <th className="px-3 py-2 text-left hidden md:table-cell">
              <SortHeader label={t("yarnPage.colAdded")} currentSort={sort} ascKey="created_at_asc" descKey="created_at_desc" onSort={onSort} />
            </th>
          </tr>
        </thead>
        <tbody>
          {yarns.map((yarn, i) => (
            <tr
              key={yarn.id}
              onClick={() => navigate(`/yarn/${yarn.id}`)}
              className={`cursor-pointer hover:bg-muted/30 transition-colors ${i % 2 !== 0 ? "bg-muted/10" : ""}`}
            >
              <td className="px-3 py-2">
                <div className="h-8 w-8 rounded overflow-hidden border border-border shrink-0">
                  <YarnPhoto yarn={yarn} className="h-8 w-8 object-cover" />
                </div>
              </td>
              <td className="px-3 py-2 font-medium max-w-[140px]">
                <span className="truncate block">{yarn.brand}</span>
              </td>
              <td className="px-3 py-2 text-muted-foreground max-w-[160px]">
                <span className="truncate block">{yarn.name}</span>
              </td>
              <td className="px-3 py-2 text-muted-foreground hidden sm:table-cell">
                <div className="flex items-center gap-1.5">
                  {yarn.color_hex && (
                    <div className="h-3 w-3 rounded-sm border border-border/50 shrink-0" style={{ backgroundColor: yarn.color_hex }} />
                  )}
                  <span className="truncate max-w-[100px] text-xs">{yarn.color_name ?? "—"}</span>
                </div>
              </td>
              <td className="px-3 py-2 text-muted-foreground text-xs hidden md:table-cell">
                {yarn.weight_notation ?? yarn.weight_category ?? "—"}
              </td>
              <td className="px-3 py-2 text-muted-foreground text-xs hidden lg:table-cell max-w-[120px]">
                <span className="truncate block">{yarn.fiber_content ?? "—"}</span>
              </td>
              <td className="px-3 py-2 hidden sm:table-cell">
                <div className="flex flex-wrap gap-1">
                  {yarn.ravelry_stash_id !== null && !yarn.out_of_stash && (
                    <span className="rounded px-1.5 py-0.5 text-[10px] bg-accent/10 text-accent leading-none whitespace-nowrap">
                      {t("yarnPage.inStash")}
                    </span>
                  )}
                  <span className="rounded px-1.5 py-0.5 text-[10px] bg-muted text-muted-foreground leading-none whitespace-nowrap">
                    {yarn.ravelry_yarn_id ? t("yarnPage.sourceRavelry") : t("yarnPage.sourceWeftmark")}
                  </span>
                </div>
              </td>
              <td className="px-3 py-2 text-right text-xs">{yarn.skein_count}</td>
              <td className="px-3 py-2 text-muted-foreground text-xs hidden md:table-cell whitespace-nowrap">
                {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(yarn.created_at))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── filter popover ───────────────────────────────────────────────────────────

function FilterPopover({
  allYarns, filters, onChange,
}: {
  allYarns: YarnSummary[];
  filters: YarnFilters;
  onChange: (f: YarnFilters) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  const availableBrands = useMemo(
    () => [...new Set(allYarns.map((y) => y.brand))].sort(),
    [allYarns],
  );
  const availableWeights = useMemo(() => {
    const ws = [...new Set(allYarns.map((y) => y.weight_category).filter(Boolean))] as string[];
    return ws.sort((a, b) => WEIGHT_ORDER.indexOf(a) - WEIGHT_ORDER.indexOf(b));
  }, [allYarns]);

  const activeCount = countActiveFilters(filters);

  function toggleBrand(brand: string) {
    const brands = filters.brands.includes(brand)
      ? filters.brands.filter((b) => b !== brand)
      : [...filters.brands, brand];
    onChange({ ...filters, brands });
  }

  function toggleWeight(weight: string) {
    const weights = filters.weights.includes(weight)
      ? filters.weights.filter((w) => w !== weight)
      : [...filters.weights, weight];
    onChange({ ...filters, weights });
  }

  return (
    <div className="relative" ref={ref}>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5"
      >
        <SlidersHorizontal className="h-3.5 w-3.5" />
        {t("yarnPage.filterLabel")}
        {activeCount > 0 && (
          <span className="rounded-full bg-accent text-accent-foreground text-[10px] px-1.5 leading-5 font-medium">
            {activeCount}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute left-0 top-full mt-1 z-50 w-60 rounded-lg border bg-popover shadow-lg p-3 text-popover-foreground">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold">{t("yarnPage.filterLabel")}</span>
            {activeCount > 0 && (
              <button
                className="text-xs text-muted-foreground hover:text-foreground"
                onClick={() => onChange(DEFAULT_FILTERS)}
              >
                {t("yarnPage.filterClearAll")}
              </button>
            )}
          </div>

          <div className="mb-3 space-y-1.5">
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={filters.missingColor}
                onChange={(e) => onChange({ ...filters, missingColor: e.target.checked })}
                className="rounded accent-accent"
              />
              {t("yarnPage.filterMissingColor")}
            </label>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={filters.inRavelryStash}
                onChange={(e) => onChange({ ...filters, inRavelryStash: e.target.checked })}
                className="rounded accent-accent"
              />
              {t("yarnPage.filterInStash")}
            </label>
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={filters.machineWashable}
                onChange={(e) => onChange({ ...filters, machineWashable: e.target.checked })}
                className="rounded accent-accent"
              />
              {t("yarnPage.filterMachineWashable")}
            </label>
          </div>

          {availableWeights.length > 0 && (
            <div className="mb-3">
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                {t("yarnPage.filterWeight")}
              </p>
              <div className="space-y-1.5">
                {availableWeights.map((w) => (
                  <label key={w} className="flex items-center gap-2 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.weights.includes(w)}
                      onChange={() => toggleWeight(w)}
                      className="rounded accent-accent"
                    />
                    {w}
                  </label>
                ))}
              </div>
            </div>
          )}

          {availableBrands.length > 1 && (
            <div>
              <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                {t("yarnPage.filterBrand")}
              </p>
              <div className="space-y-1.5 max-h-36 overflow-y-auto">
                {availableBrands.map((b) => (
                  <label key={b} className="flex items-center gap-2 text-xs cursor-pointer">
                    <input
                      type="checkbox"
                      checked={filters.brands.includes(b)}
                      onChange={() => toggleBrand(b)}
                      className="rounded accent-accent"
                    />
                    <span className="truncate">{b}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── main page ────────────────────────────────────────────────────────────────

export function YarnPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [showAddFromRavelry, setShowAddFromRavelry] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<{ synced: number; unchanged: boolean } | null>(null);
  const [showBulkPushModal, setShowBulkPushModal] = useState(false);
  const [bulkPushResult, setBulkPushResult] = useState<{ pushed: number } | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(
    () => localStorage.getItem(BANNER_KEY) === "1"
  );
  const [prefs, setPrefsState] = useState<YarnPrefs>(loadPrefs);
  const { view, sort, filters } = prefs;

  function setPrefs(update: Partial<YarnPrefs>) {
    setPrefsState((prev) => {
      const next = { ...prev, ...update };
      savePrefs(next);
      return next;
    });
  }

  const { data: ravelryStatus, isLoading: statusLoading } = useQuery({
    queryKey: ["ravelry-status"],
    queryFn: getRavelryStatus,
  });

  const connected = ravelryStatus?.connected ?? false;
  const showBanner = !statusLoading && !connected && !bannerDismissed;

  function dismissBanner() {
    localStorage.setItem(BANNER_KEY, "1");
    setBannerDismissed(true);
  }

  const syncMutation = useMutation({
    mutationFn: syncRavelryStash,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["yarn"] });
      queryClient.invalidateQueries({ queryKey: ["ravelry-status"] });
      setSyncError(null);
      setSyncResult({ synced: result.synced, unchanged: result.unchanged });
      setTimeout(() => setSyncResult(null), 5000);
    },
    onError: () => {
      setSyncError(t("yarnPage.syncError"));
      setSyncResult(null);
    },
  });

  const pushBulkMutation = useMutation({
    mutationFn: pushBulkToStash,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["yarn"] });
      setShowBulkPushModal(false);
      setBulkPushResult({ pushed: result.pushed });
      setTimeout(() => setBulkPushResult(null), 5000);
    },
  });

  const { data: rawYarns = [], isLoading, error } = useQuery({
    queryKey: ["yarn", { includeArchived: showArchived }],
    queryFn: () => listYarn(showArchived),
    staleTime: 0,
  });

  const hasAutoSynced = useRef(false);

  useEffect(() => {
    if (connected && !hasAutoSynced.current && !syncMutation.isPending) {
      hasAutoSynced.current = true;
      syncMutation.mutate();
    }
  }, [connected]); // eslint-disable-line react-hooks/exhaustive-deps

  const displayYarns = useMemo(
    () => applySort(applyFilters(rawYarns, filters), sort),
    [rawYarns, filters, sort],
  );

  const eligibleForPush = useMemo(
    () => rawYarns.filter((y) => connected && isStashPushEligible(y)),
    [rawYarns, connected],
  );

  const handleAdded = () => {
    setShowAdd(false);
    queryClient.invalidateQueries({ queryKey: ["yarn"] });
  };

  return (
    <div className="p-6 max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="mb-4">
        <h1 className="text-xl font-semibold">{t("yarnPage.title")}</h1>
        {connected && ravelryStatus?.ravelry_username && (
          <p className="text-xs text-muted-foreground mt-0.5">
            {t("yarnPage.ravelrySyncedAs", { username: ravelryStatus.ravelry_username })}
          </p>
        )}
        {connected && ravelryStatus?.last_synced_at && (
          <p className="text-xs text-muted-foreground mt-0.5">
            {t("yarnPage.lastSynced", {
              date: new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(ravelryStatus.last_synced_at)),
            })}
          </p>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap mb-6">
        <FilterPopover
          allYarns={rawYarns}
          filters={filters}
          onChange={(f) => setPrefs({ filters: f })}
        />

        <select
          value={sort}
          onChange={(e) => setPrefs({ sort: e.target.value as SortKey })}
          className="text-xs border border-border rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          aria-label={t("yarnPage.sortLabel")}
        >
          <option value="created_at_desc">{t("yarnPage.sortNewest")}</option>
          <option value="created_at_asc">{t("yarnPage.sortOldest")}</option>
          <option value="brand_asc">{t("yarnPage.sortBrandAZ")}</option>
          <option value="brand_desc">{t("yarnPage.sortBrandZA")}</option>
          <option value="name_asc">{t("yarnPage.sortNameAZ")}</option>
          <option value="weight_asc">{t("yarnPage.sortWeightLight")}</option>
        </select>

        <div className="flex rounded-md border border-border overflow-hidden">
          {(
            [
              { key: "card" as ViewMode, Icon: LayoutList, label: "viewCard" },
              { key: "grid" as ViewMode, Icon: LayoutGrid, label: "viewGrid" },
              { key: "table" as ViewMode, Icon: Table2, label: "viewTable" },
            ]
          ).map(({ key, Icon, label }) => (
            <button
              key={key}
              onClick={() => setPrefs({ view: key })}
              title={t(`yarnPage.${label}`)}
              className={`p-1.5 transition-colors ${
                view === key
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-border" />

        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowArchived((v) => !v)}
          className="text-xs text-muted-foreground"
        >
          {showArchived ? t("yarnPage.hideArchived") : t("yarnPage.showArchived")}
        </Button>

        <Button variant="outline" size="sm" onClick={() => setShowAddFromRavelry(true)}>
          {t("yarnPage.addFromRavelryButton")}
        </Button>

        {connected && (
          <Button
            variant="outline"
            size="sm"
            disabled={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            {syncMutation.isPending ? t("common.loading") : t("yarnPage.syncButton")}
          </Button>
        )}

        {connected && eligibleForPush.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowBulkPushModal(true)}
          >
            {t("yarnPage.pushToRavelryBulkButton", { count: eligibleForPush.length })}
          </Button>
        )}

        <Button onClick={() => setShowAdd(true)}>{t("yarnPage.newButton")}</Button>
      </div>

      {/* Stash connect banner */}
      {showBanner && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-muted px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-card-foreground">{t("yarnPage.stashBannerTitle")}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t("yarnPage.stashBannerDescription")}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button size="sm" onClick={() => navigate("/settings/connections")}>
              {t("yarnPage.stashBannerConnect")}
            </Button>
            <button
              className="text-muted-foreground hover:text-foreground text-lg leading-none"
              onClick={dismissBanner}
              aria-label={t("common.dismiss")}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {syncError && <p className="text-sm text-destructive mb-4">{syncError}</p>}
      {syncResult && (
        <p className="text-sm text-muted-foreground mb-4">
          {syncResult.unchanged
            ? t("yarnPage.syncUpToDate")
            : t("yarnPage.syncComplete", { count: syncResult.synced })}
        </p>
      )}
      {bulkPushResult && (
        <p className="text-sm text-muted-foreground mb-4">
          {t("yarnPage.pushBulkSuccess", { count: bulkPushResult.pushed })}
        </p>
      )}
      {isLoading && <SkeletonCardGrid count={6} cardClassName="h-[120px]" gridClassName="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" />}
      {error && <p className="text-sm text-destructive">{t("yarnPage.loadError")}</p>}

      {/* Empty — no yarn at all */}
      {!isLoading && rawYarns.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">{t("yarnPage.emptyState")}</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowAddFromRavelry(true)}>
            {t("yarnPage.addFromRavelryButton")}
          </Button>
        </div>
      )}

      {/* Empty — filters exclude everything */}
      {!isLoading && rawYarns.length > 0 && displayYarns.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <p className="text-sm text-muted-foreground">{t("yarnPage.filterEmptyState")}</p>
          <button
            className="mt-2 text-xs text-muted-foreground hover:text-foreground underline"
            onClick={() => setPrefs({ filters: DEFAULT_FILTERS })}
          >
            {t("yarnPage.filterClearAll")}
          </button>
        </div>
      )}

      {/* Content */}
      {!isLoading && displayYarns.length > 0 && (
        <>
          {view === "card" && (
            <div className="space-y-2">
              {displayYarns.map((y) => <YarnCard key={y.id} yarn={y} connected={connected} />)}
            </div>
          )}
          {view === "grid" && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {displayYarns.map((y) => <YarnGridTile key={y.id} yarn={y} connected={connected} />)}
            </div>
          )}
          {view === "table" && (
            <YarnTable
              yarns={displayYarns}
              sort={sort}
              onSort={(key) => setPrefs({ sort: key })}
            />
          )}
        </>
      )}

      {showAdd && (
        <AddYarnModal onSuccess={handleAdded} onClose={() => setShowAdd(false)} />
      )}
      {showAddFromRavelry && (
        <AddFromRavelryModal
          onSuccess={() => { setShowAddFromRavelry(false); queryClient.invalidateQueries({ queryKey: ["yarn"] }); }}
          onClose={() => setShowAddFromRavelry(false)}
        />
      )}

      {showBulkPushModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-card border border-border rounded-xl shadow-lg max-w-sm w-full mx-4 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-card-foreground">{t("yarnPage.pushToRavelryModalTitle")}</h2>
            <p className="text-xs text-muted-foreground">{t("yarnPage.pushToRavelryModalBody")}</p>
            <ul className="max-h-48 overflow-y-auto space-y-1">
              {eligibleForPush.map((y) => (
                <li key={y.id} className="text-xs text-card-foreground truncate">
                  {y.brand} — {y.name}{y.color_name ? ` (${y.color_name})` : ""}
                </li>
              ))}
            </ul>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" size="sm" onClick={() => setShowBulkPushModal(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                size="sm"
                disabled={pushBulkMutation.isPending}
                onClick={() => pushBulkMutation.mutate()}
              >
                {pushBulkMutation.isPending ? t("common.loading") : t("yarnPage.pushToRavelryModalConfirm")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
