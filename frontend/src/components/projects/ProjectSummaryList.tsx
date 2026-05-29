import { useState } from "react";
import { Link } from "react-router-dom";
import { PROJECT_TYPE_LABELS, PROJECT_STATUS_LABELS, type ProjectSummary } from "@/api/projects";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  plan: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  completed: "bg-muted text-muted-foreground",
  abandoned: "bg-muted text-muted-foreground",
};

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function ProjectRow({ project }: { project: ProjectSummary }) {
  const isPlanning = project.status === "active" && !project.loom_id;
  const badgeKey = isPlanning ? "plan" : project.status;
  const badgeLabel = isPlanning ? "Plan" : PROJECT_STATUS_LABELS[project.status];
  const endDate = project.status === "completed"
    ? project.completed_at
    : project.status === "abandoned"
      ? project.abandoned_at
      : null;

  return (
    <Link
      to={`/projects/${project.id}`}
      className="flex items-center justify-between gap-3 rounded-md px-3 py-2 hover:bg-muted transition-colors"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{project.name}</p>
        <p className="text-xs text-muted-foreground">{project.project_type ? PROJECT_TYPE_LABELS[project.project_type] : ""}{endDate ? ` · ${fmtDate(endDate)}` : ""}</p>
      </div>
      <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_COLORS[badgeKey]}`}>
        {badgeLabel}
      </span>
    </Link>
  );
}

function YearGroup({ year, items, defaultOpen }: { year: number; items: ProjectSummary[]; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-foreground mb-1"
      >
        {year} ({items.length}) <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="space-y-0.5">
          {items.map((p) => <ProjectRow key={p.id} project={p} />)}
        </div>
      )}
    </div>
  );
}

function groupByYear(items: ProjectSummary[], getDate: (p: ProjectSummary) => string | null) {
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

export function ProjectSummaryList({ projects }: { projects: ProjectSummary[] }) {
  const currentYear = new Date().getFullYear();

  const active = projects.filter((p) => p.status === "active" && !!p.loom_id);
  const planning = projects.filter((p) => p.status === "active" && !p.loom_id);
  const completed = projects
    .filter((p) => p.status === "completed")
    .sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? ""));
  const abandoned = projects
    .filter((p) => p.status === "abandoned")
    .sort((a, b) => (b.abandoned_at ?? "").localeCompare(a.abandoned_at ?? ""));

  const completedByYear = groupByYear(completed, (p) => p.completed_at);
  const abandonedByYear = groupByYear(abandoned, (p) => p.abandoned_at);

  if (projects.length === 0) {
    return <p className="text-sm text-muted-foreground">No projects yet.</p>;
  }

  return (
    <div className="space-y-4">
      {active.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Active</p>
          <div className="space-y-0.5">
            {active.map((p) => <ProjectRow key={p.id} project={p} />)}
          </div>
        </div>
      )}
      {planning.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Planning</p>
          <div className="space-y-0.5">
            {planning.map((p) => <ProjectRow key={p.id} project={p} />)}
          </div>
        </div>
      )}
      {completedByYear.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Completed</p>
          <div className="space-y-2">
            {completedByYear.map(({ year, items }) => (
              <YearGroup key={year} year={year} items={items} defaultOpen={year === currentYear} />
            ))}
          </div>
        </div>
      )}
      {abandonedByYear.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Abandoned</p>
          <div className="space-y-2">
            {abandonedByYear.map(({ year, items }) => (
              <YearGroup key={year} year={year} items={items} defaultOpen={false} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
