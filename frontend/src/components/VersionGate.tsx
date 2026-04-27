import { useEffect, useState } from "react";
import { VersionErrorPage } from "@/pages/VersionErrorPage";

type Status = "loading" | "ok" | "mismatch" | "unreachable";

export function VersionGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [backendVersion, setBackendVersion] = useState("");

  useEffect(() => {
    fetch("/health")
      .then((res) => res.json())
      .then((data: { version: string }) => {
        setBackendVersion(data.version);
        setStatus(data.version === __APP_VERSION__ ? "ok" : "mismatch");
      })
      .catch(() => setStatus("unreachable"));
  }, []);

  if (status === "loading") return null;
  if (status === "ok") return <>{children}</>;
  return <VersionErrorPage frontendVersion={__APP_VERSION__} backendVersion={backendVersion} />;
}
