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

export interface ProjectDetail extends Project {
  wif_source_software: string | null;
  wif_source_version: string | null;
}

export async function listProjects(): Promise<Project[]> {
  const res = await fetch("/api/projects", { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load projects");
  return res.json();
}

export async function getProject(id: string): Promise<ProjectDetail> {
  const res = await fetch(`/api/projects/${id}`, { credentials: "include" });
  if (!res.ok) throw new Error("Failed to load project");
  return res.json();
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

  const res = await fetch("/api/projects", {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail ?? "Upload failed");
  }
  return res.json();
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`/api/projects/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to delete project");
}

export function previewUrl(id: string): string {
  return `/api/projects/${id}/preview`;
}

export async function generateLiftplan(id: string): Promise<ProjectDetail> {
  const res = await fetch(`/api/projects/${id}/generate-liftplan`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to generate lift plan" }));
    throw new Error(err.detail ?? "Failed to generate lift plan");
  }
  return res.json();
}
