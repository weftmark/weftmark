export type ActivityType = "treadle" | "lift";
export type ActivityStatus = "active" | "completed" | "abandoned";

export const ACTIVITY_TYPE_LABELS: Record<ActivityType, string> = {
  treadle: "Treadle tracking",
  lift: "Lift tracking",
};

export const ACTIVITY_STATUS_LABELS: Record<ActivityStatus, string> = {
  active: "Active",
  completed: "Completed",
  abandoned: "Abandoned",
};

export interface ActivitySummary {
  id: string;
  project_id: string;
  loom_id: string | null;
  loom_version_id: string | null;
  name: string;
  activity_type: ActivityType;
  status: ActivityStatus;
  current_pick: number;
  total_picks: number;
  num_items: number;
  length_unit: string;
  completed_at: string | null;
  abandoned_at: string | null;
  created_at: string;
}

export interface ActivityDetail extends ActivitySummary {
  finished_length_per_item: string | null;
  waste_between_items: string | null;
  warp_waste_allowance: string | null;
  completed_at: string | null;
  notes: string | null;
  project_name: string;
  project_num_shafts: number | null;
  project_num_treadles: number | null;
  loom_name: string | null;
}

export interface CreateActivityPayload {
  name: string;
  project_id: string;
  activity_type: ActivityType;
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
  activity_type: ActivityType;
  total_picks: number;
  picks: PickRow[];
  has_weft_colors: boolean;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: "include", ...init });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(err.detail ?? "Request failed", res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listActivities(): Promise<ActivitySummary[]> {
  return req("/api/activities");
}

export function getActivity(id: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}`);
}

export function createActivity(payload: CreateActivityPayload): Promise<ActivityDetail> {
  return req("/api/activities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function stepActivity(id: string, direction: "advance" | "reverse"): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction }),
  });
}

export function completeActivity(id: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/complete`, { method: "POST" });
}

export function abandonActivity(id: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/abandon`, { method: "POST" });
}

export function renameActivity(id: string, name: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function restartActivity(id: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/restart`, { method: "POST" });
}

export function cloneActivity(id: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/clone`, { method: "POST" });
}

export function jumpActivity(id: string, pick: number): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/jump`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pick }),
  });
}

export function assignLoom(id: string, loomId: string, loomVersionId?: string): Promise<ActivityDetail> {
  return req(`/api/activities/${id}/assign-loom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ loom_id: loomId, loom_version_id: loomVersionId ?? null }),
  });
}

export function deleteActivity(id: string): Promise<void> {
  return req(`/api/activities/${id}`, { method: "DELETE" });
}

export function getActivityPicks(id: string): Promise<PicksResponse> {
  return req(`/api/activities/${id}/picks`);
}
