import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

const DETAIL_PATTERN = /^\/projects\/[^/]+/;

interface HealthResponse {
  status: string;
  version: string;
  worker_version?: string | null;
}

export function VersionBadge() {
  const { data } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/api/health"),
    staleTime: Infinity,
    retry: false,
  });

  const location = useLocation();
  const isDetailPage = DETAIL_PATTERN.test(location.pathname);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    // Re-show on every navigation (async to avoid synchronous setState in effect)
    const showTimer = setTimeout(() => setVisible(true), 0);
    if (!isDetailPage) return () => clearTimeout(showTimer);
    // Auto-hide after 2s on project detail pages
    const hideTimer = setTimeout(() => setVisible(false), 2000);
    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, [location.pathname, isDetailPage]);

  return (
    <div
      className="fixed bottom-3 right-4 z-50 flex items-center gap-2 text-xs bg-muted border border-border rounded px-2 py-1 text-foreground select-none pointer-events-none"
      style={{ opacity: visible ? 1 : 0, transition: "opacity 0.5s ease" }}
    >
      <span>UI v{__APP_VERSION__}</span>
      {data?.version && <span>API v{data.version}</span>}
      {data?.worker_version && <span>Worker v{data.worker_version}</span>}
    </div>
  );
}
