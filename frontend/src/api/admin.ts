import { api } from "@/api/client";

export interface AdminUserCounts {
  drafts: number;
  projects_active: number;
  projects_completed: number;
  looms: number;
  storage_bytes: number;
  storage_quota_bytes: number;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  is_superuser: boolean;
  is_active: boolean;
  clerk_banned: boolean;
  clerk_errored: boolean;
  deletion_state: string | null;
  deletion_initiated_at: string | null;
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
  total_drafts: number;
  total_projects: number;
  total_looms: number;
  total_yarn: number;
  pending_invites: number;
  total_storage_bytes: number;
}

export interface AdminHealth {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  db_ping_ms: number;
  uptime_seconds: number;
  started_at: string;
}

export interface AdminVersions {
  app: string;
  python: string;
  redis_server: string;
  celery: string;
  worker: string | null;
  postgres: string;
  postgres_source: string;
  backend_packages: Record<string, string>;
}

export interface AdminDbInfo {
  revision: string | null;
  is_at_head: boolean;
  last_squash_at: string | null;
  last_migrated_at: string | null;
}

export interface InviteRecord {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export const listAdminUsers = () => api.get<AdminUser[]>("/api/admin/users");
export const getAdminStats = () => api.get<AdminStats>("/api/admin/stats");
export const getAdminHealth = () => api.get<AdminHealth>("/api/admin/health");
export const getAdminVersions = () => api.get<AdminVersions>("/api/admin/versions");
export const getAdminDbInfo = () => api.get<AdminDbInfo>("/api/admin/db-info");
export const patchAdminUser = (userId: string, body: { is_active?: boolean; is_admin?: boolean; is_superuser?: boolean }) =>
  api.patch<AdminUser>(`/api/admin/users/${userId}`, body);
export const banUser = (userId: string) => api.post<AdminUser>(`/api/admin/users/${userId}/ban`, {});
export const unbanUser = (userId: string) => api.post<AdminUser>(`/api/admin/users/${userId}/unban`, {});

export interface ElevateContentSummary {
  projects: number;
  looms: number;
  drafts: number;
  yarn: number;
}

export const elevateToSuperuser = (userId: string, confirmDeleteContent: boolean) =>
  api.post<{ status: string }>(`/api/admin/users/${userId}/elevate-to-superuser`, {
    confirm_delete_content: confirmDeleteContent,
  });

export const deleteUser = (userId: string) =>
  api.post<{ status: string; user_id: string }>(`/api/admin/users/${userId}/delete`, {
    confirm: "DELETE USER",
  });

export const listInvites = () => api.get<InviteRecord[]>("/auth/invites");
export const createInvite = (email: string, role: string = "user", expires_days?: number) =>
  api.post<InviteRecord>("/auth/invite", { email, role, expires_days });
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

export interface WebhookProbeResult {
  status: "ok" | "skipped" | "error";
  latency_ms: number | null;
  message: string;
}

export const testWebhook = () => api.post<WebhookProbeResult>("/api/admin/test-webhook", {});

export interface AuditLogEntry {
  id: string;
  actor_email: string | null;
  event_type: string;
  target_email: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const getAuditLog = (params: { page?: number; page_size?: number; event_type?: string; q?: string } = {}) => {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.event_type) qs.set("event_type", params.event_type);
  if (params.q) qs.set("q", params.q);
  const query = qs.toString();
  return api.get<AuditLogPage>(`/api/admin/audit-log${query ? `?${query}` : ""}`);
};

export interface ReconcileClerkOnlyUser {
  clerk_user_id: string;
  email: string;
  display_name: string;
}

export interface ReconcileDbOnlyUser {
  user_id: string;
  email: string;
  display_name: string;
  clerk_errored: boolean;
}

export interface ReconcileReport {
  clerk_only: ReconcileClerkOnlyUser[];
  db_only: ReconcileDbOnlyUser[];
}

export const getReconcileReport = () => api.get<ReconcileReport>("/api/admin/reconcile");
export const backfillClerkUser = (clerkUserId: string, role: "user" | "admin" = "user") =>
  api.post<{ status: string; user_id: string; email: string }>(`/api/admin/reconcile/backfill/${clerkUserId}`, { role });

export interface S3OrphanFile {
  key: string;
  size: number;
  last_modified: string;
}

export interface S3AuditResult {
  total_s3_keys: number;
  total_db_paths: number;
  orphaned_count: number;
  orphaned_files: S3OrphanFile[];
  not_applicable: boolean;
}

export interface S3AuditTaskStatus {
  status: "pending" | "running" | "complete" | "failed";
  result?: S3AuditResult;
  error?: string;
}

export const startS3AuditScan = () =>
  api.post<{ task_id: string }>("/api/admin/s3-audit/scan", {});

export const getS3AuditTask = (taskId: string) =>
  api.get<S3AuditTaskStatus>(`/api/admin/s3-audit/task/${taskId}`);

export const cleanupS3Orphans = (keys: string[]) =>
  api.post<{ deleted: number }>("/api/admin/s3-audit/cleanup", { keys });

export interface CveVuln {
  id: string;
  aliases: string[];
  fix_versions: string[];
  description: string;
}

export interface CveFinding {
  name: string;
  version: string;
  vulns: CveVuln[];
}

export interface CveScanResult {
  backend_findings: CveFinding[];
  frontend_findings: CveFinding[];
  scanned_at: string;
  total_findings: number;
}

export interface CveScanTaskStatus {
  status: "pending" | "running" | "complete" | "failed";
  result?: CveScanResult;
  error?: string;
}

export interface CveScanSummary {
  finding_count: number;
  scanned_at: string | null;
}

export const startCveScan = (frontendDeps: Record<string, string>) =>
  api.post<{ task_id: string }>("/api/admin/cve-scan/start", { frontend_deps: frontendDeps });

export const getCveScanTask = (taskId: string) =>
  api.get<CveScanTaskStatus>(`/api/admin/cve-scan/task/${taskId}`);

export const getCveScanSummary = () =>
  api.get<CveScanSummary>("/api/admin/cve-scan/summary");

export interface WorkerActiveTask {
  id: string;
  name: string;
  args_repr: string;
  time_start: number | null;
}

export interface WorkerInfo {
  name: string;
  status: "online" | "offline";
  version: string | null;
  concurrency: number | null;
  completed_tasks: number | null;
  uptime: number | null;
  memory_mb: number | null;
  active_tasks: WorkerActiveTask[];
  reserved_tasks: WorkerActiveTask[];
}

export interface QueueInfo {
  name: string;
  depth: number;
}

export interface WorkerStatus {
  workers: WorkerInfo[];
  queues: QueueInfo[];
  api_version: string;
  checked_at: string;
}

export const getWorkerStatus = () =>
  api.get<WorkerStatus>("/api/admin/worker-status");

export const startDebugSleep = (seconds: number = 45) =>
  api.post<{ task_id: string; seconds: number }>("/api/admin/debug-sleep", { seconds });

export interface TaskHistoryItem {
  task_id: string;
  name: string;
  caller: string;
  state: string;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  wait_seconds: number | null;
  run_seconds: number | null;
  error: string | null;
}

export interface TaskHistoryResponse {
  items: TaskHistoryItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const getTaskHistory = (page: number = 1, pageSize: number = 25) =>
  api.get<TaskHistoryResponse>(`/api/admin/task-history?page=${page}&page_size=${pageSize}`);

export const revokeTask = (taskId: string) =>
  api.post<{ status: string; task_id: string }>(`/api/admin/tasks/${taskId}/revoke`, {});

export const runPurgeSoftDeleted = () =>
  api.post<{ status: string; task_id: string }>("/api/admin/purge-soft-deleted", {});

export interface ScheduledTask {
  name: string;
  display_name: string;
  description: string;
  enabled: boolean;
  cron: string;
  config: Record<string, unknown>;
  next_runs: string[];
  last_fired_at: string | null;
  updated_at: string;
}

export const listScheduledTasks = () =>
  api.get<ScheduledTask[]>("/api/admin/scheduled-tasks");

export const patchScheduledTask = (
  name: string,
  body: { enabled?: boolean; cron?: string; config?: Record<string, unknown> },
) => api.patch<ScheduledTask>(`/api/admin/scheduled-tasks/${name}`, body);

export interface ServerEvent {
  id: number;
  event_type: string;
  severity: "info" | "warn" | "error";
  status: "open" | "closed";
  started_at: string;
  ended_at: string | null;
  elapsed_ms: number | null;
  app_version: string;
  message: string | null;
  details: Record<string, unknown> | null;
}

export interface ServerEventPage {
  items: ServerEvent[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const getServerEvents = (params: { page?: number; page_size?: number; event_type?: string } = {}) => {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.event_type) qs.set("event_type", params.event_type);
  const query = qs.toString();
  return api.get<ServerEventPage>(`/api/admin/server-events${query ? `?${query}` : ""}`);
};
