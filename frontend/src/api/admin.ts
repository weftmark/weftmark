import { api } from "@/api/client";

export interface AdminUserCounts {
  projects: number;
  activities_active: number;
  activities_completed: number;
  looms: number;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_superuser: boolean;
  is_active: boolean;
  clerk_banned: boolean;
  created_at: string;
  last_active_at: string | null;
  approved_by_name: string | null;
  approved_by_email: string | null;
  counts: AdminUserCounts;
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

export interface AdminVersions {
  app: string;
  python: string;
  fastapi: string;
  sqlalchemy: string;
  alembic: string;
  pyweaving: string;
  pillow: string;
  boto3: string;
  psutil: string;
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
export const getAdminVersions = () => api.get<AdminVersions>("/api/admin/versions");
export const patchAdminUser = (userId: string, body: { is_active?: boolean; is_admin?: boolean; is_superuser?: boolean }) =>
  api.patch<AdminUser>(`/api/admin/users/${userId}`, body);
export const banUser = (userId: string) => api.post<AdminUser>(`/api/admin/users/${userId}/ban`, {});
export const unbanUser = (userId: string) => api.post<AdminUser>(`/api/admin/users/${userId}/unban`, {});

export interface ElevateContentSummary {
  activities: number;
  looms: number;
  projects: number;
  yarn: number;
}

export const elevateToSuperuser = (userId: string, confirmDeleteContent: boolean) =>
  api.post<{ status: string }>(`/api/admin/users/${userId}/elevate-to-superuser`, {
    confirm_delete_content: confirmDeleteContent,
  });

export const listInvites = () => api.get<InviteRecord[]>("/auth/invites");
export const createInvite = (email: string, expires_days?: number) =>
  api.post<InviteRecord>("/auth/invite", { email, expires_days });
export const revokeInvite = (inviteId: string) => api.delete<void>(`/auth/invite/${inviteId}`);

export interface PendingSignup {
  id: string;
  clerk_user_id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export const listPendingSignups = () => api.get<PendingSignup[]>("/api/admin/pending-signups");
export const approvePendingSignup = (id: string) =>
  api.post<{ status: string }>(`/api/admin/pending-signups/${id}/approve`, {});
export const dismissPendingSignup = (id: string) =>
  api.delete<void>(`/api/admin/pending-signups/${id}`);
export const banPendingSignup = (id: string) =>
  api.post<void>(`/api/admin/pending-signups/${id}/ban`, {});

export interface AdminEulaVersion {
  id: number;
  version: string;
  body_html: string;
  effective_date: string;
  created_at: string;
}

export interface EulaVersionSummary {
  id: number;
  version: string;
  effective_date: string;
  created_at: string;
}

export const getAdminEula = () => api.get<AdminEulaVersion>("/api/admin/eula");
export const createEulaVersion = (version: string, body_html: string, effective_date?: string) =>
  api.post<EulaVersionSummary>("/api/admin/eula", { version, body_html, effective_date });

export interface ServicePermCheck {
  name: string;
  status: "ok" | "error";
  message: string;
}

export interface ServiceCheck {
  service: string;
  status: "ok" | "error";
  message: string;
  checks: ServicePermCheck[];
  meta?: Record<string, string>;
}

export const getAdminServices = () => api.get<ServiceCheck[]>("/api/admin/services");
export const sendTestEmail = () => api.post<{ status: string; to: string }>("/api/admin/test-email", {});
