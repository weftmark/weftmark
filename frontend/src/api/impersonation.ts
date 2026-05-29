import { api } from "@/api/client";
import type { User } from "@/context/AuthContext";

export interface ImpersonationStartResponse {
  target: Pick<User, "id" | "email" | "display_name">;
}

export function startImpersonationSession(targetUserId: string): Promise<ImpersonationStartResponse> {
  return api.post<ImpersonationStartResponse>("/impersonation/start", { target_user_id: targetUserId });
}

export function endImpersonationSession(targetUserId: string, durationSeconds: number): Promise<void> {
  return api.post<void>("/impersonation/end", { target_user_id: targetUserId, duration_seconds: durationSeconds });
}
