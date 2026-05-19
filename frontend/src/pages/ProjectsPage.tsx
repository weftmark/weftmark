import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listProjects, projectDrawdownPreviewUrl, PROJECT_TYPE_LABELS, PROJECT_STATUS_LABELS, type ProjectSummary } from "@/api/projects";
import { AppIcons } from "@/lib/icons";
import { previewUrl } from "@/api/drafts";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { CreateProjectModal } from "@/components/projects/CreateProjectModal";
import { AssignLoomModal } from "@/components/projects/AssignLoomModal";
import { Button } from "@/components/ui/button";
import { TagChips } from "@/components/ui/TagChips";
import { Link } from "react-router-dom";

const STATUS_COLORS: Record<string, string> = {
  created: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  plan: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  completed: "bg-muted text-muted-foreground",
  abandoned: "bg-muted text-muted-foreground",
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function groupByYear(
  items: ProjectSummary[],
  getDate: (p: ProjectSummary) => string | null,
): Array<{ year: number; items: ProjectSummary[] }> {
  const map = new Map<number, ProjectSummary[]>();
  for (const item of items) {
    const d = getDate(item);
    const year = d ? new Date(d).getFullYear() : new Date().getFullYear();
    if (!map.has(year)) map.set(year, []);
    map.get(year)!.push(item);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b - a)
    .map(([year, items]) => ({ year, items }));
}

function ProjectCard({ project, onAssign }: {
  project: ProjectSummary;
  onAssign?: (id: string) => void;
}) {
  const [showPreview, setShowPreview] = useState(false);
  const isPlanning = (project.status === "active" || project.status === "created") && !project.loom_id;
  const badgeKey = isPlanning ? "plan" : project.status;
  const badgeLabel = isPlanning ? "Plan" : PROJECT_STATUS_LABELS[project.status];

  const endDate = project.status === "completed"
    ? project.completed_at
    : project.status === "abandoned"
      ? project.abandoned_at
      : null;

  const pct = project.total_picks > 0
    ? Math.round((Math.min(project.current_pick - 1, project.total_picks) / project.total_picks) * 100)
    : 0;

  return (
    <div className="relative rounded-lg border hover:border-ring transition-colors overflow-hidden">
      {project.has_drawdown_preview && (
        <div className="w-full h-20 bg-muted overflow-hidden">
          <AuthedImage
            src={projectDrawdownPreviewUrl(project.id)}
            alt=""
            className="w-full h-full object-cover object-top"
            style={{ imageRendering: "pixelated" }}
          />
        </div>
      )}
      <Link to={`/projects/${project.id}`} className="block p-4">
        <div className="flex gap-3">
          <div className="shrink-0 mt-0.5">
            {isPlanning
              ? <AppIcons.planning className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
              : project.project_type === "treadle"
                ? <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
                : <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <span className="font-medium">{project.name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  type="button"
                  aria-label="Preview drawdown"
                  onClick={(e) => { e.preventDefault(); setShowPreview(true); }}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                  title="Preview drawdown"
                >
                  <svg width="13" height="13" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
                    <rect x="0" y="0" width="5" height="5" rx="1" />
                    <rect x="7" y="0" width="5" height="5" rx="1" />
                    <rect x="0" y="7" width="5" height="5" rx="1" />
                    <rect x="7" y="7" width="5" height="5" rx="1" />
                  </svg>
                </button>
                <span className={`min-w-[5.5rem] text-center rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[badgeKey]}`}>
                  {badgeLabel}
                </span>
              </div>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">{PROJECT_TYPE_LABELS[project.project_type]}</p>
            {endDate && (
              <p className="mt-0.5 text-xs text-muted-foreground">{fmtDate(endDate)}</p>
            )}
            {project.tags && project.tags.length > 0 && (
              <TagChips tags={project.tags} className="mt-1.5" />
            )}
            {!isPlanning && project.status === "active" && (
              <div className="mt-3">
                <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                  <span>Pick {Math.min(project.current_pick, project.total_picks)} of {project.total_picks}</span>
                  <span>{pct}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                  <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )}
          </div>
        </div>
      </Link>
      {isPlanning && onAssign && (
        <div className="border-t px-3 pb-3 pt-2">
          <button
            type="button"
            onClick={() => onAssign(project.id)}
            className="w-full rounded-md border border-dashed border-input px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-ring hover:bg-muted hover:text-foreground"
          >
            Assign to loom…
          </button>
        </div>
      )}
      {project.status === "active" && project.loom_id && (
        <div className="border-t px-3 pb-3 pt-2">
          <Link
            to={`/projects/${project.id}/track`}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-input px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
          >
            <AppIcons.projectActive className="h-3.5 w-3.5" />
            Continue Weaving
          </Link>
        </div>
      )}
      {showPreview && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowPreview(false)}
        >
          <div className="relative max-w-xl w-full" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setShowPreview(false)}
              className="absolute -top-9 right-0 text-white/70 hover:text-white text-sm"
            >
              Close ✕
            </button>
            <p className="absolute -top-9 left-0 text-white/70 text-sm truncate max-w-xs">{project.name}</p>
            <AuthedImage
              src={project.has_drawdown_preview ? projectDrawdownPreviewUrl(project.id) : previewUrl(project.draft_id)}
              alt="Design preview"
              className="w-full rounded-lg shadow-2xl"
              style={{ imageRendering: "pixelated" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function YearGroup({
  year,
  items,
  defaultExpanded,
  onAssign,
}: {
  year: number;
  items: ProjectSummary[];
  defaultExpanded: boolean;
  onAssign?: (id: string) => void;
}) {
  const [open, setOpen] = useState(defaultExpanded);
  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-2 mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{year} ({items.length})</span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map((p) => <ProjectCard key={p.id} project={p} onAssign={onAssign} />)}
        </div>
      )}
    </div>
  );
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [assigningProjectId, setAssigningProjectId] = useState<string | null>(null);
  const [activeTagFilter, setActiveTagFilter] = useState<string | null>(null);

  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(),
  });

  const allTags = useMemo(() => {
    const set = new Set<string>();
    projects.forEach((p) => p.tags?.forEach((t) => set.add(t)));
    return [...set].sort();
  }, [projects]);

  const filteredProjects = activeTagFilter
    ? projects.filter((p) => p.tags?.includes(activeTagFilter))
    : projects;

  const currentYear = new Date().getFullYear();

  const planning = filteredProjects.filter((p) => (p.status === "active" || p.status === "created") && !p.loom_id);
  const notStarted = filteredProjects.filter((p) => p.status === "created" && !!p.loom_id);
  const active = filteredProjects.filter((p) => p.status === "active" && !!p.loom_id);

  const completed = filteredProjects
    .filter((p) => p.status === "completed")
    .sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? ""));

  const abandoned = filteredProjects
    .filter((p) => p.status === "abandoned")
    .sort((a, b) => (b.abandoned_at ?? "").localeCompare(a.abandoned_at ?? ""));

  const completedByYear = groupByYear(completed, (p) => p.completed_at);
  const abandonedByYear = groupByYear(abandoned, (p) => p.abandoned_at);

  return (
    <div className="p-6 max-w-3xl mx-auto w-full space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
        <Button size="sm" onClick={() => setShowCreate(true)}>New project</Button>
      </div>

      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
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
              <AppIcons.close className="h-3 w-3" /> Clear
            </button>
          )}
        </div>
      )}

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {error && <p className="text-sm text-destructive">Failed to load projects.</p>}

      {!isLoading && projects.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">No projects yet. Start one to begin tracking a weaving session.</p>
          <Button className="mt-4" onClick={() => setShowCreate(true)}>New project</Button>
        </div>
      )}

      {active.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Active</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {active.map((p) => <ProjectCard key={p.id} project={p} />)}
          </div>
        </section>
      )}

      {notStarted.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Not started</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {notStarted.map((p) => <ProjectCard key={p.id} project={p} />)}
          </div>
        </section>
      )}

      {planning.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Planning</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {planning.map((p) => <ProjectCard key={p.id} project={p} onAssign={setAssigningProjectId} />)}
          </div>
        </section>
      )}

      {completedByYear.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Completed</h2>
          <div className="space-y-4">
            {completedByYear.map(({ year, items }) => (
              <YearGroup
                key={year}
                year={year}
                items={items}
                defaultExpanded={year === currentYear}
              />
            ))}
          </div>
        </section>
      )}

      {abandonedByYear.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground uppercase tracking-wide">Abandoned</h2>
          <div className="space-y-4">
            {abandonedByYear.map(({ year, items }) => (
              <YearGroup
                key={year}
                year={year}
                items={items}
                defaultExpanded={false}
              />
            ))}
          </div>
        </section>
      )}

      {showCreate && (
        <CreateProjectModal
          onSuccess={(id) => { queryClient.invalidateQueries({ queryKey: ["projects"] }); navigate(`/projects/${id}`); }}
          onClose={() => setShowCreate(false)}
        />
      )}

      {assigningProjectId && (
        <AssignLoomModal
          projectId={assigningProjectId}
          activeProjects={projects.filter((p) => p.status === "active")}
          onSuccess={() => { setAssigningProjectId(null); queryClient.invalidateQueries({ queryKey: ["projects"] }); }}
          onClose={() => setAssigningProjectId(null)}
        />
      )}
    </div>
  );
}
