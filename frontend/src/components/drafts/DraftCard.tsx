import { useNavigate } from "react-router-dom";
import type { Draft } from "@/api/drafts";
import { drawdownPreviewUrl } from "@/api/drafts";
import { AuthedImage } from "@/components/ui/AuthedImage";
import { AppIcons } from "@/lib/icons";

interface ProjectCounts {
  active: number;
  planning: number;
  completed: number;
  abandoned: number;
}

interface Props {
  draft: Draft;
  projectCounts?: ProjectCounts;
}

export function DraftCard({ draft, projectCounts }: Props) {
  const navigate = useNavigate();

  const featureBadges = [
    draft.has_threading && "Threading",
    draft.has_tieup && "Tie-up",
  ].filter(Boolean) as string[];

  return (
    <button
      data-testid="draft-card"
      className="text-left w-full rounded-lg border bg-background shadow-sm hover:border-ring transition-colors overflow-hidden"
      onClick={() => navigate(`/drafts/${draft.id}`)}
    >
      {draft.has_drawdown_preview && (
        <div className="w-full h-20 bg-muted overflow-hidden">
          <AuthedImage
            src={drawdownPreviewUrl(draft.id)}
            alt=""
            className="w-full h-full object-cover object-top"
          />
        </div>
      )}
      <div className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate font-medium">{draft.name}</h3>
          <p className="text-xs text-muted-foreground mt-0.5 truncate">{draft.wif_filename}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {draft.has_liftplan && (
            <AppIcons.lift className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
          )}
          {draft.has_treadling && (
            <AppIcons.treadle className="h-6 w-6 text-muted-foreground" strokeWidth={1.75} />
          )}
          {draft.lint_errors.length > 0 && (
            <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-xs text-destructive">
              {draft.lint_errors.length} error{draft.lint_errors.length > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {draft.num_shafts != null && (
        <p className="mt-2 text-xs text-muted-foreground">
          {draft.num_shafts} shafts · {draft.num_treadles} treadles ·{" "}
          {draft.warp_threads} warp · {draft.weft_threads} weft
        </p>
      )}

      {(draft.has_liftplan || draft.has_treadling) && (
        <div className="mt-2 flex flex-wrap gap-2">
          {draft.has_liftplan && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs">lift tracking</span>
          )}
          {draft.has_treadling && (
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

      {draft.lint_warnings.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">
          {draft.lint_warnings.length} warning{draft.lint_warnings.length > 1 ? "s" : ""}
        </p>
      )}

      {projectCounts && (projectCounts.active + projectCounts.planning + projectCounts.completed + projectCounts.abandoned) > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 border-t pt-2.5">
          {projectCounts.active > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
              {projectCounts.active} active
            </span>
          )}
          {projectCounts.planning > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
              {projectCounts.planning} plan
            </span>
          )}
          {projectCounts.completed > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {projectCounts.completed} completed
            </span>
          )}
          {projectCounts.abandoned > 0 && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
              {projectCounts.abandoned} abandoned
            </span>
          )}
        </div>
      )}
      </div>
    </button>
  );
}
