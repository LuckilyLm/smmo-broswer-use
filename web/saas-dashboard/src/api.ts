export type ApiRecord = Record<string, any>;

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export async function apiGet<T>(path: string): Promise<T> {
  return request<T>(path);
}

export async function apiPost<T>(path: string, body?: ApiRecord): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body || {}) });
}

export async function apiPatch<T>(path: string, body: ApiRecord): Promise<T> {
  return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}

export async function apiPut<T>(path: string, body: ApiRecord): Promise<T> {
  return request<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export async function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {})
    }
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.status === 204 ? ({} as T) : ((await response.json()) as T);
}
