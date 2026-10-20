const API_BASE = "/api/proxy";

import { isProtectedPath } from "./protected-paths";

/**
 * Turn a stored ``image_url`` (``/uploads/issues/x.jpg``) into an authenticated
 * fetch URL.
 *
 * Uploads are no longer served by a public ``/uploads`` static mount — they go
 * through the authed proxy as ``/api/v1/issues/media/...``, so the browser
 * attaches the session cookie and the proxy adds the Bearer header. Building
 * the URL here keeps every caller from having to remember that mapping, and
 * makes an absolute backend URL (from an older row or a test fixture) degrade
 * to the proxied form instead of pointing at a now-unmounted path.
 */
export function mediaUrl(imageUrl: string | null | undefined): string {
  if (!imageUrl) return "";
  if (imageUrl.startsWith("/api/proxy/") || imageUrl.startsWith("/api/v1/issues/media/")) {
    return imageUrl;
  }
  // Strip a leading origin, then the /uploads prefix, and rebuild under media/.
  let path = imageUrl.replace(/^https?:\/\/[^/]+/i, "");
  path = path.replace(/^\/uploads\//, "");
  if (!path) return "";
  return `${API_BASE}/issues/media/${path}`;
}

let refreshPromise: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function rawFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (
    res.status === 401 &&
    !path.startsWith("/auth/login") &&
    !path.startsWith("/auth/register") &&
    !path.startsWith("/auth/refresh")
  ) {
    if (!refreshPromise) {
      refreshPromise = tryRefresh().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      const retry = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
      });
      if (retry.ok) {
        if (retry.status === 204) return undefined as T;
        return retry.json();
      }
    }
    // Only bounce to /login from a *protected* page. A 401 on a public page
    // (the marketing landing runs a couple of read-only queries) is a normal
    // answer, and treating it as a dead session navigated visitors away from
    // the page they deliberately opened. `expired=1` tells the middleware this
    // is a session-expiry redirect, so a stale-but-present cookie cannot bounce
    // /login straight back to the app and loop (mirrors the url-shortner flow).
    if (typeof window !== "undefined" && isProtectedPath(window.location.pathname)) {
      window.location.href = "/login?expired=1";
    }
    throw new Error("Session expired. Please login again.");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
    throw new Error(msg || "Request failed");
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export function getErrorMessage(error: unknown, fallback = "Request failed"): string {
  return error instanceof Error ? error.message : fallback;
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  return rawFetch<T>(path, options);
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  created_at: string;
  two_factor_enabled: boolean;
}

export interface Issue {
  id: number;
  issue_type: string;
  confidence: number;
  severity: number;
  status: string;
  latitude: number;
  longitude: number;
  description: string | null;
  image_url: string;
  review_required: boolean;
  ward_id: number;
  reporter_id: number;
  created_at: string;
  assigned_to: string | null;
  engineer_name: string | null;
  model_used: string | null;
  probabilities: Record<string, number> | null;
}

export interface MlInfo {
  model_path: string;
  model_exists: boolean;
  model_size_mb: number;
  onnx_path: string;
  onnx_exists: boolean;
  onnx_size_mb?: number;
  model_type?: string;
  adapter_exists: boolean;
  adapter_size_mb?: number;
  classes: string[];
  num_classes: number;
  device?: string;
  default_threshold?: number;
  review_threshold?: number;
  reject_threshold?: number;
}

export interface Ward {
  id: number;
  name: string;
  polygon: Record<string, number>[];
  center_lat: number;
  center_lon: number;
  population: number | null;
}

export interface Engineer {
  id: number;
  user_id: number;
  ward_id: number;
  specialization: string;
  current_workload: number;
  max_workload: number;
  is_available: boolean;
  avg_resolution_hours: number;
}

export interface DashboardStats {
  total_issues: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_ward: { ward: string; count: number }[];
  recent_count: number;
}

export interface HeatmapPoint {
  lat: number;
  lng: number;
  type: string;
  severity: number;
  status: string;
}

/** Aggregate counters for the public landing page (no session required). */
export interface PublicStats {
  total_issues: number;
  resolved_issues: number;
  wards_covered: number;
  active_engineers: number;
  avg_resolution_hours: number | null;
}

export const auth = {
  login: (email: string, password: string) =>
    apiFetch<{ detail: string; challenge?: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, full_name: string, role: string = "field_worker") =>
    apiFetch<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name, role }),
    }),
  me: () => apiFetch<User>("/auth/me"),
  logout: () =>
    apiFetch<{ detail: string }>("/auth/logout", { method: "POST" }),
  forgotPassword: (email: string) =>
    apiFetch<{ detail: string }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, newPassword: string) =>
    apiFetch<{ detail: string }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiFetch<{ detail: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  wsTicket: () => apiFetch<{ ticket: string }>("/auth/ws-ticket"),
  oauthAuthorizeUrl: (provider: "google" | "github", redirect?: string) =>
    `${API_BASE}/auth/oauth/${provider}/authorize${redirect ? `?redirect=${encodeURIComponent(redirect)}` : ""}`,
  oauthProviders: () => apiFetch<{ google: boolean; github: boolean }>("/auth/oauth/providers"),

  // 2FA
  twofaVerify: (challenge: string, code: string) =>
    apiFetch<{ detail: string }>("/auth/2fa/verify", {
      method: "POST",
      body: JSON.stringify({ challenge, code }),
    }),
  twofaEnable: () =>
    apiFetch<{ secret: string; provisioning_uri: string }>("/auth/2fa/enable", {
      method: "POST",
    }),
  twofaConfirm: (code: string) =>
    apiFetch<{ recovery_codes: string[] }>("/auth/2fa/confirm", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  twofaDisable: (code: string) =>
    apiFetch<{ detail: string }>("/auth/2fa/disable", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
};

export interface IssueListParams {
  skip?: number;
  limit?: number;
  status?: string;
  issue_type?: string;
  severity?: number;
  ward_id?: number;
  search?: string;
  sort?: string;
  order?: string;
}

export const issues = {
  list: (params?: IssueListParams) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.status) q.set("status", params.status);
    if (params?.issue_type) q.set("issue_type", params.issue_type);
    if (params?.severity) q.set("severity", String(params.severity));
    if (params?.ward_id) q.set("ward_id", String(params.ward_id));
    if (params?.search) q.set("search", params.search);
    if (params?.sort) q.set("sort", params.sort);
    if (params?.order) q.set("order", params.order);
    return apiFetch<{ items: Issue[]; total: number }>(`/issues?${q}`);
  },
  get: (id: number) => apiFetch<Issue>(`/issues/${id}`),
  upload: (
    file: File,
    latitude: number,
    longitude: number,
    description: string = "",
    force_submit: boolean = false,
    idempotencyKey?: string
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("latitude", String(latitude));
    form.append("longitude", String(longitude));
    form.append("description", description);
    form.append("force_submit", String(force_submit));
    return apiFetch<Issue>("/issues/upload", {
      method: "POST",
      body: form,
      // A stable key lets the backend collapse a retry of the same logical
      // upload into the original issue instead of creating a duplicate.
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    });
  },
  updateStatus: (id: number, status: string) =>
    apiFetch<Issue>(`/issues/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  assign: (id: number, engineerId: number) =>
    apiFetch<Issue>(`/issues/${id}/assign`, {
      method: "POST",
      body: JSON.stringify({ engineer_id: engineerId }),
    }),
  reassign: (id: number, engineerId: number) =>
    apiFetch<Issue>(`/issues/${id}/reassign`, {
      method: "POST",
      body: JSON.stringify({ engineer_id: engineerId }),
    }),
  delete: (id: number) =>
    apiFetch<{ detail: string; issue_id: number }>(`/issues/${id}`, {
      method: "DELETE",
    }),
};

export const admin = {
  reviewQueue: (params?: {
    skip?: number;
    limit?: number;
    issue_type?: string;
    severity?: number;
    sort?: string;
    order?: string;
  }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.issue_type) q.set("issue_type", params.issue_type);
    if (params?.severity) q.set("severity", String(params.severity));
    if (params?.sort) q.set("sort", params.sort);
    if (params?.order) q.set("order", params.order);
    return apiFetch<{ items: Issue[]; total: number }>(`/admin/review-queue?${q}`);
  },
  reviewIssue: (id: number, action: string, newType?: string) =>
    apiFetch<{ detail: string; issue_id: number; issue_type: string }>(
      `/admin/review/${id}`,
      { method: "POST", body: JSON.stringify({ action, new_type: newType }) }
    ),
  listUsers: (params?: { skip?: number; limit?: number; search?: string; role?: string; sort?: string; order?: string }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.search) q.set("search", params.search);
    if (params?.role) q.set("role", params.role);
    if (params?.sort) q.set("sort", params.sort);
    if (params?.order) q.set("order", params.order);
    return apiFetch<{ items: User[]; total: number }>(`/admin/users?${q}`);
  },
  updateUserRole: (userId: number, role: string) =>
    apiFetch<{ detail: string; user_id: number; role: string }>(
      `/admin/users/${userId}/role`,
      { method: "POST", body: JSON.stringify({ action: "change_type", new_type: role }) }
    ),
};

export const wards = {
  list: () => apiFetch<Ward[]>("/wards"),
};

export const engineers = {
  list: () => apiFetch<Engineer[]>("/engineers"),
  listPaged: (params?: {
    skip?: number;
    limit?: number;
    specialization?: string;
    ward_id?: number;
    available?: boolean;
    sort?: string;
    order?: string;
  }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.specialization) q.set("specialization", params.specialization);
    if (params?.ward_id) q.set("ward_id", String(params.ward_id));
    if (params?.available !== undefined) q.set("available", String(params.available));
    if (params?.sort) q.set("sort", params.sort);
    if (params?.order) q.set("order", params.order);
    return apiFetch<{ items: Engineer[]; total: number }>(`/engineers/list?${q}`);
  },
  /**
   * The caller's own engineer profile, or null when they do not have one.
   * Used to decide whether the engineer-only `/resolution` flow is available
   * without depending on the (potentially admin-scoped) full engineers list.
   */
  myProfile: () => apiFetch<Engineer>("/engineers/me").catch(() => null),
  create: (data: { user_id: number; ward_id: number; specialization?: string; max_workload?: number }) =>
    apiFetch<Engineer>("/engineers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const dashboard = {
  stats: () => apiFetch<DashboardStats>("/dashboard/stats"),
  heatmap: () => apiFetch<HeatmapPoint[]>("/dashboard/heatmap"),
  publicStats: () => apiFetch<PublicStats>("/dashboard/public-stats"),
};

export interface ResolutionResult {
  id: number;
  issue_id: number;
  status: string;
  message: string;
  resolved_at: string;
}

export const resolution = {
  /**
   * Close an issue with photographic proof of the fix. FormData is used so the
   * browser sets the multipart boundary itself; `rawFetch` deliberately omits
   * the JSON Content-Type for FormData bodies.
   */
  resolve: (issueId: number, file: File, notes = "") => {
    const form = new FormData();
    form.append("issue_id", String(issueId));
    form.append("file", file);
    form.append("notes", notes);
    return apiFetch<ResolutionResult>("/resolution", { method: "POST", body: form });
  },
};
