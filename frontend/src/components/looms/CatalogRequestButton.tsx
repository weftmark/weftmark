import { useState, useEffect } from "react";
import { type LoomDetail, LOOM_TYPE_LABELS } from "@/api/looms";

// ---------- types ----------

interface GithubIssue {
  number: number;
  title: string;
  url: string;
}

interface CheckCache {
  token: string;
  issues: GithubIssue[];
  checkedAt: number;
}

type CheckState = "checking" | "no_dupes" | "dupes_found" | "failed" | "submitted";

// ---------- constants ----------

const CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const CACHE_PREFIX = "wm:catalog_check:";
const SUBMITTED_KEY = "wm:catalog_submitted";

// ---------- dedup token ----------
// djb2 hash of "manufacturer:model" (lowercased). Deterministic, collision-
// resistant enough for dedup. Louet Spring and Louet Spring II produce
// completely different tokens so there are no prefix-match false positives.

function requestToken(manufacturer: string, model: string): string {
  const str = `${manufacturer.toLowerCase()}:${model.toLowerCase()}`;
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) ^ str.charCodeAt(i);
  }
  return `wmloom${(h >>> 0).toString(36)}`;
}

// ---------- localStorage helpers ----------

function getCached(loomId: string, token: string): CheckCache | null {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + loomId);
    if (!raw) return null;
    const c: CheckCache = JSON.parse(raw);
    if (c.token !== token) return null; // loom renamed — invalidate
    if (Date.now() - c.checkedAt > CACHE_TTL_MS) return null;
    return c;
  } catch {
    return null;
  }
}

function setCached(loomId: string, cache: CheckCache): void {
  try {
    localStorage.setItem(CACHE_PREFIX + loomId, JSON.stringify(cache));
  } catch {
    // ignore storage errors
  }
}

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

// ---------- GitHub API ----------

async function fetchGithubIssues(token: string): Promise<GithubIssue[]> {
  // Search for the exact token in issue bodies.
  // "wm-req:abc123" is a unique string per manufacturer:model hash so there
  // are no partial-match false positives (Spring ≠ Spring II).
  const q = encodeURIComponent(
    `repo:weftmark/weftmark "wm-req:${token}" is:issue is:open`,
  );
  const res = await fetch(
    `https://api.github.com/search/issues?q=${q}&per_page=5`,
    { headers: { Accept: "application/vnd.github+json" } },
  );
  if (!res.ok) throw new Error(`GitHub ${res.status}`);
  const data = await res.json();
  return (data.items ?? []).map(
    (item: { number: number; title: string; html_url: string }) => ({
      number: item.number,
      title: item.title,
      url: item.html_url,
    }),
  );
}

// ---------- URL builder ----------

function buildIssueUrl(
  loom: LoomDetail,
  token: string,
  existingIssues: GithubIssue[],
): string {
  const title = encodeURIComponent(
    `Loom catalog request: ${loom.manufacturer} ${loom.model_name}`,
  );

  const relatedSection =
    existingIssues.length > 0
      ? `\n**Related existing requests:**\n${existingIssues
          .map((i) => `- #${i.number} — ${i.url}`)
          .join("\n")}\n`
      : "";

  const body = encodeURIComponent(
    `## Loom catalog request\n\n` +
      `**Brand:** ${loom.manufacturer}\n` +
      `**Model:** ${loom.model_name}\n` +
      `**Type:** ${LOOM_TYPE_LABELS[loom.loom_type] ?? loom.loom_type}\n` +
      `**Loom ID (admin):** ${loom.id}\n` +
      `${relatedSection}\n` +
      `Please add this loom to the weftmark catalog so other users can find and link it.\n\n` +
      `---\n` +
      `wm-req:${token}`,
  );

  return `https://github.com/weftmark/weftmark/issues/new?title=${title}&body=${body}`;
}

// ---------- component ----------

interface Props {
  loom: LoomDetail;
}

export function CatalogRequestButton({ loom }: Props) {
  const token = requestToken(loom.manufacturer, loom.model_name);

  // Initialise synchronously from localStorage to avoid a "checking" flash
  // when we already have a cached result or a prior submission.
  const [state, setState] = useState<CheckState>(() => {
    if (isSubmitted(loom.id)) return "submitted";
    const cached = getCached(loom.id, token);
    if (cached) return cached.issues.length > 0 ? "dupes_found" : "no_dupes";
    return "checking";
  });

  const [issues, setIssues] = useState<GithubIssue[]>(() => {
    const cached = getCached(loom.id, token);
    return cached?.issues ?? [];
  });

  const [showSubmitAnyway, setShowSubmitAnyway] = useState(false);

  // Fetch from GitHub only when there's no cached result.
  // `state` is intentionally excluded from deps — we only want one fetch per
  // mount and the initial value is already correctly derived above.
  useEffect(() => {
    if (state !== "checking") return;
    let cancelled = false;

    fetchGithubIssues(token)
      .then((found) => {
        if (cancelled) return;
        setIssues(found);
        setCached(loom.id, { token, issues: found, checkedAt: Date.now() });
        setState(found.length > 0 ? "dupes_found" : "no_dupes");
      })
      .catch(() => {
        if (cancelled) return;
        setState("failed");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loom.id, token]);

  function handleSubmit(withExisting: GithubIssue[]) {
    window.open(buildIssueUrl(loom, token, withExisting), "_blank", "noopener");
    markSubmitted(loom.id);
    setState("submitted");
  }

  // ── submitted ──
  if (state === "submitted") {
    return (
      <span className="text-xs text-muted-foreground italic">Request submitted</span>
    );
  }

  // ── checking ──
  if (state === "checking") {
    return (
      <span className="text-xs text-muted-foreground italic">
        Checking for existing requests…
      </span>
    );
  }

  // ── no dupes / failed (treat API failure as no dupes — don't block submission) ──
  if (state === "no_dupes" || state === "failed") {
    return (
      <a
        href={buildIssueUrl(loom, token, [])}
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => handleSubmit([])}
        className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
      >
        Submit request to add to catalog
      </a>
    );
  }

  // ── dupes found ──
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">
        Similar requests already open:
      </p>
      <ul className="space-y-0.5 pl-1">
        {issues.map((issue) => (
          <li key={issue.number}>
            <a
              href={issue.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
            >
              #{issue.number} — {issue.title}
            </a>
          </li>
        ))}
      </ul>
      {!showSubmitAnyway ? (
        <button
          type="button"
          onClick={() => setShowSubmitAnyway(true)}
          className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
        >
          Submit a new request anyway
        </button>
      ) : (
        <div className="rounded-md border border-border bg-muted/20 px-3 py-2 space-y-1.5">
          <p className="text-xs text-muted-foreground">
            Links to the existing requests above will be included in your submission.
          </p>
          <div className="flex items-center gap-3">
            <a
              href={buildIssueUrl(loom, token, issues)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => handleSubmit(issues)}
              className="text-xs font-medium text-foreground hover:underline"
            >
              Submit with references →
            </a>
            <button
              type="button"
              onClick={() => setShowSubmitAnyway(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
