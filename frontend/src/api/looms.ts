export type LoomType =
  | "floor_loom"
  | "table_loom"
  | "rigid_heddle"
  | "inkle"
  | "dobby_floor_loom"
  | "tapestry_loom"
  | "rug_loom"
  | "frame_loom"
  | "other";

export const LOOM_TYPE_LABELS: Record<LoomType, string> = {
  floor_loom: "Floor Loom — treadle tracking",
  table_loom: "Table Loom — lift tracking",
  rigid_heddle: "Rigid Heddle",
  inkle: "Inkle",
  dobby_floor_loom: "Dobby Floor Loom",
  tapestry_loom: "Tapestry Loom — project tracking not currently supported",
  rug_loom: "Rug Loom — project tracking not currently supported",
  frame_loom: "Frame Loom — project tracking not currently supported",
  other: "Other",
};

/** Loom types that support project tracking (treadle or lift). */
export const SUPPORTED_LOOM_TYPES = new Set<LoomType>(["floor_loom", "table_loom"]);

export interface LoomVersionPhoto {
  id: string;
  filename: string;
  display_order: number;
  created_at: string;
}

export interface LoomVersionReceipt {
  id: string;
  filename: string;
  description: string | null;
  created_at: string;
}

export interface LoomVersionAccessory {
  id: string;
  name: string;
  created_at: string;
}

export interface LoomReed {
  id: string;
  dents_per_inch: number;
  width_cm: number | null;
  label: string | null;
  notes: string | null;
  created_at: string;
}

export interface LoomVersion {
  id: string;
  version_number: number;
  name: string | null;
  effective_date: string;
  description: string | null;
  num_shafts: number | null;
  num_treadles: number | null;
  num_heddles: number | null;
  weaving_width: string | null;
  weaving_width_unit: string;
  warp_waste_allowance: string | null;
  warp_waste_unit: string;
  photos: LoomVersionPhoto[];
  receipts: LoomVersionReceipt[];
  accessories: LoomVersionAccessory[];
  created_at: string;
}

export interface Loom {
  id: string;
  owner_id: string;
  loom_type: LoomType;
  manufacturer: string;
  model_name: string;
  serial_number: string | null;
  loom_reference_id: string | null;
  supports_lift_tracking: boolean;
  supports_treadle_tracking: boolean;
  notes: string | null;
  has_photo: boolean;
  current_version: LoomVersion | null;
  reeds: LoomReed[];
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
  loom_reference_id?: string;
  purchase_date?: string;
  purchase_price?: number;
  vendor?: string;
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
  notes?: string;
}

export interface AddVersionPayload {
  name?: string;
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

export interface UpdateVersionPayload {
  name?: string;
  description?: string;
  num_shafts?: number;
  num_treadles?: number;
  weaving_width?: number;
  weaving_width_unit?: string;
  warp_waste_allowance?: number | null;
  warp_waste_unit?: string;
}

export interface CloneVersionPayload {
  name?: string;
  effective_date: string;
  description?: string;
  include_accessories?: boolean;
}

import { getAuthToken } from "@/api/client";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(url, { credentials: "include", ...init, headers });
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

export function updateLoomVersion(loomId: string, versionId: string, payload: UpdateVersionPayload): Promise<LoomVersion> {
  return req(`/api/looms/${loomId}/versions/${versionId}`, {
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

export function loomPhotoUrl(id: string): string {
  return `/api/looms/${id}/photo`;
}

export async function uploadLoomPhoto(id: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`/api/looms/${id}/photo`, {
    method: "PUT",
    credentials: "include",
    headers,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }
}

export async function deleteLoomPhoto(id: string): Promise<void> {
  await req(`/api/looms/${id}/photo`, { method: "DELETE" });
}

export function versionPhotoUrl(loomId: string, versionId: string, photoId: string): string {
  return `/api/looms/${loomId}/versions/${versionId}/photos/${photoId}`;
}

export async function uploadVersionPhoto(loomId: string, versionId: string, file: File): Promise<LoomVersionPhoto> {
  const form = new FormData();
  form.append("file", file);
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`/api/looms/${loomId}/versions/${versionId}/photos`, {
    method: "POST",
    credentials: "include",
    headers,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function deleteVersionPhoto(loomId: string, versionId: string, photoId: string): Promise<void> {
  await req(`/api/looms/${loomId}/versions/${versionId}/photos/${photoId}`, { method: "DELETE" });
}

export function versionReceiptUrl(loomId: string, versionId: string, receiptId: string): string {
  return `/api/looms/${loomId}/versions/${versionId}/receipts/${receiptId}`;
}

export async function uploadVersionReceipt(
  loomId: string,
  versionId: string,
  file: File,
  description?: string,
): Promise<LoomVersionReceipt> {
  const form = new FormData();
  form.append("file", file);
  if (description) form.append("description", description);
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`/api/looms/${loomId}/versions/${versionId}/receipts`, {
    method: "POST",
    credentials: "include",
    headers,
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function deleteVersionReceipt(loomId: string, versionId: string, receiptId: string): Promise<void> {
  await req(`/api/looms/${loomId}/versions/${versionId}/receipts/${receiptId}`, { method: "DELETE" });
}

export function updateVersion(loomId: string, versionId: string, payload: UpdateVersionPayload): Promise<LoomVersion> {
  return req(`/api/looms/${loomId}/versions/${versionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function cloneVersion(loomId: string, versionId: string, payload: CloneVersionPayload): Promise<LoomVersion> {
  return req(`/api/looms/${loomId}/versions/${versionId}/clone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function addAccessory(loomId: string, versionId: string, name: string): Promise<LoomVersionAccessory> {
  return req(`/api/looms/${loomId}/versions/${versionId}/accessories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function deleteAccessory(loomId: string, versionId: string, accessoryId: string): Promise<void> {
  return req(`/api/looms/${loomId}/versions/${versionId}/accessories/${accessoryId}`, { method: "DELETE" });
}

export interface AddReedPayload {
  dents_per_inch: number;
  width_cm?: number;
  label?: string;
  notes?: string;
}

export function addReed(loomId: string, payload: AddReedPayload): Promise<LoomReed> {
  return req(`/api/looms/${loomId}/reeds`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteReed(loomId: string, reedId: string): Promise<void> {
  return req(`/api/looms/${loomId}/reeds/${reedId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Loom catalog (loom_references)
// ---------------------------------------------------------------------------

export interface LoomReferenceSummary {
  id: string;
  brand: string;
  model_name: string;
  model_series: string | null;
  loom_category: string;
  shedding_mechanism: string | null;
  shaft_count_options: number[] | null;
  treadle_count: number[] | null;
  weaving_width_options_inches: number[] | null;
  weaving_width_options_cm: number[] | null;
  foldable: boolean | null;
  origin_country: string | null;
}

export interface LoomReferenceDetail extends LoomReferenceSummary {
  frame_material: string | null;
  foldable_while_warped: boolean | null;
  weight_lbs: string | null;
  unfolded_depth_inches: string | null;
  folded_depth_inches: string | null;
  castle_height_inches: string | null;
  breast_beam_height_inches: string | null;
  reed_included: boolean | null;
  reed_dent_included: number[] | null;
  reed_material: string | null;
  heddle_type: string | null;
  heddles_per_shaft_included: string | null;
  brake_type: string | null;
  beater_type: string | null;
  beater_adjustable: boolean | null;
  tie_up_system: string | null;
  treadle_hinge: string | null;
  shaft_upgrade_available: boolean | null;
  max_shafts_with_upgrade: number | null;
  four_now_four_later: boolean | null;
  height_extender_available: boolean | null;
  height_extender_inches: string | null;
  sectional_beam_available: boolean | null;
  double_back_beam_available: boolean | null;
  floating_breast_beam: boolean | null;
  fly_shuttle_available: boolean | null;
  mobility_wheels_included: boolean | null;
  stroller_available: boolean | null;
  shaft_switching_device_available: boolean | null;
  lease_sticks_included: boolean | null;
  raddle_included: boolean | null;
  shuttle_included: boolean | null;
  carry_bag_included: boolean | null;
  assembly_required: boolean | null;
  finish_required: boolean | null;
  origin_country: string | null;
  warranty_years: string | null;
  dobby_type: string | null;
  compatible_software: string[] | null;
}

/** Search the public catalog (no auth required). Used for typeahead. */
export function searchLoomCatalog(q: string): Promise<LoomReferenceSummary[]> {
  return fetch(`/api/loom-catalog/search?q=${encodeURIComponent(q)}&limit=20`)
    .then((r) => r.json());
}

/** Full catalog list with optional filters. */
export function listLoomCatalog(params?: {
  q?: string;
  category?: string;
  foldable?: boolean;
}): Promise<LoomReferenceSummary[]> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set("q", params.q);
  if (params?.category) sp.set("category", params.category);
  if (params?.foldable !== undefined) sp.set("foldable", String(params.foldable));
  return fetch(`/api/loom-catalog?${sp}`).then((r) => r.json());
}

export function getLoomCatalogEntry(id: string): Promise<LoomReferenceDetail> {
  return fetch(`/api/loom-catalog/${id}`).then((r) => r.json());
}

export function linkLoomReference(loomId: string, referenceId: string | null): Promise<LoomDetail> {
  return req(`/api/looms/${loomId}/link-reference`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ loom_reference_id: referenceId }),
  });
}

// Admin catalog CRUD
export function adminListLoomCatalog(q?: string): Promise<LoomReferenceDetail[]> {
  const url = q ? `/api/admin/loom-catalog?q=${encodeURIComponent(q)}` : "/api/admin/loom-catalog";
  return req(url);
}

export function adminCreateLoomReference(payload: Partial<LoomReferenceDetail>): Promise<LoomReferenceDetail> {
  return req("/api/admin/loom-catalog", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function adminUpdateLoomReference(id: string, payload: Partial<LoomReferenceDetail>): Promise<LoomReferenceDetail> {
  return req(`/api/admin/loom-catalog/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function adminDeleteLoomReference(id: string): Promise<void> {
  return req(`/api/admin/loom-catalog/${id}`, { method: "DELETE" });
}
