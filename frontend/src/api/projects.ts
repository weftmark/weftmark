export interface Project {
  id: string;
  name: string;
  description: string | null;
  wif_filename: string;
  num_shafts: number | null;
  num_treadles: number | null;
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
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

import { getAuthToken } from "@/api/client";

export interface ProjectDetail extends Project {
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

export async function listProjects(): Promise<Project[]> {
  return req("/api/projects");
}

export async function getProject(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}`);
}

export async function uploadProject(
  name: string,
  file: File,
  description?: string,
): Promise<Project> {
  const form = new FormData();
  form.append("name", name);
  form.append("wif_file", file);
  if (description) form.append("description", description);
  return req("/api/projects", { method: "POST", body: form });
}

export async function deleteProject(id: string): Promise<void> {
  return req(`/api/projects/${id}`, { method: "DELETE" });
}

export function previewUrl(id: string): string {
  return `/api/projects/${id}/preview`;
}

export async function generateLiftplan(id: string): Promise<ProjectDetail> {
  return req(`/api/projects/${id}/generate-liftplan`, { method: "POST" });
}
