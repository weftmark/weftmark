import { useState, useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listYarn, yarnPhotoUrl, type YarnSummary } from "@/api/yarn";
import { getRavelryStatus, syncRavelryStash } from "@/api/ravelry";
import { AddYarnModal } from "@/components/yarn/AddYarnModal";
import { AddFromRavelryModal } from "@/components/yarn/AddFromRavelryModal";
import { Button } from "@/components/ui/button";
import { AuthedImage } from "@/components/ui/AuthedImage";

const BANNER_KEY = "ravelry_stash_banner_dismissed";

function YarnCard({ yarn }: { yarn: YarnSummary }) {
  const { t } = useTranslation();

  return (
    <Link
      to={`/yarn/${yarn.id}`}
      className="relative flex items-start gap-3 rounded-lg border p-4 hover:border-ring transition-colors"
    >
      <div className="shrink-0 flex rounded-md overflow-hidden border border-border h-14">
        {(() => {
          const photoUrl = yarn.ravelry_colorway_thumbnail_url ?? yarn.ravelry_colorway_photo_url ?? yarn.ravelry_thumbnail_url ?? yarn.ravelry_photo_url;
          if (photoUrl) {
            return <img src={photoUrl} alt={`${yarn.brand} ${yarn.name}`} className="h-14 w-14 object-cover" />;
          }
          if (yarn.has_photo) {
            return <AuthedImage src={yarnPhotoUrl(yarn.id)} alt={`${yarn.brand} ${yarn.name}`} className="h-14 w-14 object-cover" />;
          }
          return (
            <div className="h-14 w-14 flex items-center justify-center bg-muted">
              <span className="text-xs text-muted-foreground">?</span>
            </div>
          );
        })()}
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

      {yarn.unit_yardage && (
        <div className="text-right shrink-0">
          <p className="text-xs text-muted-foreground">{yarn.unit_yardage} {t("yarnPage.yardsPerUnit")}</p>
        </div>
      )}
      {yarn.ravelry_stash_id !== null && !yarn.out_of_stash && (
        <span className="absolute bottom-2 right-3 rounded px-1.5 py-0.5 text-[10px] bg-accent/10 text-accent">
          {t("yarnPage.inRavelryStash")}
        </span>
      )}
    </Link>
  );
}

export function YarnPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [showAddFromRavelry, setShowAddFromRavelry] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<{ synced: number; unchanged: boolean } | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(
    () => localStorage.getItem(BANNER_KEY) === "1"
  );

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

  const { data: yarns = [], isLoading: yarnsLoading, error } = useQuery({
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

  const handleAdded = () => {
    setShowAdd(false);
    queryClient.invalidateQueries({ queryKey: ["yarn"] });
  };

  return (
    <div className="p-6 max-w-3xl mx-auto w-full">
      <div className="flex items-center justify-between mb-4">
        <div>
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
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowArchived((v) => !v)}
            className="text-xs text-muted-foreground"
          >
            {showArchived ? t("yarnPage.hideArchived") : t("yarnPage.showArchived")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowAddFromRavelry(true)}
          >
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
        </div>
      </div>

      {/* Stash connect banner — shown when not connected and not dismissed */}
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
      {yarnsLoading && <p className="text-sm text-muted-foreground">{t("common.loading")}</p>}
      {error && <p className="text-sm text-destructive">{t("yarnPage.loadError")}</p>}

      {!yarnsLoading && yarns.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">{t("yarnPage.emptyState")}</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowAddFromRavelry(true)}>
            {t("yarnPage.addFromRavelryButton")}
          </Button>
        </div>
      )}

      <div className="space-y-2">
        {yarns.map((y) => <YarnCard key={y.id} yarn={y} />)}
      </div>

      {showAdd && (
        <AddYarnModal onSuccess={handleAdded} onClose={() => setShowAdd(false)} />
      )}
      {showAddFromRavelry && (
        <AddFromRavelryModal
          onSuccess={() => { setShowAddFromRavelry(false); queryClient.invalidateQueries({ queryKey: ["yarn"] }); }}
          onClose={() => setShowAddFromRavelry(false)}
        />
      )}
    </div>
  );
}
