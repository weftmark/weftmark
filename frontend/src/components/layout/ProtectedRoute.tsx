import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { VersionBadge } from "@/components/layout/VersionFooter";
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

  // Superusers only use the admin console — redirect any non-admin route to /admin
  if (user?.is_superuser && !requireAdmin && location.pathname !== "/admin") {
    return <Navigate to="/admin" replace />;
  }

  if (requireAdmin && !user?.is_admin) {
    return <Navigate to="/home" replace />;
  }

  return (
    <>
      {children}
      <VersionBadge />
    </>
  );
}
