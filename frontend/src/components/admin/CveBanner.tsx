import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCveScanSummary } from "@/api/admin";

export function CveBanner() {
  const navigate = useNavigate();
  const [dismissed, setDismissed] = useState(false);
  const { data } = useQuery({
    queryKey: ["admin", "cve-summary"],
    queryFn: getCveScanSummary,
    staleTime: 5 * 60_000,
  });

  if (dismissed || !data || data.finding_count == null || data.finding_count === 0) return null;

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
      <span className="text-amber-700 dark:text-amber-300 font-medium">
        {data.finding_count} CVE {data.finding_count === 1 ? "vulnerability" : "vulnerabilities"} found
        {data.scanned_at && (
          <span className="font-normal text-amber-600 dark:text-amber-400 ml-2">
            · last scanned {new Date(data.scanned_at).toLocaleString()}
          </span>
        )}
      </span>
      <div className="flex items-center gap-2 shrink-0">
        <button
          className="text-xs text-amber-700 dark:text-amber-300 underline hover:no-underline"
          onClick={() => navigate("/superuser/cve")}
        >
          View report
        </button>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setDismissed(true)}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
