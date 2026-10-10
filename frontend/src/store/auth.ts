import { create } from "zustand"
import { auth } from "@/lib/api"
import { queryClient } from "@/lib/query-client"
import type { User } from "@/lib/api"

interface AuthState {
  user: User | null
  isLoading: boolean
  setUser: (user: User | null) => void
  setLoading: (loading: boolean) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  setUser: (user) => set({ user, isLoading: false }),
  setLoading: (isLoading) => set({ isLoading }),
  logout: () => {
    // Drop every cached query *before* the session goes away. `me`, issue
    // lists, dashboard stats and the admin tables are keyed by their query key
    // alone, so leaving them cached means the next account to sign in on this
    // browser first renders the previous user's data — `["me"]` included, at a
    // 5-minute staleTime, which briefly shows the wrong identity.
    queryClient.clear()
    auth.logout().catch(() => {})
    set({ user: null, isLoading: false })
  },
}))
