import { useEffect, useState } from "react";
import { getHealthDetailed, type ReadinessResponse, type ReadinessService } from "@/api/health";

function serviceLabel(s: ReadinessService): string {
  return s.detail ? `${s.name} (${s.detail})` : s.name;
}

export function ServiceHealthBanner() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);

  useEffect(() => {
    const check = () =>
      getHealthDetailed()
        .then(setReadiness)
        .catch(() => {
          setReadiness({ status: "error", services: [{ name: "backend", ok: false, critical: true, message: "unreachable", detail: "" }] });
        });
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);

  if (!readiness || readiness.status === "ok" || readiness.status === "starting") return null;

  const failed = readiness.services.filter((s) => !s.ok);
  const webhookFailed = failed.find((s) => s.name === "Clerk Webhook");
  const otherFailed = failed.filter((s) => s.name !== "Clerk Webhook");

  if (readiness.status === "error") {
    const labels = failed.map(serviceLabel).join(", ");
    return (
      <div className="w-full bg-destructive text-destructive-foreground text-center text-xs font-semibold py-1.5 px-4 select-none">
        Service failure: {labels}
      </div>
    );
  }

  return (
    <div className="w-full bg-amber-400 text-amber-950 text-center text-xs font-semibold py-1.5 px-4 select-none">
      {webhookFailed && (
        <span>
          New account registration is temporarily unavailable — existing users are unaffected.
          {otherFailed.length > 0 && "  "}
        </span>
      )}
      {otherFailed.length > 0 && <span>Service warning: {otherFailed.map(serviceLabel).join(", ")}</span>}
    </div>
  );
}
