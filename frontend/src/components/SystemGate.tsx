import { useEffect, useState } from "react";
import { UninitializedPage } from "@/pages/UninitializedPage";

type Status = "loading" | "initialized" | "uninitialized" | "unreachable";

export function SystemGate({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    fetch("/system/status")
      .then((res) => res.json())
      .then((data: { initialized: boolean }) => {
        setStatus(data.initialized ? "initialized" : "uninitialized");
      })
      .catch(() => setStatus("unreachable"));
  }, []);

  if (status === "loading") return null;
  if (status === "uninitialized") return <UninitializedPage />;
  return <>{children}</>;
}
