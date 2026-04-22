export type LoomType = "floor_loom" | "table_loom" | "rigid_heddle" | "inkle" | "other";

export const LOOM_TYPE_LABELS: Record<LoomType, string> = {
  floor_loom: "Floor loom",
  table_loom: "Table loom",
  rigid_heddle: "Rigid heddle",
  inkle: "Inkle",
  other: "Other",
};

export interface LoomVersion {
  id: string;
  version_number: number;
  effective_date: string;
  description: string | null;
  num_shafts: number | null;
  num_treadles: number | null;
  num_heddles: number | null;
  weaving_width: string | null;
  weaving_width_unit: string;
  warp_waste_allowance: string | null;
  warp_waste_unit: string;
  created_at: string;
}

export interface Loom {
  id: string;
  loom_type: LoomType;
  manufacturer: string;
  model_name: string;
  serial_number: string | null;
  supports_lift_tracking: boolean;
  supports_treadle_tracking: boolean;
  notes: string | null;
  current_version: LoomVersion | null;
  created_at: string;
}

export interface LoomDetail extends Loom {
  purchase_date: string | null;
  purchase_price: string | null;
  vendor: string | null;
  versions: LoomVersion[];
}

export interface CreateLoomPayload {
  loom_type: LoomType;
  manufacturer: string;
  model_name: string;
  serial_number?: string;
  purchase_date?: string;
  purchase_price?: number;
  vendor?: string;
  supports_lift_tracking: boolean;
  supports_treadle_tracking: boolean;
  notes?: string;
  effective_date: string;
  num_shafts?: number;
  num_treadles?: number;
  num_heddles?: number;
  weaving_width?: number;
  weaving_width_unit: string;
  warp_waste_allowance?: number;
  warp_waste_unit: string;
  version_description?: string;
}

export interface UpdateLoomPayload {
  loom_type?: LoomType;
  manufacturer?: string;
  model_name?: string;
  serial_number?: string;
  purchase_date?: string;
  purchase_price?: number;
  vendor?: string;
  supports_lift_tracking?: boolean;
  supports_treadle_tracking?: boolean;
  notes?: string;
}

export interface AddVersionPayload {
  effective_date: string;
  description?: string;
  num_shafts?: number;
  num_treadles?: number;
  num_heddles?: number;
  weaving_width?: number;
  weaving_width_unit: string;
  warp_waste_allowance?: number;
  warp_waste_unit: string;
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: "include", ...init });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listLooms(): Promise<Loom[]> {
  return req("/api/looms");
}

export function getLoom(id: string): Promise<LoomDetail> {
  return req(`/api/looms/${id}`);
}

export function createLoom(payload: CreateLoomPayload): Promise<LoomDetail> {
  return req("/api/looms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateLoom(id: string, payload: UpdateLoomPayload): Promise<LoomDetail> {
  return req(`/api/looms/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function addLoomVersion(id: string, payload: AddVersionPayload): Promise<LoomVersion> {
  return req(`/api/looms/${id}/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteLoom(id: string): Promise<void> {
  return req(`/api/looms/${id}`, { method: "DELETE" });
}
