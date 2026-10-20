import { AppShell } from "@/components/layout/app-shell"

/**
 * The authenticated shell.
 *
 * This used to wrap `{children}` in an extra `<Suspense fallback={null}>`. That
 * boundary was a leftover: it originally wrapped `<Sidebar />`, which needed one
 * because it rendered client hooks, and a later refactor moved it onto the page
 * content where it served no purpose — every route in this segment already
 * streams behind its own boundary from the `loading.tsx` files.
 *
 * A `fallback={null}` boundary around the whole page is the wrong default: it
 * makes the page render as "nothing" until the client takes over, which is a
 * worse first paint than the route's own skeleton and hides any streamed content
 * if hydration is slow. Let the route-level boundary own the loading state.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
