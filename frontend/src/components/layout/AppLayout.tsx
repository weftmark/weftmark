import { useState } from "react";
import { useLocation } from "react-router-dom";
import { AppIcons } from "@/lib/icons";
import { Sidebar } from "@/components/layout/Sidebar";
import { VersionBadge } from "@/components/layout/VersionFooter";
import { FeedbackModal } from "@/components/FeedbackModal";
import { useAuth } from "@/hooks/useAuth";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ImpersonationBanner } from "@/components/layout/ImpersonationBanner";
import { MobileNavContext } from "@/context/MobileNavContext";
import type { ReactNode } from "react";

const DETAIL_PATTERN = /^\/projects\/[^/]+/;
// Tracking mode renders its own combined mobile header (hamburger + name +
// overflow menu) to recover vertical space, so AppLayout's generic mobile
// bar is suppressed there (#1168).
const TRACKING_PATTERN = /^\/projects\/[^/]+\/track$/;

interface Props {
  readonly children: ReactNode;
}

export function AppLayout({ children }: Props) {
  const { user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  // Track which detail path the user manually expanded the sidebar on.
  // Collapse whenever on a detail page unless this matches the current path.
  const [expandedOnPath, setExpandedOnPath] = useState<string | null>(null);
  const location = useLocation();

  const isDetailPage = DETAIL_PATTERN.test(location.pathname);
  const isTrackingPage = TRACKING_PATTERN.test(location.pathname);
  const desktopCollapsed = isDetailPage && expandedOnPath !== location.pathname;

  return (
    <MobileNavContext.Provider value={{ openSidebar: () => setSidebarOpen(true), openFeedback: () => setFeedbackOpen(true) }}>
      <div className="flex h-dvh overflow-hidden bg-background">
        <Sidebar
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          desktopCollapsed={desktopCollapsed}
          onDesktopExpand={() => setExpandedOnPath(location.pathname)}
          onDesktopCollapse={isDetailPage && !desktopCollapsed ? () => setExpandedOnPath(null) : undefined}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Mobile top bar — hidden on lg+ where sidebar is always visible.
              Tracking mode renders its own combined header instead (#1168). */}
          {!isTrackingPage && (
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card px-4 lg:hidden">
              <button type="button"
                onClick={() => setSidebarOpen(true)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Open navigation"
              >
                <AppIcons.MobileMenu className="h-5 w-5" />
              </button>
              <button type="button"
                onClick={() => setFeedbackOpen(true)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Send feedback"
              >
                <AppIcons.Feedback className="h-5 w-5" />
              </button>
            </div>
          )}

          <ImpersonationBanner />
          <OfflineBanner />

          {/* Detail pages manage their own height/scroll internally; other pages use the scroll wrapper */}
          <main className={`flex-1 ${isDetailPage ? "overflow-hidden" : "overflow-y-auto"}`}>
            {children}
          </main>
        </div>

        {(user?.show_version_numbers ?? true) && <VersionBadge />}
        {feedbackOpen && <FeedbackModal onClose={() => setFeedbackOpen(false)} />}
      </div>
    </MobileNavContext.Provider>
  );
}
