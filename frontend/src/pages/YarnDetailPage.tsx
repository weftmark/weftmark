import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getYarn, updateYarn } from "@/api/yarn";
import { getRavelryYarnDetail, type RavelryYarnApiDetail } from "@/api/ravelry";
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
          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {yarn.color_name && (
              <span className="rounded-full bg-muted text-muted-foreground px-2.5 py-0.5 text-xs">
                {yarn.color_name}
              </span>
            )}
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
