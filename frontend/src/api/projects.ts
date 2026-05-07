export type ProjectType = "treadle" | "lift";
export type ProjectStatus = "active" | "completed" | "abandoned";

export const PROJECT_TYPE_LABELS: Record<ProjectType, string> = {
  treadle: "Treadle tracking",
  lift: "Lift tracking",
};

export const PROJECT_STATUS_LABELS: Record<ProjectStatus, string> = {
  active: "Active",
  completed: "Completed",
  abandoned: "Abandoned",
};

export interface ProjectSummary {
  id: string;
  draft_id: string;
  loom_id: string | null;
  loom_version_id: string | null;
  name: string;
  project_type: ProjectType;
  status: ProjectStatus;
  current_pick: number;
  total_picks: number;
  num_items: number;
  length_unit: string;
  completed_at: string | null;
  abandoned_at: string | null;
  created_at: string;
}

export interface ProjectPhoto {
  id: string;
  filename: string;
  display_order: number;
  created_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  finished_length_per_item: string | null;
  waste_between_items: string | null;
  warp_waste_allowance: string | null;
  completed_at: string | null;
  notes: string | null;
  draft_name: string;
  draft_num_shafts: number | null;
  draft_num_treadles: number | null;
  draft_effective_num_treadles: number | null;
  draft_effective_num_shafts: number | null;
  draft_metadata_overrides: Record<string, { original: number | null; override: number }> | null;
  loom_name: string | null;
  photos: ProjectPhoto[];
}

export interface CreateProjectPayload {
  name: string;
  draft_id: string;
  project_type: ProjectType;
  loom_id?: string;
  loom_version_id?: string;
  finished_length_per_item?: number;
  num_items?: number;
  waste_between_items?: number;
  warp_waste_allowance?: number;
  length_unit?: string;
}

export interface PickRow {
  pick: number;
  active: number[];
  color: string | null;
}

export interface PicksResponse {
  project_type: ProjectType;
  total_picks: number;
  picks: PickRow[];
  has_weft_colors: boolean;
}

import { getAuthToken } from "@/api/client";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(url, { credentials: "include", ...init, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(err.detail ?? "Request failed", res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listProjects(params?: { draftId?: string; loomId?: string }): Promise<ProjectSummary[]> {
  const qs = new URLSearchParams();
  if (params?.draftId) qs.set("draft_id", params.draftId);
  if (params?.loomId) qs.set("loom_id", params.loomId);
  const query = qs.size ? `?${qs}` : "";
  return req(`/api/projects${query}`);
}

export function getProject(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}`);
}

export function createProject(payload: CreateProjectPayload): Promise<ProjectDetail> {
  return req("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function stepProject(id: string, direction: "advance" | "reverse"): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction }),
  });
}

export function completeProject(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/complete`, { method: "POST" });
}

export function abandonProject(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/abandon`, { method: "POST" });
}

export function renameProject(id: string, name: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function updateProjectNotes(id: string, notes: string | null): Promise<ProjectDetail> {
  return req(`/api/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
}

export function restartProject(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/restart`, { method: "POST" });
}

export function cloneProject(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/clone`, { method: "POST" });
}

export function jumpProject(id: string, pick: number): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/jump`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pick }),
  });
}

export function assignLoom(id: string, loomId: string, loomVersionId?: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/assign-loom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ loom_id: loomId, loom_version_id: loomVersionId ?? null }),
  });
}

export function deleteProject(id: string): Promise<void> {
  return req(`/api/projects/${id}`, { method: "DELETE" });
}

export function getProjectPicks(id: string): Promise<PicksResponse> {
  return req(`/api/projects/${id}/picks`);
}

export function projectPhotoUrl(projectId: string, photoId: string): string {
  return `/api/projects/${projectId}/photos/${photoId}`;
}

export function uploadProjectPhoto(projectId: string, file: File): Promise<ProjectPhoto> {
  const body = new FormData();
  body.append("file", file);
  return req(`/api/projects/${projectId}/photos`, { method: "POST", body });
}

export function deleteProjectPhoto(projectId: string, photoId: string): Promise<void> {
  return req(`/api/projects/${projectId}/photos/${photoId}`, { method: "DELETE" });
}
