import { useEffect, useState } from "react";
import { getHealthReady, type ReadinessResponse } from "@/api/health";

export function ServiceHealthBanner() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);

  useEffect(() => {
    getHealthReady()
      .then(setReadiness)
      .catch(() => {
        setReadiness({ status: "error", services: [{ name: "backend", ok: false, critical: true, message: "unreachable" }] });
      });
  }, []);

  if (!readiness || readiness.status === "ok") return null;

  const failed = readiness.services.filter((s) => !s.ok);
  const names = failed.map((s) => s.name).join(", ");

  if (readiness.status === "error") {
    return (
      <div className="w-full bg-destructive text-destructive-foreground text-center text-xs font-semibold py-1.5 px-4 select-none">
        Service failure: {names} — some features may be unavailable
      </div>
    );
  }

  return (
    <div className="w-full bg-amber-400 text-amber-950 text-center text-xs font-semibold py-1.5 px-4 select-none">
      Service warning: {names} — some features may be degraded
    </div>
  );
}
