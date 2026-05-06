import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

interface HealthResponse {
  status: string;
  version: string;
  worker_version?: string | null;
}

export function VersionBadge() {
  const { data } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/health"),
    staleTime: Infinity,
    retry: false,
  });

  return (
    <div className="fixed bottom-3 right-4 z-50 flex items-center gap-2 text-xs bg-muted border border-border rounded px-2 py-1 text-foreground select-none pointer-events-none">
      <span>UI v{__APP_VERSION__}</span>
      {data?.version && <span>API v{data.version}</span>}
      {data?.worker_version && <span>Worker v{data.worker_version}</span>}
    </div>
  );
}
