export interface WifMeasurements {
  warp_length?: number;           // cm, normalized
  warp_length_original?: number;
  warp_length_unit?: string;      // "in" | "cm" | "dp"
  warp_spacing?: number;          // cm
  warp_spacing_original?: number;
  warp_spacing_unit?: string;
  weft_length?: number;           // cm, normalized
  weft_length_original?: number;
  weft_length_unit?: string;
  weft_spacing?: number;          // cm
  weft_spacing_original?: number;
  weft_spacing_unit?: string;
}

export interface WifColor {
  index: number;
  r: number;
  g: number;
  b: number;
  hex: string;
}

export interface ColorStat {
  hex: string;
  count: number;
  percentage: number;
}

/** @deprecated use ColorStat */
export type WeftColorStat = ColorStat;

export interface Draft {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  wif_filename: string;
  num_shafts: number | null;
  num_treadles: number | null;
  effective_num_treadles: number | null;
  effective_num_shafts: number | null;
  warp_threads: number | null;
  weft_threads: number | null;
  has_threading: boolean;
  has_tieup: boolean;
  has_treadling: boolean;
  has_liftplan: boolean;
  liftplan_generated: boolean;
  has_color_palette: boolean;
  lint_warnings: string[];
  lint_errors: string[];
  has_preview: boolean;
  has_drawdown_preview: boolean;
  has_modified_file: boolean;
  metadata_overrides: Record<string, { original: number | null; override: number }> | null;
  wif_measurements: WifMeasurements | null;
  wif_colors: WifColor[] | null;
  weft_color_stats: ColorStat[] | null;
  warp_color_stats: ColorStat[] | null;
  warp_length_cm: number | null;
  warp_length_overridden: boolean;
  weaving_width_override_cm: number | null;
  epi_override: number | null;
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

import { getAuthToken } from "@/api/client";

export interface DraftDetail extends Draft {
  wif_source_software: string | null;
  wif_source_version: string | null;
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
    throw new Error(err.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function listDrafts(): Promise<Draft[]> {
  return req("/api/drafts");
}

export async function getDraft(id: string): Promise<DraftDetail> {
  return req(`/api/drafts/${id}`);
}

export async function uploadDraft(
  name: string,
  file: File,
  description?: string,
): Promise<Draft> {
  const form = new FormData();
  form.append("name", name);
  form.append("wif_file", file);
  if (description) form.append("description", description);
  return req("/api/drafts", { method: "POST", body: form });
}

export async function deleteDraft(id: string): Promise<void> {
  return req(`/api/drafts/${id}`, { method: "DELETE" });
}

export function previewUrl(id: string): string {
  return `/api/drafts/${id}/preview`;
}

export function previewSvgUrl(id: string): string {
  return `/api/drafts/${id}/preview/svg`;
}

export function drawdownPreviewUrl(id: string): string {
  return `/api/drafts/${id}/drawdown_preview`;
}

export async function generateLiftplan(id: string): Promise<DraftDetail> {
  return req(`/api/drafts/${id}/generate-liftplan`, { method: "POST" });
}

export async function downloadWif(id: string, filename: string): Promise<void> {
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`/api/drafts/${id}/wif`, { credentials: "include", headers });
  if (!res.ok) throw new Error("WIF file not available");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadWifModified(id: string, filename: string): Promise<void> {
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`/api/drafts/${id}/wif-modified`, { credentials: "include", headers });
  if (!res.ok) throw new Error("Modified file not available");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const base = filename.replace(/\.wif$/i, "");
  a.download = `${base}-modified.wif`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function overrideDraftMetadata(
  id: string,
  field: "num_treadles" | "num_shafts",
  value: number,
): Promise<DraftDetail> {
  return req(`/api/drafts/${id}/override-metadata`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
}

export async function setDraftWarpLength(
  id: string,
  warpLength: number,
  unit: "cm" | "in",
): Promise<DraftDetail> {
  return req(`/api/drafts/${id}/measurements`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ warp_length: warpLength, unit }),
  });
}

export async function setDraftWeavingWidth(
  id: string,
  width: number,
  unit: "cm" | "in",
): Promise<DraftDetail> {
  return req(`/api/drafts/${id}/measurements`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ weaving_width: width, unit }),
  });
}

export async function setDraftEpi(
  id: string,
  epi: number,
): Promise<DraftDetail> {
  return req(`/api/drafts/${id}/measurements`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ epi, unit: "cm" }),
  });
}
