import { api } from "./client";
import type { User } from "@/context/AuthContext";

export interface EulaCurrent {
  version: string;
  body_html: string;
  effective_date: string;
}

export async function getCurrentEula(): Promise<EulaCurrent> {
  return api.get<EulaCurrent>("/api/eula/current");
}

export interface UserSettingsUpdate {
  display_name?: string;
  theme?: string;
  activity_theme?: string | null;
  idle_timeout_minutes?: number;
  measurement_system?: string;
  ai_training_consent?: boolean;
  show_version_numbers?: boolean;
  hide_unused_shafts_treadles?: boolean;
  tracker_color_mode?: string;
  tracker_show_weft_color?: boolean;
  tracker_show_drawdown?: boolean;
  tracker_show_progress?: boolean;
  tracker_show_pick_cards?: boolean;
  onboarding_dismissed?: boolean;
}

export async function updateSettings(body: UserSettingsUpdate): Promise<User> {
  return api.patch<User>("/api/users/me", body);
}

export async function acceptEula(version: string): Promise<User> {
  return api.post<User>("/api/users/me/eula", { version });
}

export async function deleteAccount(confirm: string): Promise<void> {
  return api.delete<void>("/api/users/me", { confirm });
}

export interface ExportStatus {
  request_id: string | null;
  status: string | null;
  requested_at: string | null;
  expires_at: string | null;
  error: string | null;
}

export async function requestDataExport(): Promise<ExportStatus> {
  return api.post<ExportStatus>("/api/users/me/data-export", {});
}

export async function getDataExportStatus(): Promise<ExportStatus> {
  return api.get<ExportStatus>("/api/users/me/data-export/status");
}

export function getDataExportDownloadUrl(requestId: string): string {
  return `/api/users/me/data-export/download/${requestId}`;
}

export interface HeatmapProject {
  id: string;
  name: string;
  step_count: number;
}

export interface ActivityDay {
  date: string;
  count: number;
  projects: HeatmapProject[];
}

export interface ActivityHeatmapData {
  days: ActivityDay[];
  earliest_activity_date: string | null;
  years_with_activity: number[];
}

export function getActivityHeatmap(params?: { year?: number }): Promise<ActivityHeatmapData> {
  const qs = params?.year != null ? `?year=${params.year}` : "";
  return api.get<ActivityHeatmapData>(`/api/users/me/activity-heatmap${qs}`);
}

export interface OnboardingStatus {
  eula_accepted: boolean;
  has_loom: boolean;
  has_draft: boolean;
  has_project: boolean;
}

export function getOnboardingStatus(): Promise<OnboardingStatus> {
  return api.get<OnboardingStatus>("/api/users/me/onboarding-status");
}
