import { useEffect, useState } from "react";
import { VersionErrorPage } from "@/pages/VersionErrorPage";

type Status = "loading" | "ok" | "mismatch" | "unreachable";

export function VersionGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [backendVersion, setBackendVersion] = useState("");
  const [workerVersion, setWorkerVersion] = useState<string | undefined>();

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data: { version: string; worker_version?: string | null }) => {
        setBackendVersion(data.version);
        setWorkerVersion(data.worker_version ?? undefined);
        const apiMismatch = data.version !== __APP_VERSION__;
        const workerMismatch = !!data.worker_version && data.worker_version !== data.version;
        setStatus(apiMismatch || workerMismatch ? "mismatch" : "ok");
      })
      .catch(() => setStatus("unreachable"));
  }, []);

  if (status === "loading") return null;
  if (status === "ok") return <>{children}</>;
  return (
    <VersionErrorPage
      frontendVersion={__APP_VERSION__}
      backendVersion={backendVersion}
      workerVersion={workerVersion}
    />
  );
}
