"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { auth, issues, wards, engineers, dashboard, admin } from "@/lib/api";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => auth.me(),
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

export function useLoginMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      auth.login(email, password),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
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

export function useIssues(params?: { skip?: number; limit?: number }) {
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
    }: {
      file: File;
      latitude: number;
      longitude: number;
      description: string;
      force_submit?: boolean;
    }) => issues.upload(file, latitude, longitude, description, force_submit ?? false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues"] }),
  });
}

export function useAdminUsers(params?: { skip?: number; limit?: number; search?: string; role?: string }) {
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

export function useReviewQueue(params?: { skip?: number; limit?: number }) {
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
      qc.invalidateQueries({ queryKey: ["issues"] });
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
      qc.invalidateQueries({ queryKey: ["issues"] });
    },
  });
}

export function useReassignIssueMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, engineerId }: { issueId: number; engineerId: number }) =>
      issues.reassign(issueId, engineerId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["issues"] });
    },
  });
}

export function useMyAssignments() {
  return useQuery({
    queryKey: ["my-assignments"],
    queryFn: () => engineers.myAssignments(),
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
