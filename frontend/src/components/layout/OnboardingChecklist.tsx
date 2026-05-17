import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AppIcons } from "@/lib/icons";
import { useAuth } from "@/hooks/useAuth";
import { getOnboardingStatus, updateSettings } from "@/api/users";

const SESSION_SKIP_KEY = "onboarding_skipped";

interface Task {
  key: string;
  label: string;
  href: string;
}

const TASKS: Task[] = [
  { key: "eula_accepted", label: "Accept terms of service", href: "/settings/terms" },
  { key: "has_loom",      label: "Add a loom",             href: "/looms" },
  { key: "has_draft",     label: "Upload a draft",         href: "/drafts" },
  { key: "has_project",   label: "Create a project",       href: "/projects" },
];

export function OnboardingChecklist({ collapsed }: { collapsed?: boolean }) {
  const { user, refetch: refetchUser } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [sessionSkipped, setSessionSkipped] = useState(
    () => typeof sessionStorage !== "undefined" && !!sessionStorage.getItem(SESSION_SKIP_KEY)
  );

  const shouldShow = !!user && !user.onboarding_dismissed && !sessionSkipped && !user.is_superuser;

  const { data: status } = useQuery({
    queryKey: ["onboarding-status"],
    queryFn: getOnboardingStatus,
    enabled: shouldShow,
    staleTime: 60_000,
  });

  const dismissMutation = useMutation({
    mutationFn: () => updateSettings({ onboarding_dismissed: true }),
    onSuccess: () => {
      refetchUser();
      qc.invalidateQueries({ queryKey: ["onboarding-status"] });
    },
  });

  if (!shouldShow) return null;

  const checks = status
    ? {
        eula_accepted: status.eula_accepted,
        has_loom: status.has_loom,
        has_draft: status.has_draft,
        has_project: status.has_project,
      }
    : { eula_accepted: false, has_loom: false, has_draft: false, has_project: false };

  const doneCount = Object.values(checks).filter(Boolean).length;
  const allDone = doneCount === TASKS.length;

  function handleSkip() {
    sessionStorage.setItem(SESSION_SKIP_KEY, "1");
    setSessionSkipped(true);
    setOpen(false);
  }

  function handleDismiss() {
    dismissMutation.mutate();
  }

  if (collapsed) {
    // Rail mode: just a small clickable icon with a dot if incomplete
    return (
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-center w-full rounded-lg p-2 text-muted-foreground hover:bg-accent/50 hover:text-foreground relative"
        title="Getting started"
      >
        <AppIcons.onboarding className="h-4 w-4" strokeWidth={1.75} />
        {!allDone && (
          <span className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-primary" />
        )}
      </button>
    );
  }

  return (
    <div className="mx-3 mb-1 rounded-lg border border-border bg-card text-sm overflow-hidden">
      {/* Header row — always visible */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
      >
        <AppIcons.onboarding className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} />
        <span className="flex-1 text-xs font-medium text-foreground">Getting started</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {doneCount}/{TASKS.length}
        </span>
        <AppIcons.chevronDown
          className={`h-3 w-3 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {/* Expanded body */}
      {open && (
        <div className="border-t border-border px-3 py-2 space-y-1.5">
          {TASKS.map((task) => {
            const done = checks[task.key as keyof typeof checks];
            return (
              <div key={task.key} className="flex items-center gap-2">
                {done ? (
                  <AppIcons.projectCompleted className="h-3.5 w-3.5 shrink-0 text-green-600 dark:text-green-400" />
                ) : (
                  <span className="h-3.5 w-3.5 shrink-0 rounded-sm border border-border" />
                )}
                {done ? (
                  <span className="text-xs text-muted-foreground line-through">{task.label}</span>
                ) : (
                  <Link
                    to={task.href}
                    className="text-xs text-foreground hover:text-primary hover:underline"
                  >
                    {task.label}
                    <AppIcons.chevronRight className="inline h-3 w-3 ml-0.5 text-muted-foreground" />
                  </Link>
                )}
              </div>
            );
          })}

          <div className="flex gap-2 pt-1.5 border-t border-border">
            <button
              onClick={handleSkip}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Skip for now
            </button>
            <span className="text-muted-foreground/40">·</span>
            {allDone ? (
              <button
                onClick={handleDismiss}
                disabled={dismissMutation.isPending}
                className="text-xs font-medium text-primary hover:underline disabled:opacity-50"
              >
                {dismissMutation.isPending ? "Saving…" : "Complete ✓"}
              </button>
            ) : (
              <button
                onClick={handleDismiss}
                disabled={dismissMutation.isPending}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              >
                Never show again
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
