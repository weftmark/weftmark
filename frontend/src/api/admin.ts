import { api } from "@/api/client";

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_active_at: string | null;
}

export interface AdminStats {
  total_users: number;
  active_users: number;
  active_7d: number;
  active_30d: number;
  active_90d: number;
  total_projects: number;
  total_activities: number;
  total_looms: number;
  total_yarn: number;
  pending_invites: number;
}

export interface AdminHealth {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  db_ping_ms: number;
  uptime_seconds: number;
}

export interface InviteRecord {
  id: string;
  email: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export const listAdminUsers = () => api.get<AdminUser[]>("/api/admin/users");
export const getAdminStats = () => api.get<AdminStats>("/api/admin/stats");
export const getAdminHealth = () => api.get<AdminHealth>("/api/admin/health");
export const patchAdminUser = (userId: string, body: { is_active?: boolean; is_admin?: boolean }) =>
  api.patch<AdminUser>(`/api/admin/users/${userId}`, body);

export const listInvites = () => api.get<InviteRecord[]>("/auth/invites");
export const createInvite = (email: string, expires_days?: number) =>
  api.post<InviteRecord>("/auth/invite", { email, expires_days });
export const revokeInvite = (inviteId: string) => api.delete<void>(`/auth/invite/${inviteId}`);
