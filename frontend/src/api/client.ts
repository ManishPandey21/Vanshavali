/**
 * Thin fetch wrapper for the Vanshavali API (`/api/v1`).
 *
 * - Cookie sessions: every request uses `credentials: "include"`.
 * - CSRF double-submit: unsafe methods send `X-CSRF-Token` copied from the readable `vsh_csrf` cookie.
 * - Errors: the server's structured `{error: {code, message, details}}` body becomes a typed `ApiError`.
 * - 401: notifies the registered unauthenticated handler (the app redirects to the login screen).
 */

export const API_BASE = "/api/v1";
export const CSRF_COOKIE = "vsh_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface ValidationDetail {
  loc: (string | number)[];
  msg: string;
  type?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }
  get isNotFound(): boolean {
    return this.status === 404;
  }
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** Field-level validation messages keyed by the dotted body path (e.g. `names.0.given_name`). */
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (!Array.isArray(this.details)) return out;
    for (const d of this.details as ValidationDetail[]) {
      if (!d || !Array.isArray(d.loc)) continue;
      const path = d.loc.filter((p) => p !== "body").join(".");
      if (!(path in out)) out[path] = cleanMessage(d.msg);
    }
    return out;
  }
}

function cleanMessage(msg: string): string {
  return msg.replace(/^Value error, /, "");
}

export function readCookie(name: string, source: string = typeof document !== "undefined" ? document.cookie : ""): string | null {
  for (const part of source.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

type UnauthorizedHandler = (err: ApiError) => void;
let onUnauthenticated: UnauthorizedHandler | null = null;

/** Registered once by the app shell; called on any 401 from a non-auth endpoint. */
export function setUnauthenticatedHandler(fn: UnauthorizedHandler | null): void {
  onUnauthenticated = fn;
}

export type QueryValue = string | number | boolean | null | undefined | (string | number)[];

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** Multipart body (file uploads). The browser sets the boundary header itself. */
  form?: FormData;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  /** Don't trigger the global 401 redirect (used by `/auth/me` probing and login). */
  skipAuthRedirect?: boolean;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((item) => params.append(k, String(item)));
    else params.append(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.body !== undefined && !opts.form) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers[CSRF_HEADER] = token;
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), {
      method,
      headers,
      credentials: "include",
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
      signal: opts.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }
  if (!res.ok) {
    const err = toApiError(res.status, data);
    if (err.status === 401 && !opts.skipAuthRedirect && onUnauthenticated) onUnauthenticated(err);
    throw err;
  }
  return data as T;
}

export function toApiError(status: number, data: unknown): ApiError {
  if (data && typeof data === "object" && "error" in data) {
    const e = (data as { error: { code?: string; message?: string; details?: unknown } }).error;
    if (e && typeof e === "object") {
      return new ApiError(status, e.code ?? "http_error", e.message ?? `Request failed (${status})`, e.details);
    }
  }
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    return new ApiError(status, "http_error", typeof d === "string" ? d : `Request failed (${status})`, d);
  }
  return new ApiError(status, "http_error", `Request failed (${status})`);
}

/**
 * Fetch binary content (signed file URLs, GEDCOM export). Errors are parsed like JSON calls.
 * `url` may be an API path ("/exports/gedcom") or an absolute/same-origin URL returned by the API.
 */
export async function apiBlob(url: string, query?: Record<string, QueryValue>): Promise<{ blob: Blob; filename: string | null }> {
  const full = url.startsWith("/api/") || /^https?:/.test(url) ? url : buildUrl(url, query);
  let res: Response;
  try {
    res = await fetch(full, { credentials: "include" });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    let data: unknown;
    try {
      data = await res.json();
    } catch {
      data = undefined;
    }
    const err = toApiError(res.status, data);
    if (err.status === 401 && onUnauthenticated) onUnauthenticated(err);
    throw err;
  }
  const cd = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  const filename = star ? decodeURIComponent(star[1]) : plain ? plain[1] : null;
  return { blob: await res.blob(), filename };
}

/** Trigger a browser download of a blob. */
export function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

export const api = {
  get: <T>(path: string, query?: RequestOptions["query"], signal?: AbortSignal) =>
    apiRequest<T>(path, { query, signal }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body: body ?? {} }),
  put: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => apiRequest<T>(path, { method: "POST", form }),
};
