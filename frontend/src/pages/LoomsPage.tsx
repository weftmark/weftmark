import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { listLooms, loomPhotoUrl, type Loom } from "@/api/looms";
import { AppIcons } from "@/lib/icons";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { listProjects } from "@/api/projects";
import { NewLoomModal } from "@/components/looms/NewLoomModal";
import { Button } from "@/components/ui/button";
import { SkeletonCardGrid } from "@/components/ui/skeleton";

interface LoomProjectCounts {
  active: number;
  completed: number;
  abandoned: number;
}

function LoomCard({ loom, projectCounts, retired }: { loom: Loom; projectCounts?: LoomProjectCounts; retired?: boolean }) {
  const { t } = useTranslation();
  const v = loom.current_version;
  return (
    <Link
      to={`/looms/${loom.id}`}
      className="rounded-lg border hover:border-ring transition-colors block overflow-hidden"
    >
      {loom.has_photo && (
        <div className="w-full h-32 bg-muted overflow-hidden">
          <AuthedImage
            src={loomPhotoUrl(loom.id)}
            alt=""
            className="w-full h-full object-cover"
          />
        </div>
      )}
      <div className="p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3">
          <div className="shrink-0 mt-0.5">
            {loom.supports_lift_tracking
              ? <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
              : loom.supports_treadle_tracking
                ? <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                : <AppIcons.equipment className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />}
          </div>
          <div>
            <p className="font-medium">{loom.manufacturer} {loom.model_name}</p>
            {loom.serial_number && (
              <p className="text-xs text-muted-foreground">S/N: {loom.serial_number}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-right text-xs text-muted-foreground">
          {retired && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{t("loomsPage.retiredBadge")}</span>
          )}
          {v && (
            <span>
              {v.num_shafts != null ? `${v.num_shafts}S` : null}
              {v.num_shafts != null && v.num_treadles != null ? " / " : null}
              {v.num_treadles != null ? `${v.num_treadles}T` : null}
            </span>
          )}
        </div>
      </div>
      {v?.weaving_width && (
        <p className="mt-2 text-sm text-muted-foreground">
          {t("loomsPage.weavingWidth", { width: v.weaving_width, unit: v.weaving_width_unit })}
        </p>
      )}
      <div className="mt-2 flex gap-2">
        {loom.supports_lift_tracking && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{t("loomsPage.liftTracking")}</span>
        )}
        {loom.supports_treadle_tracking && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs">{t("loomsPage.treadleTracking")}</span>
        )}
      </div>
      {projectCounts && (projectCounts.active + projectCounts.completed + projectCounts.abandoned) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t pt-2.5">
          {projectCounts.active > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
              {t("loomsPage.activeCount", { count: projectCounts.active })}
            </span>
          )}
          {projectCounts.completed > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {t("loomsPage.completedCount", { count: projectCounts.completed })}
            </span>
          )}
          {projectCounts.abandoned > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {t("loomsPage.abandonedCount", { count: projectCounts.abandoned })}
            </span>
          )}
        </div>
      )}
      </div>
    </Link>
  );
}

export function LoomsPage() {
  const { t } = useTranslation();
  const [showNew, setShowNew] = useState(false);
  const [retiredOpen, setRetiredOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: looms, isLoading, error } = useQuery({
    queryKey: ["looms", { includeRetired: true }],
    queryFn: () => listLooms(true),
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const projectCountsByLoom = projects.reduce<Record<string, LoomProjectCounts>>(
    (acc, a) => {
      if (!a.loom_id) return acc;
      if (!acc[a.loom_id]) acc[a.loom_id] = { active: 0, completed: 0, abandoned: 0 };
      if (a.status === "active") acc[a.loom_id].active++;
      else if (a.status === "completed") acc[a.loom_id].completed++;
      else if (a.status === "abandoned") acc[a.loom_id].abandoned++;
      return acc;
    },
    {},
  );

  const handleSuccess = () => {
    setShowNew(false);
    queryClient.invalidateQueries({ queryKey: ["looms"] });
  };

  const activeLooms = (looms ?? []).filter((l) => !l.retired_at);
  const retiredLooms = (looms ?? []).filter((l) => l.retired_at);

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-xl font-semibold">{t("loomsPage.title")}</h1>
        <Button size="sm" onClick={() => setShowNew(true)}>{t("loomsPage.newButton")}</Button>
      </div>
      <div className="mb-6">
        <Link to="/catalog/looms" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          {t("loomsPage.catalogLink")}
        </Link>
      </div>

      {isLoading && <SkeletonCardGrid count={3} cardClassName="h-[160px]" />}
      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {t("loomsPage.loadError")}
        </p>
      )}

      {looms && activeLooms.length === 0 && retiredLooms.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <p className="text-muted-foreground">{t("loomsPage.emptyState")}</p>
          <Button className="mt-4" onClick={() => setShowNew(true)}>
            {t("loomsPage.addFirst")}
          </Button>
        </div>
      )}

      {activeLooms.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {activeLooms.map((l) => (
            <LoomCard key={l.id} loom={l} projectCounts={projectCountsByLoom[l.id]} />
          ))}
        </div>
      )}

      {retiredLooms.length > 0 && (
        <div className="mt-8">
          <button
            type="button"
            onClick={() => setRetiredOpen((v) => !v)}
            className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors w-full text-left"
          >
            <AppIcons.chevronDown
              className={`h-4 w-4 transition-transform duration-200 ${retiredOpen ? "rotate-180" : ""}`}
            />
            {t("loomsPage.retired", { count: retiredLooms.length })}
          </button>
          {retiredOpen && (
            <div className="mt-3 grid gap-4 sm:grid-cols-2 opacity-60">
              {retiredLooms.map((l) => (
                <LoomCard key={l.id} loom={l} projectCounts={projectCountsByLoom[l.id]} retired />
              ))}
            </div>
          )}
        </div>
      )}

      {showNew && (
        <NewLoomModal onSuccess={handleSuccess} onClose={() => setShowNew(false)} />
      )}
    </div>
  );
}
