import { useNavigate } from "react-router-dom";
import type { Project } from "@/api/projects";
import { AppIcons } from "@/lib/icons";

interface ActivityCounts {
  active: number;
  planning: number;
  completed: number;
  abandoned: number;
}

interface Props {
  project: Project;
  activityCounts?: ActivityCounts;
}

export function ProjectCard({ project, activityCounts }: Props) {
  const navigate = useNavigate();

  const featureBadges = [
    project.has_threading && "Threading",
    project.has_tieup && "Tie-up",
  ].filter(Boolean) as string[];

  return (
    <button
      className="text-left w-full rounded-lg border bg-background p-4 shadow-sm hover:border-ring transition-colors"
      onClick={() => navigate(`/projects/${project.id}`)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-medium">{project.name}</h3>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{project.wif_filename}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {project.has_liftplan && (
            <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
          )}
          {project.has_treadling && (
            <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
          )}
          {project.lint_errors.length > 0 && (
            <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive">
              {project.lint_errors.length} error{project.lint_errors.length > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {project.num_shafts != null && (
        <p className="mt-2 text-xs text-muted-foreground">
          {project.num_shafts} shafts · {project.num_treadles} treadles ·{" "}
          {project.warp_threads} warp · {project.weft_threads} weft
        </p>
      )}

      {(project.has_liftplan || project.has_treadling) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {project.has_liftplan && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs">lift tracking</span>
          )}
          {project.has_treadling && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs">treadle tracking</span>
          )}
        </div>
      )}

      {featureBadges.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {featureBadges.map((b) => (
            <span
              key={b}
              className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
            >
              {b}
            </span>
          ))}
        </div>
      )}

      {project.lint_warnings.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {project.lint_warnings.length} warning{project.lint_warnings.length > 1 ? "s" : ""}
        </p>
      )}

      {activityCounts && (activityCounts.active + activityCounts.planning + activityCounts.completed + activityCounts.abandoned) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t pt-2.5">
          {activityCounts.active > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
              {activityCounts.active} active
            </span>
          )}
          {activityCounts.planning > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
              {activityCounts.planning} plan
            </span>
          )}
          {activityCounts.completed > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {activityCounts.completed} completed
            </span>
          )}
          {activityCounts.abandoned > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {activityCounts.abandoned} abandoned
            </span>
          )}
        </div>
      )}
    </button>
  );
}
