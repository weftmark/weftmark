import { useEffect } from "react";

/**
 * Closes on Escape via a document-level listener, so it fires regardless of
 * which element currently has focus (e.g. while typing in a field inside the
 * dialog) — unlike a keydown handler on the backdrop, which only fires if the
 * backdrop itself happens to be focused.
 */
export function useEscapeKey(onEscape: () => void, enabled: boolean = true): void {
  useEffect(() => {
    if (!enabled) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onEscape();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onEscape, enabled]);
}
