import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getYarn, updateYarn, patchYarnColorway } from "@/api/yarn";
import { getRavelryYarnDetail, type RavelryColorway, type RavelryYarnApiDetail } from "@/api/ravelry";
import { Button } from "@/components/ui/button";
import { ColorPicker } from "@/components/ui/ColorPicker";

function DevJsonModal({ data, onClose }: { data: unknown; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="relative bg-card border border-border rounded-xl shadow-lg max-w-2xl w-full max-h-[80vh] overflow-auto m-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <span className="text-xs font-mono font-semibold text-accent">DEV — raw data</span>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">×</button>
        </div>
        <pre className="p-4 text-xs font-mono text-card-foreground whitespace-pre-wrap break-all">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  );
}

const WEIGHT_LABELS: Record<string, string> = {
  thread: "Thread",
  lace: "Lace",
  fingering: "Fingering",
  sport: "Sport",
  dk: "DK",
  worsted: "Worsted",
  aran: "Aran",
  bulky: "Bulky",
  super_bulky: "Super Bulky",
};

// ---------------------------------------------------------------------------
// Edit colorway modal
// ---------------------------------------------------------------------------

function EditColorwayModal({
  yarn,
  onClose,
  onSaved,
}: {
  yarn: { id: string; color_name: string | null; ravelry_yarn_id: number | null };
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<"rename" | "link">("rename");
  const [colorName, setColorName] = useState(yarn.color_name ?? "");
  const [colorways, setColorways] = useState<RavelryColorway[]>([]);
  const [colorwaysLoading, setColorwaysLoading] = useState(false);
  const [colorwayFilter, setColorwayFilter] = useState("");
  const [selectedColorway, setSelectedColorway] = useState<RavelryColorway | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filteredColorways = useMemo(() => {
    if (!colorwayFilter.trim()) return colorways;
    const q = colorwayFilter.toLowerCase();
    return colorways.filter((cw) => cw.name.toLowerCase().includes(q));
  }, [colorways, colorwayFilter]);

  async function loadColorways() {
    if (!yarn.ravelry_yarn_id || colorways.length > 0) return;
    setColorwaysLoading(true);
    try {
      const { getRavelryYarnDetail: _getRavelryYarnDetail } = await import("@/api/ravelry");
      const resp = await _getRavelryYarnDetail(yarn.ravelry_yarn_id);
      setColorways(resp.colorways ?? []);
    } catch {
      setError(t("yarnDetailPage.colorwayLoadError"));
    } finally {
      setColorwaysLoading(false);
    }
  }

  function handleTabChange(next: "rename" | "link") {
    setTab(next);
    if (next === "link") loadColorways();
  }

  function pickColorway(cw: RavelryColorway) {
    setSelectedColorway(cw);
    setColorName(cw.name);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload: Parameters<typeof patchYarnColorway>[1] = {
        color_name: colorName.trim() || null,
      };
      if (tab === "link" && selectedColorway) {
        payload.colorway_photo_url = selectedColorway.photos?.[0]?.square_url ?? null;
        payload.colorway_thumbnail_url = selectedColorway.photos?.[0]?.thumbnail_url ?? null;
      } else if (tab === "rename") {
        payload.clear_photos = true;
      }
      await patchYarnColorway(yarn.id, payload);
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("common.error"));
    } finally {
      setSaving(false);
    }
  }

  const inputCls = "w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl border border-border bg-card shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h2 className="text-sm font-semibold">{t("yarnDetailPage.editColorwayTitle")}</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">×</button>
        </div>

        {yarn.ravelry_yarn_id && (
          <div className="flex border-b border-border">
            {(["rename", "link"] as const).map((t_) => (
              <button
                key={t_}
                onClick={() => handleTabChange(t_)}
                className={`flex-1 px-4 py-2.5 text-xs font-medium transition-colors ${
                  tab === t_
                    ? "border-b-2 border-accent text-accent"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t_ === "rename" ? t("yarnDetailPage.renameTab") : t("yarnDetailPage.linkRavelryTab")}
              </button>
            ))}
          </div>
        )}

        <div className="px-5 py-4 space-y-3 max-h-[60vh] overflow-y-auto">
          {tab === "link" && (
            <>
              {colorwaysLoading && <p className="text-xs text-muted-foreground">{t("common.loading")}</p>}
              {!colorwaysLoading && colorways.length > 6 && (
                <div className="relative">
                  <input
                    className={inputCls}
                    placeholder={t("yarnDetailPage.colorwayFilter")}
                    value={colorwayFilter}
                    onChange={(e) => setColorwayFilter(e.target.value)}
                  />
                  {colorwayFilter && (
                    <button className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs" onClick={() => setColorwayFilter("")}>✕</button>
                  )}
                </div>
              )}
              {!colorwaysLoading && filteredColorways.length === 0 && (
                <p className="text-xs text-muted-foreground">{t("yarnDetailPage.noColorways")}</p>
              )}
              {filteredColorways.length > 0 && (
                <div className="grid grid-cols-3 gap-1.5">
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
                      <span className="truncate block leading-tight">{cw.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">{t("yarnDetailPage.colorNameLabel")}</label>
            <input
              className={inputCls}
              placeholder={t("yarnDetailPage.colorNamePlaceholder")}
              value={colorName}
              onChange={(e) => setColorName(e.target.value)}
              autoFocus={tab === "rename"}
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-border">
          <Button variant="outline" size="sm" onClick={onClose} disabled={saving}>{t("common.cancel")}</Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Color picker section
// ---------------------------------------------------------------------------

function ColorSection({ yarn, onSaved }: { yarn: { id: string; color_hex: string | null; ravelry_stash_id: number | null }; onSaved: () => void }) {
  const { t } = useTranslation();
  const [colorHex, setColorHex] = useState(yarn.color_hex ?? "#888888");
  const [saving, setSaving] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateYarn(yarn.id, { color_hex: colorHex });
      onSaved();
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h2 className="text-sm font-medium text-card-foreground">{t("yarnDetailPage.color")}</h2>
      <div className="flex items-center gap-3">
        <div
          className="h-10 w-10 rounded-md border border-border shrink-0"
          style={{ backgroundColor: colorHex }}
        />
        <ColorPicker value={colorHex} onChange={setColorHex} />
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {savedFlash ? t("yarnDetailPage.saved") : t("yarnDetailPage.saveColor")}
        </Button>
      </div>
      {yarn.ravelry_stash_id && (
        <p className="text-xs text-muted-foreground">{t("yarnDetailPage.colorHint")}</p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Ravelry attributes section
// ---------------------------------------------------------------------------

function RavelrySection({ ry, companyUrl, permalink }: {
  ry: RavelryYarnApiDetail;
  companyUrl: string | null;
  permalink: string | null;
}) {
  const { t } = useTranslation();

  const ravelryUrl = permalink
    ? `https://www.ravelry.com/yarns/library/${permalink}`
    : null;

  const gaugeStr = (() => {
    if (!ry.min_gauge && !ry.max_gauge) return null;
    const range = ry.min_gauge === ry.max_gauge
      ? `${ry.min_gauge}`
      : `${ry.min_gauge ?? "?"}–${ry.max_gauge ?? "?"}`;
    const divisor = ry.gauge_divisor ? `${ry.gauge_divisor} in` : null;
    const pattern = ry.gauge_pattern;
    return [range, "sts", divisor ? `/ ${divisor}` : null, pattern ? `(${pattern})` : null]
      .filter(Boolean).join(" ");
  })();

  const fibers = ry.fiber_contents?.filter(f => f.fiber_category?.name) ?? [];

  const ratingStr = ry.rating_average && ry.rating_count
    ? t("yarnDetailPage.rating", { avg: parseFloat(ry.rating_average).toFixed(2), count: ry.rating_count.toLocaleString() })
    : null;

  const attributes: string[] = [
    fibers.length === 1 ? `${fibers[0].percentage ?? 100}% ${fibers[0].fiber_category.name}` : null,
    ry.grams ? t("yarnDetailPage.gramsPerSkein", { grams: ry.grams }) : null,
    gaugeStr ? t("yarnDetailPage.gauge", { gauge: gaugeStr }) : null,
    ry.wpi ? t("yarnDetailPage.wpi", { wpi: ry.wpi }) : null,
    ratingStr,
  ].filter(Boolean) as string[];

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-4">
      <h2 className="text-sm font-medium text-card-foreground">{t("yarnDetailPage.ravelrySection")}</h2>

      {/* Multi-fiber breakdown */}
      {fibers.length > 1 && (
        <ul className="space-y-1">
          {fibers.map((f, i) => (
            <li key={i} className="text-sm text-muted-foreground flex gap-2">
              <span className="text-card-foreground font-medium w-12 text-right shrink-0">
                {f.percentage != null ? `${f.percentage}%` : "—"}
              </span>
              <span>{f.fiber_category.name}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Attribute bullets */}
      {attributes.length > 0 && (
        <ul className="space-y-1 text-sm text-muted-foreground list-none">
          {attributes.map((attr, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-accent mt-0.5">•</span>
              <span>{attr}</span>
            </li>
          ))}
        </ul>
      )}

      {/* Links */}
      <div className="flex flex-col gap-1.5">
        {ravelryUrl && (
          <a
            href={ravelryUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-accent hover:text-accent/80 flex items-center gap-1"
          >
            {t("yarnDetailPage.viewOnRavelry")}
            <span className="text-xs opacity-60">↗</span>
          </a>
        )}
        {companyUrl && (
          <a
            href={companyUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-accent hover:text-accent/80 flex items-center gap-1"
          >
            {ry.yarn_company?.name
              ? t("yarnDetailPage.manufacturerWebsite", { company: ry.yarn_company.name })
              : t("yarnDetailPage.manufacturerWebsiteFallback")}
            <span className="text-xs opacity-60">↗</span>
          </a>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function YarnDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [showDebug, setShowDebug] = useState(false);
  const [showEditColorway, setShowEditColorway] = useState(false);
  const [ravelryRawData, setRavelryRawData] = useState<unknown>(null);
  const [ravelryLoading, setRavelryLoading] = useState(false);

  const { data: yarn, isLoading, error } = useQuery({
    queryKey: ["yarn", id],
    queryFn: () => getYarn(id!),
    enabled: !!id,
  });

  const { data: ravelryYarnResp } = useQuery({
    queryKey: ["ravelry-yarn-detail", yarn?.ravelry_yarn_id],
    queryFn: async () => {
      const resp = await getRavelryYarnDetail(yarn!.ravelry_yarn_id!);
      // Backfill photo URLs into DB if not already stored so the list card shows them too
      if (yarn && resp.yarn.photos?.length) {
        const sorted = [...resp.yarn.photos].sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999));
        const best = sorted[0];
        const photoUrl = best.medium_url ?? best.small_url ?? best.square_url;
        const thumbUrl = best.square_url ?? best.thumbnail_url ?? best.small_url;
        if (photoUrl && (!yarn.ravelry_photo_url || !yarn.ravelry_thumbnail_url)) {
          updateYarn(yarn.id, {
            ravelry_photo_url: yarn.ravelry_photo_url ?? photoUrl,
            ravelry_thumbnail_url: yarn.ravelry_thumbnail_url ?? thumbUrl,
          }).then(() => {
            queryClient.invalidateQueries({ queryKey: ["yarn"] });
          }).catch(() => {/* non-critical */});
        }
      }
      return resp;
    },
    enabled: !!yarn?.ravelry_yarn_id,
    staleTime: 5 * 60 * 1000,
  });
  const ry = ravelryYarnResp?.yarn ?? null;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["yarn", id] });
    queryClient.invalidateQueries({ queryKey: ["yarn"] });
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">{t("yarnDetailPage.loading")}</p>
      </div>
    );
  }
  if (error || !yarn) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-destructive">{t("yarnDetailPage.notFound")}</p>
      </div>
    );
  }

  const isDevEnv = import.meta.env.VITE_APP_ENV === "dev";
  const weightLabel = yarn.weight_category ? (WEIGHT_LABELS[yarn.weight_category] ?? yarn.weight_category) : null;
  const weightDisplay = [weightLabel, yarn.weight_notation ? `(${yarn.weight_notation})` : null].filter(Boolean).join(" ");

  // Best photo: colorway-specific first, then live Ravelry yarn API photo, then stored generic yarn photo
  const heroPhoto = ry?.photos?.length
    ? [...ry.photos].sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999))[0]
    : null;
  const heroPhotoUrl =
    yarn.ravelry_colorway_photo_url ??
    heroPhoto?.medium_url ?? heroPhoto?.small_url ?? heroPhoto?.square_url ??
    yarn.ravelry_photo_url;

  return (
    <div className="p-6 max-w-2xl mx-auto w-full space-y-6">

      {/* Breadcrumb */}
      <div className="flex items-center text-sm">
        <Link to="/yarn" className="text-muted-foreground hover:text-foreground">
          ← {t("yarnDetailPage.breadcrumb")}
        </Link>
      </div>

      {showDebug && <DevJsonModal data={yarn} onClose={() => setShowDebug(false)} />}
      {ravelryRawData !== null && <DevJsonModal data={ravelryRawData} onClose={() => setRavelryRawData(null)} />}
      {showEditColorway && (
        <EditColorwayModal
          yarn={yarn}
          onClose={() => setShowEditColorway(false)}
          onSaved={() => queryClient.invalidateQueries({ queryKey: ["yarn", id] })}
        />
      )}

      {/* Hero: photo + title block */}
      <div className="flex gap-5 items-start">
        {heroPhotoUrl ? (
          <img
            src={heroPhotoUrl}
            alt={`${yarn.brand} ${yarn.name}`}
            className="h-36 w-36 rounded-xl object-cover border border-border shrink-0"
          />
        ) : yarn.color_hex ? (
          <div
            className="h-36 w-36 rounded-xl border border-border shrink-0"
            style={{ backgroundColor: yarn.color_hex }}
          />
        ) : (
          <div className="h-36 w-36 rounded-xl border border-dashed border-border flex items-center justify-center text-xs text-muted-foreground shrink-0">
            {t("yarnDetailPage.noPhoto")}
          </div>
        )}

        <div className="flex-1 min-w-0 space-y-1.5 pt-1">
          <h1 className="text-xl font-semibold text-card-foreground leading-tight">{yarn.brand}</h1>
          <p className="text-muted-foreground">{yarn.name}</p>

          {/* Tags row */}
          <div className="flex flex-wrap gap-1.5 pt-0.5 items-center">
            <button
              onClick={() => setShowEditColorway(true)}
              title={t("yarnDetailPage.editColorway")}
              className="flex items-center gap-1 rounded-full bg-muted text-muted-foreground px-2.5 py-0.5 text-xs hover:bg-accent/20 hover:text-foreground transition-colors"
            >
              {yarn.color_name ?? <span className="italic">{t("yarnDetailPage.noColorway")}</span>}
              <svg className="h-3 w-3 shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M11.5 2.5a1.414 1.414 0 0 1 2 2L5 13H3v-2L11.5 2.5Z" strokeLinejoin="round"/>
              </svg>
            </button>
            {yarn.ravelry_discontinued && (
              <span className="rounded-full bg-destructive/10 text-destructive px-2.5 py-0.5 text-xs font-medium">
                {t("yarnDetailPage.discontinued")}
              </span>
            )}
            {yarn.ravelry_machine_washable && (
              <span className="rounded-full bg-muted text-muted-foreground px-2.5 py-0.5 text-xs">
                {t("yarnDetailPage.machineWashable")}
              </span>
            )}
            {yarn.out_of_stash && (
              <span className="rounded-full bg-muted text-muted-foreground px-2.5 py-0.5 text-xs">
                {t("yarnPage.outOfStash")}
              </span>
            )}
          </div>

        </div>
      </div>

      {/* Quick details */}
      {(yarn.fiber_content || weightDisplay || yarn.unit_yardage || isDevEnv) && (
        <section className="rounded-lg border border-border bg-card p-4">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
            {yarn.fiber_content && (
              <>
                <dt className="text-muted-foreground">{t("yarnDetailPage.fiber")}</dt>
                <dd className="text-card-foreground sm:col-span-2">{yarn.fiber_content}</dd>
              </>
            )}
            {weightDisplay && (
              <>
                <dt className="text-muted-foreground">{t("yarnDetailPage.weight")}</dt>
                <dd className="text-card-foreground sm:col-span-2">{weightDisplay}</dd>
              </>
            )}
            {yarn.unit_yardage && (
              <>
                <dt className="text-muted-foreground">{t("yarnDetailPage.yardagePerSkein")}</dt>
                <dd className="text-card-foreground sm:col-span-2">{yarn.unit_yardage} yds</dd>
              </>
            )}
          </dl>
          {isDevEnv && (
            <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-4">
              <button
                onClick={() => setShowDebug(true)}
                className="text-xs font-mono text-accent hover:text-accent/80"
              >
                DEV: stash entry JSON
              </button>
              {yarn.ravelry_yarn_id && (
                <button
                  onClick={async () => {
                    setRavelryLoading(true);
                    try {
                      const data = await getRavelryYarnDetail(yarn.ravelry_yarn_id!);
                      setRavelryRawData(data);
                    } finally {
                      setRavelryLoading(false);
                    }
                  }}
                  disabled={ravelryLoading}
                  className="text-xs font-mono text-accent hover:text-accent/80 disabled:opacity-50"
                >
                  {ravelryLoading ? "loading…" : "DEV: Ravelry yarn JSON"}
                </button>
              )}
            </div>
          )}
        </section>
      )}

      {/* Ravelry rich section */}
      {ry && (
        <RavelrySection
          ry={ry}
          companyUrl={yarn.ravelry_yarn_company_url}
          permalink={yarn.ravelry_permalink}
        />
      )}

      {/* Color picker */}
      <ColorSection yarn={yarn} onSaved={invalidate} />

      {/* Notes */}
      {yarn.notes && (
        <section className="rounded-lg border border-border bg-card p-4 space-y-2">
          <h2 className="text-sm font-medium text-card-foreground">{t("yarnDetailPage.notes")}</h2>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">{yarn.notes}</p>
        </section>
      )}

    </div>
  );
}
