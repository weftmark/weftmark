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

  // Superusers live in the admin console but can still access personal settings
  if (
    user?.is_superuser &&
    !requireAdmin &&
    !location.pathname.startsWith("/admin") &&
    !location.pathname.startsWith("/settings")
  ) {
    return <Navigate to="/admin" replace />;
  }

  if (requireAdmin && !user?.is_admin) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <>{children}</>;
}
