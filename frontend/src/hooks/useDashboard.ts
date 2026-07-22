"use client"

import { useMemo } from "react"
import { useMe, useIssues, useWards, useEngineers, useDashboardStats } from "@/queries/index"

export function useDashboard() {
  const { data: user, isLoading: userLoading } = useMe()
  const { data: stats, isLoading: statsLoading } = useDashboardStats()
  const { data: issuesData, isLoading: issuesLoading } = useIssues({ limit: 50 })
  const { data: wards = [], isLoading: wardsLoading } = useWards()
  const { data: engineers = [], isLoading: engineersLoading } = useEngineers()

  const issues = issuesData?.items || []
  const totalCount = issuesData?.total || 0

  const isLoading = userLoading || statsLoading || issuesLoading || wardsLoading || engineersLoading

  const recentIssues = useMemo(() => issues.slice(0, 10), [issues])

  const issuesByStatus = useMemo(() => {
    const grouped: Record<string, number> = {}
    issues.forEach((issue) => {
      grouped[issue.status] = (grouped[issue.status] || 0) + 1
    })
    return grouped
  }, [issues])

  return {
    user,
    stats,
    issues,
    totalCount,
    wards,
    engineers,
    recentIssues,
    issuesByStatus,
    isLoading,
  }
}
