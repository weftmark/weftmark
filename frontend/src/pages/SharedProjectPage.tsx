import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getSharedProject,
  sharedProjectPreviewUrl,
  sharedProjectSvgUrl,
  PROJECT_STATUS_LABELS,
  type WifColor,
  type ColorStat,
} from "@/api/projects";
import { WeftmarkLogo } from "@/components/WeftmarkLogo";
import { PublicFooter } from "@/components/PublicFooter";

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    created: "bg-blue-100 text-blue-700",
    active: "bg-green-100 text-green-800",
    completed: "bg-stone-100 text-stone-600",
    abandoned: "bg-stone-100 text-stone-500",
  };
  const label = PROJECT_STATUS_LABELS[status as keyof typeof PROJECT_STATUS_LABELS] ?? status;
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${colors[status] ?? "bg-stone-100 text-stone-600"}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Progress bar
// ---------------------------------------------------------------------------

function ProgressBar({ current, total }: { current: number; total: number }) {
  const { t } = useTranslation();
  const done = Math.max(0, current - 1);
  const pct = Math.min(100, Math.round((done / Math.max(total, 1)) * 100));
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-stone-500">
        <span>{t("sharedProjectPage.progress")}</span>
        <span className="tabular-nums">{t("sharedProjectPage.picks", { done: done.toLocaleString(), total: total.toLocaleString(), pct })}</span>
      </div>
      <div className="h-2 w-full rounded-full bg-stone-200 overflow-hidden">
        <div
          className="h-full rounded-full bg-amber-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drawdown with progress haze overlay
// ---------------------------------------------------------------------------

function DrawdownWithHaze({
  previewUrl,
  svgUrl,
  currentPick,
  totalPicks,
  isActive,
}: {
  previewUrl: string;
  svgUrl: string;
  currentPick: number;
  totalPicks: number;
  isActive: boolean;
}) {
  const { t } = useTranslation();
  const [showHaze, setShowHaze] = useState(true);
  const [imgError, setImgError] = useState(false);
  const [useSvg, setUseSvg] = useState(false);

  // Weaving builds from the bottom up: completed picks are at the BOTTOM of the
  // image (woven first), uncompleted picks are at the TOP.
  const completedFraction = totalPicks > 0 ? Math.min(1, Math.max(0, (currentPick - 1) / totalPicks)) : 0;
  const uncompletedPct = (1 - completedFraction) * 100;

  const src = useSvg ? svgUrl : previewUrl;

  return (
    <div className="space-y-3">
      <div className="relative rounded-lg overflow-hidden border border-stone-200 bg-stone-100 flex justify-center">
        {imgError ? (
          <div className="flex items-center justify-center h-48 text-stone-400 text-sm">
            {t("sharedProjectPage.drawdownNotAvailable")}
          </div>
        ) : (
          <>
            <img
              src={src}
              alt="Drawdown"
              className="block w-full object-contain max-h-[480px]"
              onError={() => {
                if (!useSvg) {
                  setUseSvg(true);
                } else {
                  setImgError(true);
                }
              }}
            />
            {isActive && showHaze && uncompletedPct > 0 && (
              <div
                className="absolute inset-x-0 top-0 pointer-events-none"
                style={{
                  height: `${uncompletedPct}%`,
                  background: "rgba(255,255,255,0.60)",
                  backdropFilter: "blur(2px)",
                }}
              />
            )}
          </>
        )}
      </div>

      {isActive && (
        <div className="flex items-center gap-2.5 px-1">
          <span className="text-xs text-stone-500 select-none">{t("sharedProjectPage.showProgress")}</span>
          <button
            role="switch"
            aria-checked={showHaze}
            onClick={() => setShowHaze((v) => !v)}
            className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${showHaze ? "bg-amber-500" : "bg-stone-300"}`}
          >
            <span
              className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${showHaze ? "translate-x-4" : "translate-x-0"}`}
            />
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Color palette
// ---------------------------------------------------------------------------

function ColorPaletteTable({
  wifColors,
  warpStats,
  weftStats,
  colorReplacements,
}: {
  wifColors: WifColor[];
  warpStats: ColorStat[] | null;
  weftStats: ColorStat[] | null;
  colorReplacements: Record<string, string> | null;
}) {
  const { t } = useTranslation();
  const bothPresent = warpStats !== null && weftStats !== null;
  const visibleColors = bothPresent
    ? wifColors.filter(
        (c) => warpStats!.some((s) => s.hex === c.hex) || weftStats!.some((s) => s.hex === c.hex)
      )
    : wifColors;

  if (visibleColors.length === 0) return null;

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide">{t("sharedProjectPage.colorPalette")}</h2>
      <div className="rounded-lg border border-stone-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-stone-200 bg-stone-50 text-stone-500 text-xs uppercase tracking-wide">
              <th className="px-3 py-2 text-left">{t("sharedProjectPage.color")}</th>
              <th className="px-3 py-2 text-right">{t("sharedProjectPage.warpEnds")}</th>
              <th className="px-3 py-2 text-right">{t("sharedProjectPage.weftPicks")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {visibleColors.map((c) => {
              const displayHex = colorReplacements?.[c.hex] ?? c.hex;
              const warp = warpStats?.find((s) => s.hex === c.hex);
              const weft = weftStats?.find((s) => s.hex === c.hex);
              return (
                <tr key={c.hex} className="bg-white">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span
                        className="inline-block h-5 w-5 rounded border border-stone-200 shrink-0"
                        style={{ background: displayHex }}
                      />
                      <span className="font-mono text-xs text-stone-400">
                        {c.hex}
                        {colorReplacements?.[c.hex] && (
                          <span className="ml-1 text-amber-600"> → {colorReplacements[c.hex]}</span>
                        )}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-stone-600">
                    {warp ? `${warp.count} (${warp.percentage}%)` : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-stone-600">
                    {weft ? `${weft.count} (${weft.percentage}%)` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Info row
// ---------------------------------------------------------------------------

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 border-b border-stone-100 last:border-0">
      <span className="text-sm text-stone-500 shrink-0">{label}</span>
      <span className="text-sm text-stone-800 text-right">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function SharedProjectPage() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["shared-project", slug],
    queryFn: () => getSharedProject(slug!),
    enabled: !!slug,
    retry: false,
  });

  const isExpired = (error as { status?: number } | null)?.status === 410;
  const isNotFound = (error as { status?: number } | null)?.status === 404;

  const isActive = data?.project_status === "active" || data?.project_status === "created";
  const hasDrawdown = data?.has_drawdown_svg || data?.has_drawdown_preview;

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <Link to="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
            <WeftmarkLogo className="h-8 w-auto text-amber-800" />
            <span className="text-lg font-semibold tracking-tight" style={{ fontFamily: '"Segoe UI", system-ui, sans-serif' }}>
              weftmark
            </span>
          </Link>
        </div>
      </header>

      <main className="flex-1 px-4 py-10">
        <div className="mx-auto max-w-3xl space-y-8">

          {isLoading && (
            <div className="text-sm text-stone-400 text-center mt-16">{t("sharedProjectPage.loading")}</div>
          )}

          {isError && isExpired && (
            <div className="text-center space-y-3 mt-16">
              <h1 className="text-2xl font-bold text-stone-800">{t("sharedProjectPage.linkExpired")}</h1>
              <p className="text-stone-500 text-sm">{t("sharedProjectPage.linkExpiredDesc")}</p>
            </div>
          )}

          {isError && isNotFound && !isExpired && (
            <div className="text-center space-y-3 mt-16">
              <h1 className="text-2xl font-bold text-stone-800">{t("sharedProjectPage.notFound")}</h1>
              <p className="text-stone-500 text-sm">{t("sharedProjectPage.notFoundDesc")}</p>
            </div>
          )}

          {isError && !isExpired && !isNotFound && (
            <div className="text-center space-y-3 mt-16">
              <h1 className="text-2xl font-bold text-stone-800">{t("sharedProjectPage.errorTitle")}</h1>
              <p className="text-stone-500 text-sm">{t("sharedProjectPage.errorDesc")}</p>
            </div>
          )}

          {data && (
            <>
              {/* Header */}
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h1 className="text-2xl font-bold tracking-tight text-stone-900">{data.project_name}</h1>
                  <StatusBadge status={data.project_status} />
                </div>
                <p className="text-sm text-stone-500">
                  {t("sharedProjectPage.sharedBy")} <span className="font-medium text-stone-700">{data.owner_display_name}</span>
                  {" · "}
                  <span className="capitalize">{t("sharedProjectPage.typeTracking", { type: data.project_type })}</span>
                  {" · "}
                  <span className="italic">{data.draft_name}</span>
                </p>
              </div>

              {/* Drawdown with haze overlay */}
              {slug && hasDrawdown && (
                <DrawdownWithHaze
                  previewUrl={sharedProjectPreviewUrl(slug)}
                  svgUrl={sharedProjectSvgUrl(slug)}
                  currentPick={data.current_pick}
                  totalPicks={data.total_picks}
                  isActive={!!isActive}
                />
              )}

              {/* Progress bar */}
              {(data.project_status === "active" || data.project_status === "created") && (
                <ProgressBar current={data.current_pick} total={data.total_picks} />
              )}

              {/* Project info */}
              <div className="rounded-lg border border-stone-200 bg-white px-4 py-1">
                {data.draft_num_shafts != null && (
                  <InfoRow label={t("sharedProjectPage.shafts")} value={data.draft_num_shafts} />
                )}
                {data.draft_num_treadles != null && data.project_type === "treadle" && (
                  <InfoRow label={t("sharedProjectPage.treadles")} value={data.draft_num_treadles} />
                )}
                <InfoRow label={t("sharedProjectPage.totalPicks")} value={data.total_picks.toLocaleString()} />
                {data.num_items > 1 && (
                  <InfoRow label={t("sharedProjectPage.items")} value={data.num_items} />
                )}
                {data.project_status === "active" && data.num_items > 1 && (
                  <InfoRow
                    label={t("sharedProjectPage.currentItem")}
                    value={t("sharedProjectPage.itemOf", { current: data.current_item, total: data.num_items })}
                  />
                )}
                {data.completed_at && (
                  <InfoRow label={t("sharedProjectPage.completed")} value={new Date(data.completed_at).toLocaleDateString()} />
                )}
                {data.abandoned_at && (
                  <InfoRow label={t("sharedProjectPage.abandoned")} value={new Date(data.abandoned_at).toLocaleDateString()} />
                )}
                <InfoRow label={t("sharedProjectPage.started")} value={new Date(data.created_at).toLocaleDateString()} />
              </div>

              {/* Color palette */}
              {data.draft_wif_colors && data.draft_wif_colors.length > 0 && (
                <ColorPaletteTable
                  wifColors={data.draft_wif_colors}
                  warpStats={data.draft_warp_color_stats}
                  weftStats={data.draft_weft_color_stats}
                  colorReplacements={data.color_replacements}
                />
              )}

              {/* Expiry note */}
              {data.share_expires_at && (
                <p className="text-xs text-stone-400 text-center">
                  {t("sharedProjectPage.linkExpires", { date: new Date(data.share_expires_at).toLocaleDateString() })}
                </p>
              )}
            </>
          )}
        </div>
      </main>

      <PublicFooter />
    </div>
  );
}
