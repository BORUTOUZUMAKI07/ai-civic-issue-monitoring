import { Suspense } from "react"
import { AppShell } from "@/components/layout/app-shell"

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell>
      <Suspense fallback={null}>{children}</Suspense>
    </AppShell>
  )
}
