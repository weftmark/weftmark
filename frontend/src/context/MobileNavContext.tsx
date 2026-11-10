import { createContext, useContext } from "react";

interface MobileNavState {
  readonly openSidebar: () => void;
  readonly openFeedback: () => void;
}

export const MobileNavContext = createContext<MobileNavState | null>(null);

// AppLayout owns the mobile hamburger/sidebar and feedback-modal state. Pages
// that render their own compact mobile header (e.g. tracking mode, #1168)
// use this to trigger them without prop-drilling through the route tree.
export function useMobileNav(): MobileNavState {
  const ctx = useContext(MobileNavContext);
  if (!ctx) throw new Error("useMobileNav must be used inside AppLayout");
  return ctx;
}
