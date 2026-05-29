const BASE_URL = import.meta.env.VITE_API_URL ?? "";

type TokenGetter = () => Promise<string | null>;
let _getToken: TokenGetter | null = null;
let _impersonateUserId: string | null = null;

export function configureApiClient(getter: TokenGetter) {
  _getToken = getter;
}

export function setImpersonationTarget(userId: string | null) {
  _impersonateUserId = userId;
}

export async function getAuthToken(): Promise<string | null> {
  if (!_getToken) return null;
  return _getToken();
}

export async function downloadAuthed(url: string, filename: string): Promise<void> {
  const token = await getAuthToken();
  const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(url, { headers, credentials: "include" });
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };

  if (_getToken) {
    const token = await _getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  if (_impersonateUserId) {
    headers["X-Impersonate-User-ID"] = _impersonateUserId;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    ...init,
    headers,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => response.statusText);
    const err = new Error(text || `HTTP ${response.status}`) as Error & { status: number };
    err.status = response.status;
    throw err;
  }

  // 204 No Content
  if (response.status === 204) return undefined as T;

  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "DELETE", body: body ? JSON.stringify(body) : undefined }),
};
