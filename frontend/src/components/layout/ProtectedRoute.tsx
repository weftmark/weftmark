import { Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { VersionBadge } from "@/components/layout/VersionFooter";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  requireAdmin?: boolean;
}

export function ProtectedRoute({ children, requireAdmin = false }: Props) {
  const { user, isLoading, isAuthenticated } = useAuth();

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

  if (requireAdmin && !user?.is_admin) {
    return <Navigate to="/" replace />;
  }

  return (
    <>
      {children}
      <VersionBadge />
    </>
  );
}
