"use client"

import { useState, useMemo } from "react"
import { useIssues } from "@/queries/index"

export function useIssueFilters() {
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState<string>("")

  const { data, isLoading, error } = useIssues({ limit: 100 })

  const issues = data?.items || []

  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      if (statusFilter !== "all" && issue.status !== statusFilter) return false
      if (typeFilter !== "all" && issue.issue_type !== typeFilter) return false
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        return (
          issue.description?.toLowerCase().includes(q) ||
          issue.issue_type.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [issues, statusFilter, typeFilter, searchQuery])

  return {
    issues: filteredIssues,
    totalCount: filteredIssues.length,
    statusFilter,
    setStatusFilter,
    typeFilter,
    setTypeFilter,
    searchQuery,
    setSearchQuery,
    isLoading,
    error,
  }
}
