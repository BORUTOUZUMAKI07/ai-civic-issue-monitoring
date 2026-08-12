import { clearTokenCookies, setTokenCookie } from "@/lib/token-cookie";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

async function tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem("access_token", data.access_token);
    if (data.refresh_token) localStorage.setItem("refresh_token", data.refresh_token);
    return true;
  } catch {
    return false;
  }
}

function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  clearTokenCookies();
}

let refreshPromise: Promise<boolean> | null = null;

async function handleUnauthorized() {
  if (!refreshPromise) {
    refreshPromise = tryRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  const refreshed = await refreshPromise;
  if (refreshed) return true;
  clearTokens();
  if (typeof window !== "undefined") window.location.href = "/login";
  return false;
}

async function rawFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (
    res.status === 401 &&
    !path.startsWith("/api/v1/auth/login") &&
    !path.startsWith("/api/v1/auth/register") &&
    !path.startsWith("/api/v1/auth/refresh")
  ) {
    const recovered = await handleUnauthorized();
    if (recovered) {
      const newToken = getToken();
      headers["Authorization"] = `Bearer ${newToken}`;
      const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (retry.ok) return retry.json();
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

export async function apiFetchBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    const recovered = await handleUnauthorized();
    if (recovered) {
      const newToken = getToken();
      headers["Authorization"] = `Bearer ${newToken}`;
      const retry = await fetch(`${API_BASE}${path}`, { ...options, headers });
      if (retry.ok) return retry.blob();
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
}

export interface Token {
  access_token: string;
  refresh_token: string;
  token_type: string;
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
    apiFetch<Token>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, full_name: string, role: string = "field_worker") =>
    apiFetch<User>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name, role }),
    }),
  me: () => apiFetch<User>("/api/v1/auth/me"),
  refresh: (refresh_token: string) =>
    apiFetch<Token>("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
    }),
};

export const issues = {
  list: (params?: { skip?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.skip) q.set("skip", String(params.skip));
    if (params?.limit) q.set("limit", String(params.limit));
    return apiFetch<{ items: Issue[]; total: number }>(`/api/v1/issues?${q}`);
  },
  get: (id: number) => apiFetch<Issue>(`/api/v1/issues/${id}`),
  upload: (file: File, latitude: number, longitude: number, description: string = "") => {
    const form = new FormData();
    form.append("file", file);
    form.append("latitude", String(latitude));
    form.append("longitude", String(longitude));
    form.append("description", description);
    return apiFetch<Issue>("/api/v1/issues/upload", {
      method: "POST",
      body: form,
      headers: {},
    });
  },
  updateStatus: (id: number, status: string) =>
    apiFetch<Issue>(`/api/v1/issues/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
};

export const wards = {
  list: () => apiFetch<Ward[]>("/api/v1/wards"),
};

export const engineers = {
  list: () => apiFetch<Engineer[]>("/api/v1/engineers"),
};

export const dashboard = {
  stats: () => apiFetch<DashboardStats>("/api/v1/dashboard/stats"),
  heatmap: () => apiFetch<HeatmapPoint[]>("/api/v1/dashboard/heatmap"),
};

export const resolution = {
  resolve: (issue_id: number, file: File, notes: string = "") => {
    const form = new FormData();
    form.append("issue_id", String(issue_id));
    form.append("file", file);
    form.append("notes", notes);
    return apiFetch<{ id: number; issue_id: number; status: string; message: string }>(
      "/api/v1/resolution",
      { method: "POST", body: form, headers: {} }
    );
  },
};
