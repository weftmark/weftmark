import { useMemo } from "react";

const STORAGE_KEY_PREFIX = "weftmark_tracker_session:";

// crypto.randomUUID() requires a secure context (HTTPS or localhost) and throws
// otherwise — fall back to crypto.getRandomValues(), which (unlike randomUUID)
// works in insecure contexts too, so a LAN hostname during local dev still gets
// an unpredictable id instead of crashing the whole page on render.
function generateTrackerToken(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return `${Date.now().toString(36)}-${Array.from(bytes, (b) => b.toString(36)).join("")}`;
  }
  return Date.now().toString(36);
}

// Per-tab, per-project identity for the tracker lock (#1029). sessionStorage (not
// localStorage) is required — each browser tab must be a distinct "device" so an
// idle tab left open elsewhere doesn't share identity with the tab actively in use.
export function useTrackerSession(projectId: string | undefined): string | null {
  return useMemo(() => {
    if (!projectId) return null;
    const key = `${STORAGE_KEY_PREFIX}${projectId}`;
    let token = sessionStorage.getItem(key);
    if (!token) {
      token = generateTrackerToken();
      sessionStorage.setItem(key, token);
    }
    return token;
  }, [projectId]);
}
