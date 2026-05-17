import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  requireAdmin?: boolean;
}

export function ProtectedRoute({ children, requireAdmin = false }: Props) {
  const { user, isLoading, isAuthenticated } = useAuth();
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

  // Superusers land in the admin console; allow /settings and specific resource
  // detail pages (/drafts/:id, /looms/:id, /projects/:id) for read-only inspection
  if (
    user?.is_superuser &&
    !requireAdmin &&
    !location.pathname.startsWith("/admin") &&
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
