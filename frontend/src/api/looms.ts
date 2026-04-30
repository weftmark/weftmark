export type LoomType = "floor_loom" | "table_loom" | "rigid_heddle" | "inkle" | "other";

export const LOOM_TYPE_LABELS: Record<LoomType, string> = {
  floor_loom: "Floor loom",
  table_loom: "Table loom",
  rigid_heddle: "Rigid heddle",
  inkle: "Inkle",
  other: "Other",
};

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
  loom_type: LoomType;
  manufacturer: string;
  model_name: string;
  serial_number: string | null;
  supports_lift_tracking: boolean;
  supports_treadle_tracking: boolean;
  notes: string | null;
  has_photo: boolean;
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
