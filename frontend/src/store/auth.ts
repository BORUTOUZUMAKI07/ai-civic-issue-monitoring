import { create } from "zustand"
import { clearTokenCookies } from "@/lib/token-cookie"
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
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    clearTokenCookies()
    set({ user: null })
  },
}))
