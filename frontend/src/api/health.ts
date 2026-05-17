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
  checked_at?: string | null;
  next_check_at?: string | null;
}

export async function getHealthReady(): Promise<ReadinessResponse> {
  const res = await fetch("/health/ready");
  return res.json() as Promise<ReadinessResponse>;
}

export async function getHealthDetailed(): Promise<ReadinessResponse> {
  const res = await fetch("/health/detailed");
  return res.json() as Promise<ReadinessResponse>;
}
