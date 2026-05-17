import { api } from "@/api/client";

export type SubmissionType = "feedback" | "feature_request" | "bug_report";

export const SUBMISSION_TYPE_LABELS: Record<SubmissionType, string> = {
  feedback: "Feedback",
  feature_request: "Feature Request",
  bug_report: "Bug Report",
};

export interface FeedbackDiagnostics {
  environment: string;
  page_url: string;
  user_agent: string;
  app_version: string | null;
  project_id?: string | null;
  draft_id?: string | null;
}

export interface SubmitFeedbackPayload {
  submission_type: SubmissionType;
  body: string;
  subject?: string | null;
  is_anonymous: boolean;
  diagnostics: FeedbackDiagnostics;
}

export interface FeedbackRecord {
  id: string;
  submission_type: SubmissionType;
  subject: string | null;
  body: string;
  is_anonymous: boolean;
  diagnostics: Record<string, unknown> | null;
  github_discussion_url: string | null;
  dispatch_status: "pending" | "sent" | "failed" | "skipped";
  user_email: string | null;
  deleted_at: string | null;
  created_at: string;
}

export interface FeedbackPage {
  items: FeedbackRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export const submitFeedback = (payload: SubmitFeedbackPayload) =>
  api.post<FeedbackRecord>("/api/feedback", payload);

export const listMyFeedback = () =>
  api.get<FeedbackRecord[]>("/api/feedback/mine");

export const listAdminFeedback = (params: {
  page?: number;
  page_size?: number;
  submission_type?: SubmissionType;
  dispatch_status?: string;
  include_deleted?: boolean;
} = {}) => {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  if (params.submission_type) qs.set("submission_type", params.submission_type);
  if (params.dispatch_status) qs.set("dispatch_status", params.dispatch_status);
  if (params.include_deleted) qs.set("include_deleted", "true");
  const query = qs.toString();
  return api.get<FeedbackPage>(`/api/admin/feedback${query ? `?${query}` : ""}`);
};

export const getAdminFeedbackDetail = (id: string) =>
  api.get<FeedbackRecord>(`/api/admin/feedback/${id}`);

export const softDeleteFeedback = (id: string) =>
  api.delete<FeedbackRecord>(`/api/admin/feedback/${id}`);

export const recoverFeedback = (id: string) =>
  api.post<FeedbackRecord>(`/api/admin/feedback/${id}/recover`, {});

export const retryFeedbackDispatch = (id: string) =>
  api.post<FeedbackRecord>(`/api/admin/feedback/${id}/retry-dispatch`, {});

export interface FeedbackStatus {
  dispatch_status: string;
  github_discussion_url: string | null;
}

export const getFeedbackStatus = (id: string) =>
  api.get<FeedbackStatus>(`/api/feedback/${id}/status`);
