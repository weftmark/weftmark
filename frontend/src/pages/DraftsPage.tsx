import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { listDrafts } from "@/api/drafts";
import { listProjects } from "@/api/projects";
import { DraftCard } from "@/components/drafts/DraftCard";
import { UploadWifModal } from "@/components/drafts/UploadWifModal";
import { Button } from "@/components/ui/button";
import { AppIcons } from "@/lib/icons";
import { Skeleton } from "@/components/ui/skeleton";

export function DraftsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [showUpload, setShowUpload] = useState(false);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const [activeTagFilter, setActiveTagFilter] = useState<string | null>(null);

  const { data: drafts = [], isLoading, error } = useQuery({
    queryKey: ["drafts", { includeArchived: true }],
    queryFn: () => listDrafts(true),
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const projectCountsByDraft = projects.reduce<Record<string, { active: number; planning: number; completed: number; abandoned: number }>>(
    (acc, a) => {
      const did = a.draft_id;
      if (!acc[did]) acc[did] = { active: 0, planning: 0, completed: 0, abandoned: 0 };
      if (a.status === "active" && !!a.loom_id) acc[did].active++;
      else if (a.status === "active" && !a.loom_id) acc[did].planning++;
      else if (a.status === "completed") acc[did].completed++;
      else if (a.status === "abandoned") acc[did].abandoned++;
      return acc;
    },
    {},
  );

  const allTags = useMemo(() => {
    const set = new Set<string>();
    drafts.forEach((d) => d.tags?.forEach((t) => set.add(t)));
    return [...set].sort();
  }, [drafts]);

  const handleUploadSuccess = () => {
    setShowUpload(false);
    queryClient.invalidateQueries({ queryKey: ["drafts"] });
  };

  const filteredDrafts = activeTagFilter
    ? drafts.filter((d) => d.tags?.includes(activeTagFilter))
    : drafts;

  const activeDrafts = filteredDrafts.filter((d) => !d.archived_at);
  const archivedDrafts = filteredDrafts.filter((d) => d.archived_at);

  return (
    <div className="p-6 max-w-4xl mx-auto w-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">{t("draftsPage.title")}</h1>
        <Button onClick={() => setShowUpload(true)}>{t("draftsPage.newButton")}</Button>
      </div>

      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-5">
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setActiveTagFilter(activeTagFilter === tag ? null : tag)}
              className={`rounded-full px-2.5 py-0.5 text-xs transition-colors ${
                activeTagFilter === tag
                  ? "bg-accent text-accent-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent/20"
              }`}
            >
              {tag}
            </button>
          ))}
          {activeTagFilter && (
            <button
              onClick={() => setActiveTagFilter(null)}
              className="rounded-full px-2 py-0.5 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
            >
              <AppIcons.close className="h-3 w-3" /> {t("draftsPage.clearFilter")}
            </button>
          )}
        </div>
      )}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[130px] rounded-lg" />)}
        </div>
      )}
      {error && <p className="text-sm text-destructive">{t("draftsPage.loadError")}</p>}

      {!isLoading && activeDrafts.length === 0 && archivedDrafts.length === 0 && !activeTagFilter && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">{t("draftsPage.emptyState")}</p>
          <Button className="mt-4" onClick={() => setShowUpload(true)}>
            {t("draftsPage.newButton")}
          </Button>
        </div>
      )}

      {!isLoading && activeDrafts.length === 0 && archivedDrafts.length === 0 && activeTagFilter && (
        <p className="text-sm text-muted-foreground">{t("draftsPage.noTagMatch", { tag: activeTagFilter })}</p>
      )}

      {activeDrafts.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2">
          {activeDrafts.map((d) => (
            <DraftCard key={d.id} draft={d} projectCounts={projectCountsByDraft[d.id]} />
          ))}
        </div>
      )}

      {archivedDrafts.length > 0 && (
        <div className="mt-8">
          <button
            type="button"
            onClick={() => setArchivedOpen((v) => !v)}
            className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors w-full text-left"
          >
            <AppIcons.chevronDown
              className={`h-4 w-4 transition-transform duration-200 ${archivedOpen ? "rotate-180" : ""}`}
            />
            {t("draftsPage.archived", { count: archivedDrafts.length })}
          </button>
          {archivedOpen && (
            <div className="mt-3 grid gap-4 sm:grid-cols-2 opacity-60">
              {archivedDrafts.map((d) => (
                <DraftCard key={d.id} draft={d} projectCounts={projectCountsByDraft[d.id]} archived />
              ))}
            </div>
          )}
        </div>
      )}

      {showUpload && (
        <UploadWifModal
          onSuccess={handleUploadSuccess}
          onClose={() => setShowUpload(false)}
        />
      )}
    </div>
  );
}
