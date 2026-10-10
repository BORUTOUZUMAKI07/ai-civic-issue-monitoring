import { QueryClient } from "@tanstack/react-query";

/**
 * The app's single QueryClient.
 *
 * It lives here rather than inside `Providers`' `useState` so that code outside
 * the React tree — most importantly `useAuthStore().logout()` — can reach it.
 * Logging out has to drop every cached query, not just reset the auth store:
 * `me`, issue lists, dashboard stats and the admin/user tables are all keyed by
 * nothing but their query key, so leaving them cached hands the next account
 * that signs in on this browser a render of the previous user's data.
 *
 * A module-level singleton is also stable across remounts of `Providers`, which
 * is what `useState` was there to guarantee.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 10 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
