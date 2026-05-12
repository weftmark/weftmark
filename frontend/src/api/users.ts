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

export async function getDataExport(): Promise<{ status: string; milestone: string; message: string }> {
  return api.get("/api/users/me/data-export");
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
}

export function getActivityHeatmap(): Promise<ActivityHeatmapData> {
  return api.get<ActivityHeatmapData>("/api/users/me/activity-heatmap");
}
