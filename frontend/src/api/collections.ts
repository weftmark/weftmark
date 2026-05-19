import { api } from "@/api/client";

export interface CollectionSummary {
  id: string;
  name: string;
  description: string | null;
  tags: string[];
  draft_count: number;
  project_count: number;
  created_at: string;
  updated_at: string;
}

export interface DraftMember {
  id: string;
  name: string;
  wif_filename: string;
  has_preview: boolean;
  num_shafts: number | null;
  num_treadles: number | null;
  added_at: string;
}

export interface ProjectMember {
  id: string;
  name: string;
  status: string;
  added_at: string;
}

export interface CollectionDetail {
  id: string;
  name: string;
  description: string | null;
  tags: string[];
  drafts: DraftMember[];
  projects: ProjectMember[];
  created_at: string;
  updated_at: string;
}

export async function listCollections(): Promise<CollectionSummary[]> {
  return api.get<CollectionSummary[]>("/api/collections");
}

export async function getCollection(id: string): Promise<CollectionDetail> {
  return api.get<CollectionDetail>(`/api/collections/${id}`);
}

export async function createCollection(data: {
  name: string;
  description?: string;
  tags?: string[];
}): Promise<CollectionSummary> {
  return api.post<CollectionSummary>("/api/collections", data);
}

export async function updateCollection(
  id: string,
  data: { name?: string; description?: string; tags?: string[] },
): Promise<CollectionSummary> {
  return api.patch<CollectionSummary>(`/api/collections/${id}`, data);
}

export async function deleteCollection(id: string): Promise<void> {
  await api.delete(`/api/collections/${id}`);
}

export async function addDraftToCollection(collectionId: string, draftId: string): Promise<void> {
  await api.post(`/api/collections/${collectionId}/drafts`, { draft_id: draftId });
}

export async function removeDraftFromCollection(collectionId: string, draftId: string): Promise<void> {
  await api.delete(`/api/collections/${collectionId}/drafts/${draftId}`);
}

export async function addProjectToCollection(collectionId: string, projectId: string): Promise<void> {
  await api.post(`/api/collections/${collectionId}/projects`, { project_id: projectId });
}

export async function removeProjectFromCollection(collectionId: string, projectId: string): Promise<void> {
  await api.delete(`/api/collections/${collectionId}/projects/${projectId}`);
}
