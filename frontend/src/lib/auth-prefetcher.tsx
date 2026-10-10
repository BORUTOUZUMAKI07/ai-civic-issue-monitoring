"use client"

import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { auth } from "@/lib/api"
import { useAuthStore } from "@/store/auth"

export function AuthPrefetcher() {
  const qc = useQueryClient()
  const setUser = useAuthStore((s) => s.setUser)
  const setLoading = useAuthStore((s) => s.setLoading)

  useEffect(() => {
    qc.fetchQuery({
      queryKey: ["me"],
      queryFn: () => auth.me(),
      staleTime: 5 * 60 * 1000,
    }).then((user) => {
      if (user) setUser(user)
    }).catch(() => {
      // A failed `me` (401 for a signed-out visitor, network error, backend
      // down) must still release `isLoading`. It starts `true` and is only
      // ever cleared by `setUser`, so an unauthenticated first visit left the
      // store latched on "loading" forever — any component gating on it would
      // spin indefinitely instead of falling through to the login screen.
      setLoading(false)
    })
  }, [qc, setUser, setLoading])

  return null
}
