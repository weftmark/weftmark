import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useImpersonation } from "@/context/ImpersonationContext";
import type { ReactNode } from "react";

interface Props {
  readonly children: ReactNode;
  readonly requireAdmin?: boolean;
  readonly requireSuperuser?: boolean;
}

export function ProtectedRoute({ children, requireAdmin = false, requireSuperuser = false }: Props) {
  const { user, isLoading, isAuthenticated } = useAuth();
  const { isImpersonating } = useImpersonation();
  const location = useLocation();

  if (isLoading && !user) {
    return (
      <div className="flex h-screen items-center justify-center">
        <span className="text-muted-foreground text-sm">Loading…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (requireSuperuser && !user?.is_superuser) {
    return <Navigate to="/unauthorized" replace />;
  }

  // Superusers land in the admin console; allow /settings, /superuser, and
  // specific resource detail pages for read-only inspection.
  // Skip this redirect during impersonation so the superuser can browse as the target user.
  if (
    user?.is_superuser &&
    !isImpersonating &&
    !requireAdmin &&
    !requireSuperuser &&
    !location.pathname.startsWith("/admin") &&
    !location.pathname.startsWith("/superuser") &&
    !location.pathname.startsWith("/settings") &&
    !location.pathname.startsWith("/drafts/") &&
    !location.pathname.startsWith("/looms/") &&
    !location.pathname.startsWith("/projects/")
  ) {
    return <Navigate to="/admin" replace />;
  }

  if (requireAdmin && !user?.is_admin) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
}
