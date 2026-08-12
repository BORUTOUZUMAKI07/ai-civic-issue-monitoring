"use client"

import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { auth } from "@/lib/api"

export function AuthPrefetcher() {
  const qc = useQueryClient()

  useEffect(() => {
    qc.prefetchQuery({
      queryKey: ["me"],
      queryFn: () => auth.me(),
      staleTime: 5 * 60 * 1000,
    })
  }, [qc])

  return null
}
