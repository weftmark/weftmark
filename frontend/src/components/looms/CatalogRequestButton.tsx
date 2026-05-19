import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { AppIcons } from "@/lib/icons";
import { type LoomDetail, LOOM_TYPE_LABELS } from "@/api/looms";
import { submitFeedback } from "@/api/feedback";

// ---------- localStorage dedup ----------

const SUBMITTED_KEY = "wm:catalog_submitted";

function isSubmitted(loomId: string): boolean {
  try {
    const raw = localStorage.getItem(SUBMITTED_KEY);
    return raw ? (JSON.parse(raw) as string[]).includes(loomId) : false;
  } catch {
    return false;
  }
}

function markSubmitted(loomId: string): void {
  try {
    const raw = localStorage.getItem(SUBMITTED_KEY);
    const arr: string[] = raw ? JSON.parse(raw) : [];
    if (!arr.includes(loomId)) {
      arr.push(loomId);
      localStorage.setItem(SUBMITTED_KEY, JSON.stringify(arr));
    }
  } catch {
    // ignore storage errors
  }
}

// ---------- component ----------

interface Props {
  loom: LoomDetail;
}

export function CatalogRequestButton({ loom }: Props) {
  const [showModal, setShowModal] = useState(false);
  const [done, setDone] = useState(() => isSubmitted(loom.id));

  const mutation = useMutation({
    mutationFn: submitFeedback,
    onSuccess: () => {
      markSubmitted(loom.id);
      setDone(true);
      setShowModal(false);
    },
  });

  function handleSubmit() {
    const typeLabel = LOOM_TYPE_LABELS[loom.loom_type] ?? loom.loom_type;
    mutation.mutate({
      submission_type: "feature_request",
      subject: `Loom catalog request: ${loom.manufacturer} ${loom.model_name}`,
      body: [
        "## Loom catalog request",
        "",
        `**Brand:** ${loom.manufacturer}`,
        `**Model:** ${loom.model_name}`,
        `**Type:** ${typeLabel}`,
        `**Loom ID (admin):** ${loom.id}`,
        "",
        "Please add this loom to the weftmark catalog so other users can find and link it.",
      ].join("\n"),
      is_anonymous: false,
      diagnostics: {
        environment:
          window.location.hostname === "weftmark.com" ||
          window.location.hostname.endsWith(".weftmark.com")
            ? `https://${window.location.hostname}`
            : "local instance",
        page_url: window.location.pathname,
        user_agent: navigator.userAgent,
        app_version: null,
      },
    });
  }

  if (done) {
    return (
      <span className="text-xs text-muted-foreground italic">Request submitted</span>
    );
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="text-xs h-7"
        onClick={() => setShowModal(true)}
      >
        Request catalog addition
      </Button>

      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => { if (!mutation.isPending) setShowModal(false); }}
        >
          <div
            className="w-full max-w-md rounded-lg border border-border bg-background shadow-xl p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Request catalog addition</h2>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                disabled={mutation.isPending}
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                aria-label="Close"
              >
                <AppIcons.close className="h-4 w-4" />
              </button>
            </div>

            <p className="text-sm text-muted-foreground">
              Submit a request to add this loom to the weftmark catalog. Once added, all
              users can link their loom to it and see manufacturer specs.
            </p>

            <div className="rounded-md border border-border bg-muted/30 px-4 py-3 space-y-1.5 text-sm">
              <div className="flex gap-3">
                <span className="text-muted-foreground w-14 shrink-0">Brand</span>
                <span className="font-medium">{loom.manufacturer}</span>
              </div>
              <div className="flex gap-3">
                <span className="text-muted-foreground w-14 shrink-0">Model</span>
                <span className="font-medium">{loom.model_name}</span>
              </div>
              <div className="flex gap-3">
                <span className="text-muted-foreground w-14 shrink-0">Type</span>
                <span className="font-medium">
                  {LOOM_TYPE_LABELS[loom.loom_type] ?? loom.loom_type}
                </span>
              </div>
            </div>

            {mutation.isError && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                Failed to submit. Please try again.
              </p>
            )}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowModal(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handleSubmit}
                disabled={mutation.isPending}
              >
                {mutation.isPending ? "Submitting…" : "Submit Request"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
