const OZ_TO_G = 28.3495;

export function weightBothUnits(
  value: string,
  unit: "oz" | "g",
): { oz: number | undefined; g: number | undefined } {
  const v = parseFloat(value);
  if (!value || isNaN(v)) return { oz: undefined, g: undefined };
  if (unit === "oz") return { oz: v, g: parseFloat((v * OZ_TO_G).toFixed(1)) };
  return { oz: parseFloat((v / OZ_TO_G).toFixed(2)), g: v };
}

export function displayWeight(oz: string | null, g: string | null): string | null {
  if (oz) return `${oz} oz (${Math.round(parseFloat(oz) * OZ_TO_G)} g)`;
  if (g) return `${g} g`;
  return null;
}

import i18next from "i18next";

export const SKEIN_STATUS_LABELS: Record<string, string> = {
  get available() { return i18next.t("skeinStatus.available"); },
  get in_use() { return i18next.t("skeinStatus.in_use"); },
  get consumed() { return i18next.t("skeinStatus.consumed"); },
};

export type SkeinStatus = "available" | "in_use" | "consumed";

export interface Skein {
  id: string;
  status: SkeinStatus;
  current_yardage: string | null;
  current_weight_oz: string | null;
  current_weight_g: string | null;
  notes: string | null;
  created_at: string;
}

export interface YarnSummary {
  id: string;
  brand: string;
  name: string;
  weight_notation: string | null;
  weight_category: string | null;
  fiber_content: string | null;
  color_name: string | null;
  color_hex: string | null;
  unit_yardage: string | null;
  has_photo: boolean;
  skein_count: number;
  available_count: number;
  out_of_stash: boolean;
  archived: boolean;
  ravelry_stash_id: number | null;
  ravelry_yarn_id: number | null;
  ravelry_photo_url: string | null;
  ravelry_thumbnail_url: string | null;
  ravelry_colorway_photo_url: string | null;
  ravelry_colorway_thumbnail_url: string | null;
  ravelry_permalink: string | null;
  ravelry_discontinued: boolean | null;
  ravelry_machine_washable: boolean | null;
  ravelry_yarn_company_url: string | null;
  machine_washable: boolean | null;
  yarn_attribute_ids: number[];
  created_at: string;
}

export interface YarnDetail extends YarnSummary {
  unit_weight_oz: string | null;
  unit_weight_g: string | null;
  yards_per_pound: string | null;
  sett_min: number | null;
  sett_max: number | null;
  purchase_source: string | null;
  purchase_price: string | null;
  purchase_date: string | null;
  dye_lot: string | null;
  notes: string | null;
  skeins: Skein[];
}

export interface CreateYarnPayload {
  brand: string;
  name: string;
  weight_notation?: string;
  weight_category?: string;
  fiber_content?: string;
  color_name?: string;
  color_hex?: string;
  unit_weight_oz?: number;
  unit_weight_g?: number;
  unit_yardage?: number;
  yards_per_pound?: number;
  sett_min?: number;
  sett_max?: number;
  purchase_source?: string;
  purchase_price?: number;
  purchase_date?: string;
  dye_lot?: string | null;
  notes?: string;
  machine_washable?: boolean | null;
  yarn_attribute_ids?: number[];
}

export interface UpdateYarnPayload extends Partial<CreateYarnPayload> {
  ravelry_photo_url?: string | null;
  ravelry_thumbnail_url?: string | null;
}

export interface AddSkeinsPayload {
  quantity?: number;
  status?: SkeinStatus;
  current_yardage?: number;
  current_weight_oz?: number;
  current_weight_g?: number;
  notes?: string;
}

export interface UpdateSkeinPayload {
  status?: SkeinStatus;
  current_yardage?: number | null;
  current_weight_oz?: number | null;
  current_weight_g?: number | null;
  notes?: string | null;
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

export function listYarn(includeArchived = false): Promise<YarnSummary[]> {
  return req(`/api/yarn${includeArchived ? "?include_archived=true" : ""}`);
}

export function getYarn(id: string): Promise<YarnDetail> {
  return req(`/api/yarn/${id}`);
}

export function createYarn(payload: CreateYarnPayload): Promise<YarnDetail> {
  return req("/api/yarn", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateYarn(id: string, payload: UpdateYarnPayload): Promise<YarnDetail> {
  return req(`/api/yarn/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteYarn(id: string): Promise<void> {
  return req(`/api/yarn/${id}`, { method: "DELETE" });
}

export function yarnPhotoUrl(id: string): string {
  return `/api/yarn/${id}/photo`;
}

export async function uploadYarnPhoto(id: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`/api/yarn/${id}/photo`, {
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

export function deleteYarnPhoto(id: string): Promise<void> {
  return req(`/api/yarn/${id}/photo`, { method: "DELETE" });
}

export function addSkeins(yarnId: string, payload: AddSkeinsPayload): Promise<Skein[]> {
  return req(`/api/yarn/${yarnId}/skeins`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateSkein(yarnId: string, skeinId: string, payload: UpdateSkeinPayload): Promise<Skein> {
  return req(`/api/yarn/${yarnId}/skeins/${skeinId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteSkein(yarnId: string, skeinId: string): Promise<void> {
  return req(`/api/yarn/${yarnId}/skeins/${skeinId}`, { method: "DELETE" });
}

export interface PatchColorwayPayload {
  color_name?: string | null;
  colorway_photo_url?: string | null;
  colorway_thumbnail_url?: string | null;
  clear_photos?: boolean;
}

export function patchYarnColorway(id: string, payload: PatchColorwayPayload): Promise<YarnDetail> {
  return req(`/api/yarn/${id}/colorway`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface CloneYarnPayload {
  color_name?: string;
  color_hex?: string;
}

export function cloneYarn(id: string, payload: CloneYarnPayload): Promise<YarnDetail> {
  return req(`/api/yarn/${id}/clone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface YarnAttribute {
  id: number;
  name: string;
  permalink: string;
  description: string | null;
}

export interface YarnAttributeGroup {
  id: number;
  name: string;
  permalink: string;
  attributes: YarnAttribute[];
}

export function getYarnProperties(): Promise<YarnAttributeGroup[]> {
  return req("/api/yarn/properties");
}

export interface YarnProjectRef {
  project_id: string;
  project_name: string;
  project_status: string;
  color_hex: string;
}

export function getYarnProjects(yarnId: string): Promise<YarnProjectRef[]> {
  return req(`/api/yarn/${yarnId}/projects`);
}
