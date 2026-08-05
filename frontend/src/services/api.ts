import { API_BASE_URL } from "../config";
import { tokenStorage } from "./tokenStorage";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Authenticated fetch wrapper - reads the token straight from storage
 * rather than through AuthContext, so plain data-fetching code (hooks,
 * services) doesn't need to be a React component to use it. A 401 here
 * always means the token expired/was invalidated (e.g. logged out
 * elsewhere), so the caller can redirect to /login on that status. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = tokenStorage.getToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail || `Request to ${path} failed (${response.status}).`);
  }
  return response;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return (await response.json()) as T;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await response.json()) as T;
}

export function getPipelineSocketUrl(): string {
  const token = tokenStorage.getToken();
  const base = API_BASE_URL.replace(/^http/, "ws");
  return `${base}/ws/pipeline${token ? `?token=${encodeURIComponent(token)}` : ""}`;
}
