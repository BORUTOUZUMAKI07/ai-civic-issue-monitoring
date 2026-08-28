"use client"

import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { auth } from "@/lib/api"
import { useAuthStore } from "@/store/auth"

export function AuthPrefetcher() {
  const qc = useQueryClient()
  const setUser = useAuthStore((s) => s.setUser)

  useEffect(() => {
    qc.fetchQuery({
      queryKey: ["me"],
      queryFn: () => auth.me(),
      staleTime: 5 * 60 * 1000,
    }).then((user) => {
      if (user) setUser(user)
    }).catch(() => {})
  }, [qc, setUser])

  return null
}
