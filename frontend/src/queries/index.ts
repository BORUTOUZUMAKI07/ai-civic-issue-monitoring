"use client";

import { useQuery, useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { auth, issues, wards, engineers, dashboard, admin, resolution } from "@/lib/api";
import { clearNotifications } from "@/lib/notifications";

// Any mutation that changes issue data must refresh the list, the affected
// detail, and the aggregates derived from them. Without this the dashboard and
// heatmap keep serving their cached copy for the full 30s stale window after a
// report, review or (re)assignment.
function invalidateIssueData(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: ["issues"] });
  qc.invalidateQueries({ queryKey: ["issue"] });
  qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
  qc.invalidateQueries({ queryKey: ["heatmap"] });
}

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => auth.me(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLogoutMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      // Drop every cached query *before* the session goes away. `me`, issue
      // lists, dashboard stats and the admin tables are keyed by their query
      // key alone, so leaving them cached means the next account to sign in
      // on this browser first renders the previous user's data — `["me"]`
      // included, at a 5-minute staleTime, which briefly shows the wrong
      // identity.
      qc.clear();
      clearNotifications();
      await auth.logout().catch(() => {});
    },
  });
}

export function useRegisterMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      email,
      password,
      full_name,
      role,
    }: {
      email: string;
      password: string;
      full_name: string;
      role: string;
    }) => auth.register(email, password, full_name, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useIssues(params?: {
  skip?: number;
  limit?: number;
  status?: string;
  issue_type?: string;
  severity?: number;
  ward_id?: number;
  search?: string;
  sort?: string;
  order?: string;
}) {
  return useQuery({
    queryKey: ["issues", params],
    queryFn: () => issues.list(params),
  });
}

export function useIssue(id: number) {
  return useQuery({
    queryKey: ["issue", id],
    queryFn: () => issues.get(id),
    enabled: !!id,
  });
}

export function useUploadIssueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      latitude,
      longitude,
      description,
      force_submit,
      idempotencyKey,
    }: {
      file: File;
      latitude: number;
      longitude: number;
      description: string;
      force_submit?: boolean;
      idempotencyKey?: string;
    }) => issues.upload(file, latitude, longitude, description, force_submit ?? false, idempotencyKey),
    onSuccess: () => invalidateIssueData(qc),
  });
}

export function useAdminUsers(params?: { skip?: number; limit?: number; search?: string; role?: string; sort?: string; order?: string }) {
  return useQuery({
    queryKey: ["admin-users", params],
    queryFn: () => admin.listUsers(params),
  });
}

export function useUpdateUserRoleMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      admin.updateUserRole(userId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });
}

export function useReviewQueue(params?: {
  skip?: number;
  limit?: number;
  issue_type?: string;
  severity?: number;
  sort?: string;
  order?: string;
}) {
  return useQuery({
    queryKey: ["review-queue", params],
    queryFn: () => admin.reviewQueue(params),
  });
}

export function useReviewIssueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action, newType }: { id: number; action: string; newType?: string }) =>
      admin.reviewIssue(id, action, newType),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-queue"] });
      invalidateIssueData(qc);
    },
  });
}

export function useWards() {
  return useQuery({
    queryKey: ["wards"],
    queryFn: () => wards.list(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useEngineers() {
  return useQuery({
    queryKey: ["engineers"],
    queryFn: () => engineers.list(),
    staleTime: 2 * 60 * 1000,
  });
}

export function useEngineersPaged(params?: {
  skip?: number;
  limit?: number;
  specialization?: string;
  ward_id?: number;
  available?: boolean;
  sort?: string;
  order?: string;
}) {
  return useQuery({
    queryKey: ["engineers-paged", params],
    queryFn: () => engineers.listPaged(params),
  });
}

export function useMyEngineerProfile() {
  return useQuery({
    queryKey: ["engineer-me"],
    queryFn: () => engineers.myProfile(),
    staleTime: 2 * 60 * 1000,
    retry: false,
  });
}

export function useCreateEngineerMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { user_id: number; ward_id: number; specialization?: string; max_workload?: number }) =>
      engineers.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["engineers"] }),
  });
}

export function useAssignIssueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, engineerId }: { issueId: number; engineerId: number }) =>
      issues.assign(issueId, engineerId),
    onSuccess: () => {
      invalidateIssueData(qc);
    },
  });
}

export function useReassignIssueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, engineerId }: { issueId: number; engineerId: number }) =>
      issues.reassign(issueId, engineerId),
    onSuccess: () => {
      invalidateIssueData(qc);
    },
  });
}

export function useResolveIssueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, file, notes }: { issueId: number; file: File; notes?: string }) =>
      resolution.resolve(issueId, file, notes ?? ""),
    onSuccess: () => {
      invalidateIssueData(qc);
    },
  });
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => dashboard.stats(),
    staleTime: 30_000,
  });
}

export function useHeatmapData() {
  return useQuery({
    queryKey: ["heatmap"],
    queryFn: () => dashboard.heatmap(),
    staleTime: 30_000,
  });
}

/**
 * Public, unauthenticated aggregate counters for the landing page. Failures
 * are swallowed by the caller (the landing page falls back to hiding the
 * stat block), so a landing-page visit never depends on the API being up.
 */
export function usePublicStats() {
  return useQuery({
    queryKey: ["public-stats"],
    queryFn: () => dashboard.publicStats(),
    staleTime: 60_000,
    retry: false,
  });
}
