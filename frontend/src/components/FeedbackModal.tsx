import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { AppIcons } from "@/lib/icons";
import { useAuth } from "@/hooks/useAuth";
import {
  submitFeedback,
  getFeedbackStatus,
  SUBMISSION_TYPE_LABELS,
  type SubmissionType,
  type FeedbackRecord,
} from "@/api/feedback";

interface Props {
  onClose: () => void;
}

const TYPE_PLACEHOLDERS: Record<SubmissionType, string> = {
  feedback: "Share your thoughts, impressions, or anything you'd like us to know about your experience.",
  feature_request: "Describe the feature you'd like and how it would help your workflow.",
  bug_report:
    "Describe the issue: what happened, what you expected, and how to reproduce it. " +
    "Include browser and device info if relevant.",
};

function getEnvironment(hostname: string): string {
  if (hostname.endsWith(".weftmark.com")) return `https://${hostname}`;
  return "local instance";
}

async function getAppVersion(): Promise<string | null> {
  try {
    const res = await fetch("/version.json");
    if (!res.ok) return null;
    const data = await res.json();
    return data.version ?? null;
  } catch {
    return null;
  }
}

function extractProjectId(pathname: string): string | null {
  const m = pathname.match(/^\/projects\/([0-9a-f-]{36})/i);
  return m ? m[1] : null;
}

function extractDraftId(pathname: string): string | null {
  const m = pathname.match(/^\/drafts\/([0-9a-f-]{36})/i);
  return m ? m[1] : null;
}

export function FeedbackModal({ onClose }: Props) {
  const { user } = useAuth();
  const location = useLocation();

  const [type, setType] = useState<SubmissionType>("feedback");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [isAnonymous, setIsAnonymous] = useState(false);
  const [includeIds, setIncludeIds] = useState(true);
  const [submitted, setSubmitted] = useState<FeedbackRecord | null>(null);
  const [appVersion, setAppVersion] = useState<string | null>(null);

  const detectedProjectId = extractProjectId(location.pathname);
  const detectedDraftId = extractDraftId(location.pathname);

  useEffect(() => {
    getAppVersion().then(setAppVersion);
  }, []);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const mutation = useMutation({
    mutationFn: submitFeedback,
    onSuccess: (data) => setSubmitted(data),
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;

    const env = getEnvironment(window.location.hostname);

    mutation.mutate({
      submission_type: type,
      subject: subject.trim() || null,
      body: body.trim(),
      is_anonymous: user ? isAnonymous : false,
      diagnostics: {
        environment: env,
        page_url: location.pathname,
        user_agent: navigator.userAgent,
        app_version: appVersion,
        project_id: includeIds && !isAnonymous ? detectedProjectId : null,
        draft_id: includeIds && !isAnonymous ? detectedDraftId : null,
      },
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-lg border border-border bg-background shadow-xl p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold flex items-center gap-2">
            <AppIcons.feedback className="h-4 w-4 text-muted-foreground" />
            Send Feedback
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <AppIcons.close className="h-4 w-4" />
          </button>
        </div>

        {submitted ? (
          <SuccessView record={submitted} onClose={onClose} />
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Type selector */}
            <div>
              <label className="mb-1.5 block text-sm font-medium">Type</label>
              <div className="flex gap-2 flex-wrap">
                {(Object.keys(SUBMISSION_TYPE_LABELS) as SubmissionType[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setType(t)}
                    className={`rounded-full px-3 py-1 text-sm font-medium border transition-colors ${
                      type === t
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:border-foreground hover:text-foreground"
                    }`}
                  >
                    {SUBMISSION_TYPE_LABELS[t]}
                  </button>
                ))}
              </div>
            </div>

            {/* Subject */}
            <div>
              <label className="mb-1 block text-sm font-medium">
                Subject <span className="text-muted-foreground font-normal">(optional)</span>
              </label>
              <input
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                placeholder="Brief summary"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                maxLength={200}
              />
            </div>

            {/* Body */}
            <div>
              <label className="mb-1 block text-sm font-medium">
                Details <span className="text-destructive">*</span>
              </label>
              <textarea
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring resize-none"
                rows={5}
                placeholder={TYPE_PLACEHOLDERS[type]}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                required
              />
            </div>

            {/* Anonymous toggle — logged-in users only */}
            {user && (
              <div className="space-y-2">
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={isAnonymous}
                    onChange={(e) => setIsAnonymous(e.target.checked)}
                    className="rounded"
                  />
                  <span className="text-sm">Submit anonymously</span>
                </label>
                <p className="text-xs text-muted-foreground pl-6">
                  {isAnonymous
                    ? "Page URL and project/draft IDs won't be included in the public Discussion. Admins can still see who submitted, and it will appear in your feedback history."
                    : "Page URL and project/draft IDs (if opted in below) will appear in the public Discussion."}
                </p>
              </div>
            )}

            {/* Include IDs — shown when not anonymous and IDs detected */}
            {user && !isAnonymous && (detectedProjectId || detectedDraftId) && (
              <label className="flex items-start gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={includeIds}
                  onChange={(e) => setIncludeIds(e.target.checked)}
                  className="rounded mt-0.5"
                />
                <span className="text-sm text-muted-foreground">
                  Include{" "}
                  {[
                    detectedProjectId && "project ID",
                    detectedDraftId && "draft ID",
                  ]
                    .filter(Boolean)
                    .join(" and ")}{" "}
                  to help with troubleshooting
                </span>
              </label>
            )}

            {/* Error */}
            {mutation.isError && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                Failed to submit. Please try again.
              </p>
            )}

            {/* Footer note */}
            <p className="text-xs text-muted-foreground">
              This is a hobby project — responses may be slow. After submitting, you'll
              receive a link to a GitHub Discussion thread where you can attach screenshots.
            </p>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={mutation.isPending || !body.trim()}>
                {mutation.isPending ? "Sending…" : "Send Feedback"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function SuccessView({ record, onClose }: { record: FeedbackRecord; onClose: () => void }) {
  const { user } = useAuth();

  const [pollDispatchStatus, setPollDispatchStatus] = useState<string>(record.dispatch_status);
  const [pollDiscussionUrl, setPollDiscussionUrl] = useState<string | null>(record.github_discussion_url);
  const [timedOut, setTimedOut] = useState(false);

  const canPoll = !!user && pollDispatchStatus === "pending";

  useEffect(() => {
    if (!canPoll) return;

    const TIMEOUT_MS = 30_000;
    const INTERVAL_MS = 2_500;
    const startTime = Date.now();

    const interval = setInterval(async () => {
      if (Date.now() - startTime >= TIMEOUT_MS) {
        clearInterval(interval);
        setTimedOut(true);
        return;
      }
      try {
        const s = await getFeedbackStatus(record.id);
        if (s.dispatch_status !== "pending") {
          clearInterval(interval);
          setPollDispatchStatus(s.dispatch_status);
          setPollDiscussionUrl(s.github_discussion_url);
        }
      } catch {
        // ignore transient poll errors
      }
    }, INTERVAL_MS);

    return () => clearInterval(interval);
  }, [canPoll, record.id]);

  const typeLabel = SUBMISSION_TYPE_LABELS[record.submission_type as SubmissionType] ?? "feedback";

  return (
    <div className="space-y-4">
      <p className="text-sm text-foreground">
        Thank you — your {typeLabel} was received.
      </p>

      {pollDispatchStatus === "pending" && !timedOut ? (
        <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
          <AppIcons.spinner className="h-4 w-4 animate-spin shrink-0" />
          <span>Creating your GitHub Discussion thread…</span>
        </div>
      ) : pollDispatchStatus === "sent" && pollDiscussionUrl ? (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            A discussion thread has been created. You can follow progress and attach screenshots there:
          </p>
          <a
            href={pollDiscussionUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
          >
            <AppIcons.externalLink className="h-3.5 w-3.5" />
            View on GitHub
          </a>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Your submission is stored and will be reviewed by the team.
          {(pollDispatchStatus === "skipped" || timedOut) &&
            " No public Discussion will be created, but the team will see your message."}
          {pollDispatchStatus === "failed" &&
            " The Discussion thread couldn't be created right now — the team will still see your submission."}
        </p>
      )}

      <p className="text-xs text-muted-foreground border-t border-border pt-3">
        weftmark is a hobby project, not a business. Response times may be slow or limited.
        We genuinely appreciate you taking the time to share your feedback.
      </p>

      <div className="flex justify-end">
        <Button onClick={onClose}>Close</Button>
      </div>
    </div>
  );
}
