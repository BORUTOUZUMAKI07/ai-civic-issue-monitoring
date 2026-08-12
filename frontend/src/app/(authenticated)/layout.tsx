import { Suspense } from "react"
import { AppShell } from "@/components/layout/app-shell"
import { AuthPrefetcher } from "@/lib/auth-prefetcher"

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <AuthPrefetcher />
      <Suspense fallback={null}>{children}</Suspense>
    </AppShell>
  )
}
