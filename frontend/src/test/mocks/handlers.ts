import { http, HttpResponse } from "msw"

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export const mockUser = {
  id: 1,
  email: "test@civicpulse.com",
  full_name: "Test User",
  role: "admin",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
}

export const mockIssue = {
  id: 1,
  issue_type: "pothole",
  confidence: 0.92,
  severity: 3,
  status: "reported",
  latitude: 22.3072,
  longitude: 73.1812,
  description: "Large pothole near main road",
  image_url: "/uploads/issues/test.jpg",
  review_required: false,
  ward_id: 1,
  reporter_id: 1,
  created_at: "2024-06-01T00:00:00Z",
  assigned_to: null,
  engineer_name: null,
}

export const mockWard = {
  id: 1,
  name: "Ward 1 - Sayajipura",
  polygon: [],
  center_lat: 22.3072,
  center_lon: 73.1812,
  population: 45000,
}

export const mockEngineer = {
  id: 1,
  user_id: 2,
  ward_id: 1,
  specialization: "road_maintenance",
  current_workload: 3,
  max_workload: 10,
  is_available: true,
  avg_resolution_hours: 48.5,
}

export const mockStats = {
  total_issues: 156,
  by_status: { reported: 20, assigned: 15, in_progress: 10, resolved: 100, verified: 11 },
  by_type: { pothole: 80, garbage: 40, streetlight: 20, water_logging: 16 },
  by_ward: [{ ward: "Sayajipura", count: 30 }],
  recent_count: 12,
}

export const handlers = [
  http.get(`${API}/api/v1/auth/me`, () => HttpResponse.json(mockUser)),

  http.post(`${API}/api/v1/auth/login`, () =>
    HttpResponse.json({ access_token: "mock-token", refresh_token: "mock-refresh", token_type: "bearer" })
  ),

  http.post(`${API}/api/v1/auth/register`, () => HttpResponse.json(mockUser)),

  http.post(`${API}/api/v1/auth/refresh`, () =>
    HttpResponse.json({ access_token: "mock-refreshed-token", token_type: "bearer" })
  ),

  http.get(`${API}/api/v1/issues`, () =>
    HttpResponse.json({ items: [mockIssue], total: 1 })
  ),

  http.get(`${API}/api/v1/issues/:id`, () => HttpResponse.json(mockIssue)),

  http.post(`${API}/api/v1/issues/upload`, () => HttpResponse.json(mockIssue)),

  http.patch(`${API}/api/v1/issues/:id/status`, () =>
    HttpResponse.json({ ...mockIssue, status: "assigned" })
  ),

  http.get(`${API}/api/v1/wards`, () => HttpResponse.json([mockWard])),

  http.get(`${API}/api/v1/engineers`, () => HttpResponse.json([mockEngineer])),

  http.get(`${API}/api/v1/dashboard/stats`, () => HttpResponse.json(mockStats)),

  http.get(`${API}/api/v1/dashboard/heatmap`, () =>
    HttpResponse.json([{ lat: 22.3072, lng: 73.1812, type: "pothole", severity: 3, status: "reported" }])
  ),
]
