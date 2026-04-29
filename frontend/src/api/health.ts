export interface ReadinessService {
  name: string;
  ok: boolean;
  critical: boolean;
  message: string;
  detail: string;
}

export interface ReadinessResponse {
  status: "ok" | "degraded" | "error" | "starting";
  services: ReadinessService[];
}

export async function getHealthReady(): Promise<ReadinessResponse> {
  const res = await fetch("/health/ready");
  return res.json() as Promise<ReadinessResponse>;
}
