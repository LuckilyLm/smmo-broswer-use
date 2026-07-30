import type { ApiRecord } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
    fields?: Array<{ field: string; message: string }>;
  };
}

export class ApiError extends Error {
  code: string;
  status: number;
  fieldErrors?: Record<string, string[]>;
  requestId?: string;

  constructor(code: string, message: string, status: number, fieldErrors?: Record<string, string[]>, requestId?: string) {
    super(message);
    this.code = code;
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.requestId = requestId;
  }
}

function parseFieldErrors(payload: ApiErrorPayload): Record<string, string[]> | undefined {
  const fields = payload.error?.fields;
  if (!fields || !Array.isArray(fields)) return undefined;
  const map: Record<string, string[]> = {};
  for (const f of fields) {
    if (!map[f.field]) map[f.field] = [];
    map[f.field].push(f.message);
  }
  return map;
}

let sessionExpiredHandled = false;

function handleSessionExpired() {
  if (sessionExpiredHandled) return;
  sessionExpiredHandled = true;
  window.dispatchEvent(new Event("saas:session-expired"));
  // Reset after a delay so future 401s can trigger again if needed
  setTimeout(() => { sessionExpiredHandled = false; }, 5000);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const timeoutController = new AbortController();
  const externalSignal = init.signal;
  const abortFromExternal = () => timeoutController.abort(externalSignal?.reason);
  if (externalSignal?.aborted) abortFromExternal();
  else externalSignal?.addEventListener("abort", abortFromExternal, { once: true });
  const timeoutId = setTimeout(() => timeoutController.abort(), 30000);

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> || {}),
  };

  const requestId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  headers["X-Request-Id"] = requestId;

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers,
      signal: timeoutController.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      let payload: ApiErrorPayload = {};
      try {
        payload = await response.json();
      } catch {
        // Non-JSON error response
      }

      const code = payload.error?.code || getDefaultErrorCode(response.status);
      const message = payload.error?.message || getDefaultErrorMessage(response.status);
      const fieldErrors = parseFieldErrors(payload);

      if (response.status === 401) {
        handleSessionExpired();
      }

      throw new ApiError(code, message, response.status, fieldErrors, requestId);
    }

    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    if (err instanceof Error && err.name === "AbortError") {
      const externallyAborted = externalSignal?.aborted;
      throw new ApiError(
        externallyAborted ? "request_aborted" : "request_timeout",
        externallyAborted ? "请求已取消" : "请求超时，请重试",
        0,
        undefined,
        requestId,
      );
    }
    throw new ApiError("network_error", "网络错误，请检查连接", 0, undefined, requestId);
  } finally {
    clearTimeout(timeoutId);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}

function getDefaultErrorCode(status: number): string {
  switch (status) {
    case 401: return "unauthorized";
    case 403: return "forbidden";
    case 404: return "not_found";
    case 409: return "conflict";
    case 422: return "validation_error";
    case 429: return "rate_limited";
    case 500: return "server_error";
    default: return "api_error";
  }
}

function getDefaultErrorMessage(status: number): string {
  switch (status) {
    case 401: return "登录状态已过期，请重新登录";
    case 403: return "权限不足，无法执行此操作";
    case 404: return "请求的资源不存在";
    case 409: return "操作冲突，请刷新后重试";
    case 422: return "请求参数验证失败";
    case 429: return "请求过于频繁，请稍后重试";
    case 500: return "服务器错误，请稍后重试";
    default: return "请求失败";
  }
}

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

export function createAbortableRequest<T>(
  path: string,
  init: RequestInit = {}
): { promise: Promise<T>; abort: () => void } {
  const controller = new AbortController();
  const promise = request<T>(path, {
    ...init,
    signal: controller.signal,
  });
  return { promise, abort: () => controller.abort() };
}
