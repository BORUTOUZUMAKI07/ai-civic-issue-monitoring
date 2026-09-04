const API_BASE = "/api/proxy";

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
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
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

export async function apiFetchBlob<T>(path: string, options: RequestInit = {}): Promise<Blob> {
  const headers: Record<string, string> = {
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
      if (retry.ok) return retry.blob();
    }
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Session expired. Please login again.");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    const msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail || body);
    throw new Error(msg || "Request failed");
  }

  return res.blob();
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

export interface RejectedUpload {
  id: string;
  image_url: string;
  vision_label: string;
  vision_confidence: number;
  description: string;
  action_taken: string;
  created_at: string;
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
  twofaRegenerateRecovery: (code: string) =>
    apiFetch<{ recovery_codes: string[] }>("/auth/2fa/recovery-codes", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
};

export const issues = {
  list: (params?: { skip?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    return apiFetch<{ items: Issue[]; total: number }>(`/issues?${q}`);
  },
  get: (id: number) => apiFetch<Issue>(`/issues/${id}`),
  upload: (
    file: File,
    latitude: number,
    longitude: number,
    description: string = "",
    force_submit: boolean = false
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
      headers: {},
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
  reviewQueue: (params?: { skip?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    return apiFetch<{ items: Issue[]; total: number }>(`/admin/review-queue?${q}`);
  },
  reviewIssue: (id: number, action: string, newType?: string) =>
    apiFetch<{ detail: string; issue_id: number; issue_type: string }>(
      `/admin/review/${id}`,
      { method: "POST", body: JSON.stringify({ action, new_type: newType }) }
    ),
  listUsers: (params?: { skip?: number; limit?: number; search?: string; role?: string }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.search) q.set("search", params.search);
    if (params?.role) q.set("role", params.role);
    return apiFetch<{ items: User[]; total: number }>(`/admin/users?${q}`);
  },
  updateUserRole: (userId: number, role: string) =>
    apiFetch<{ detail: string; user_id: number; role: string }>(
      `/admin/users/${userId}/role`,
      { method: "POST", body: JSON.stringify({ action: "change_type", new_type: role }) }
    ),
  rejectedUploads: (params?: { skip?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    return apiFetch<{ items: RejectedUpload[]; total: number }>(
      `/admin/rejected-uploads?${q}`
    );
  },
};

export const wards = {
  list: () => apiFetch<Ward[]>("/wards"),
};

export const engineers = {
  list: () => apiFetch<Engineer[]>("/engineers"),
  create: (data: { user_id: number; ward_id: number; specialization?: string; max_workload?: number }) =>
    apiFetch<Engineer>("/engineers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  myAssignments: () =>
    apiFetch<{ items: Array<{
      assignment_id: number;
      status: string;
      assigned_at: string;
      sla_deadline: string;
      issue_id: number;
      issue_type: string;
      severity: number;
      issue_status: string;
      latitude: number;
      longitude: number;
      description: string | null;
      image_url: string;
      ward_id: number;
      created_at: string;
    }>; total: number }>("/engineers/me/assignments"),
};

export const dashboard = {
  stats: () => apiFetch<DashboardStats>("/dashboard/stats"),
  heatmap: () => apiFetch<HeatmapPoint[]>("/dashboard/heatmap"),
};

export const resolution = {
  resolve: (issue_id: number, file: File, notes: string = "") => {
    const form = new FormData();
    form.append("issue_id", String(issue_id));
    form.append("file", file);
    form.append("notes", notes);
    return apiFetch<{ id: number; issue_id: number; status: string; message: string }>(
      "/resolution",
      { method: "POST", body: form, headers: {} }
    );
  },
};
