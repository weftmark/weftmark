import { api } from "./client";

export interface RavelryStatus {
  connected: boolean;
  ravelry_username: string | null;
  last_synced_at: string | null;
}

export interface SyncResult {
  synced: number;
  unchanged: boolean;
  last_synced_at: string | null;
}

export async function getRavelryStatus(): Promise<RavelryStatus> {
  return api.get<RavelryStatus>("/api/ravelry/status");
}

export async function getRavelryAuthorizeUrl(): Promise<{ url: string }> {
  return api.get<{ url: string }>("/api/ravelry/authorize");
}

export async function disconnectRavelry(): Promise<void> {
  return api.delete<void>("/api/ravelry/connection");
}

export async function syncRavelryStash(): Promise<SyncResult> {
  return api.post<SyncResult>("/api/ravelry/sync", {});
}

export interface RavelryFiberContent {
  percentage: number | null;
  fiber_category: { name: string; parent: { name: string } | null };
}

export interface RavelryYarnApiPhoto {
  id: number;
  sort_order: number;
  medium_url: string | null;
  small_url: string | null;
  square_url: string | null;
  thumbnail_url: string | null;
}

export interface RavelryYarnApiDetail {
  id: number;
  name: string;
  permalink: string;
  discontinued: boolean;
  machine_washable: boolean | null;
  rating_average: string | null;
  rating_count: number | null;
  grams: number | null;
  yardage: number | null;
  min_gauge: number | null;
  max_gauge: number | null;
  gauge_divisor: number | null;
  gauge_pattern: string | null;
  wpi: string | null;
  ply: string | null;
  fiber_contents: RavelryFiberContent[];
  photos: RavelryYarnApiPhoto[];
  yarn_company: { name: string; url: string | null; permalink: string } | null;
  notes: string | null;
  url: string | null;
}

export interface RavelryYarnDetailResponse {
  yarn: RavelryYarnApiDetail;
  colorways: RavelryColorway[];
}

export async function getRavelryYarnDetail(ravelryYarnId: number): Promise<RavelryYarnDetailResponse> {
  return api.get<RavelryYarnDetailResponse>(`/api/ravelry/yarn-detail/${ravelryYarnId}`);
}

export interface RavelryCompany {
  id: number;
  name: string;
  permalink: string;
}

export interface RavelryYarnResult {
  id: number;
  name: string;
  company_name: string;
  permalink: string;
  weight_name: string | null;
  photo_url: string | null;
}

export interface RavelryColorway {
  id: number;
  name: string;
  current_status: string;
  photos: { square_url: string | null; thumbnail_url: string | null }[];
}

export async function getPopularRavelryCompanies(limit = 10): Promise<RavelryCompany[]> {
  return api.get<RavelryCompany[]>(`/api/ravelry/popular/companies?limit=${limit}`);
}

export async function getPopularRavelryYarns(companyId: number, companyName: string, limit = 8): Promise<RavelryYarnResult[]> {
  const params = new URLSearchParams({ company_id: String(companyId), company_name: companyName, limit: String(limit) });
  return api.get<RavelryYarnResult[]>(`/api/ravelry/popular/yarns?${params}`);
}

export async function searchRavelryCompanies(q: string): Promise<RavelryCompany[]> {
  return api.get<RavelryCompany[]>(`/api/ravelry/search/companies?q=${encodeURIComponent(q)}`);
}

export async function searchRavelryYarns(q: string, companyId?: number): Promise<RavelryYarnResult[]> {
  const params = new URLSearchParams({ q });
  if (companyId) params.set("company_id", String(companyId));
  return api.get<RavelryYarnResult[]>(`/api/ravelry/search/yarns?${params}`);
}

export async function importRavelryYarn(payload: {
  ravelry_yarn_id: number;
  color_name?: string;
  color_hex?: string;
}): Promise<{ id: string }> {
  return api.post<{ id: string }>("/api/ravelry/import-yarn", payload);
}

export async function pushYarnToStash(yarnId: string): Promise<{ ravelry_stash_id: number }> {
  return api.post<{ ravelry_stash_id: number }>(`/api/ravelry/stash-push/${yarnId}`, {});
}

export async function pushBulkToStash(): Promise<{ pushed: number; skipped: number }> {
  return api.post<{ pushed: number; skipped: number }>("/api/ravelry/stash-push/bulk", {});
}
