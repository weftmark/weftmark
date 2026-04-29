import { useEffect, useState } from "react";
import { getHealthReady, type ReadinessResponse, type ReadinessService } from "@/api/health";

function serviceLabel(s: ReadinessService): string {
  return s.detail ? `${s.name} (${s.detail})` : s.name;
}

export function ServiceHealthBanner() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);

  useEffect(() => {
    getHealthReady()
      .then(setReadiness)
      .catch(() => {
        setReadiness({ status: "error", services: [{ name: "backend", ok: false, critical: true, message: "unreachable", detail: "" }] });
      });
  }, []);

  if (!readiness || readiness.status === "ok") return null;

  const failed = readiness.services.filter((s) => !s.ok);
  const labels = failed.map(serviceLabel).join(", ");

  if (readiness.status === "error") {
    return (
      <div className="w-full bg-destructive text-destructive-foreground text-center text-xs font-semibold py-1.5 px-4 select-none">
        Service failure: {labels}
      </div>
    );
  }

  return (
    <div className="w-full bg-amber-400 text-amber-950 text-center text-xs font-semibold py-1.5 px-4 select-none">
      Service warning: {labels}
    </div>
  );
}
