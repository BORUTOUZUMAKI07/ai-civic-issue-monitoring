"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { auth, issues, wards, engineers, dashboard, admin } from "@/lib/api";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => auth.me(),
    retry: false,
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
  });
}

export function useEngineers() {
  return useQuery({
    queryKey: ["engineers"],
    queryFn: () => engineers.list(),
  });
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => dashboard.stats(),
  });
}

export function useHeatmapData() {
  return useQuery({
    queryKey: ["heatmap"],
    queryFn: () => dashboard.heatmap(),
  });
}
