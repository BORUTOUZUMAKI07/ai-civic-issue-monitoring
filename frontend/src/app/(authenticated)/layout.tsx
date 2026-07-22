import { Suspense } from "react"
import { Sidebar } from "@/components/layout/sidebar"
import { AuthPrefetcher } from "@/lib/auth-prefetcher"

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <AuthPrefetcher />
      <Suspense fallback={null}>
        <Sidebar />
      </Suspense>
      <main className="flex-1 overflow-auto pt-14 md:pt-0">
        {children}
      </main>
    </div>
  )
}
