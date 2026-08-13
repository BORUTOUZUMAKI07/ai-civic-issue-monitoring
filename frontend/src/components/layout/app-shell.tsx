"use client"

import { useState, type ReactNode } from "react"
import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"

export function AppShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onOpenSidebar={() => setSidebarOpen(true)} />
        <main className="relative flex-1 overflow-y-auto">
          {/* Decorative ambient glows */}
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 top-0 h-72 overflow-hidden"
          >
            <div className="absolute -top-24 right-[-10%] h-72 w-72 rounded-full bg-primary/10 blur-3xl dark:bg-primary/[0.14]" />
            <div className="absolute -top-16 left-1/3 h-56 w-56 rounded-full bg-violet-500/10 blur-3xl dark:bg-violet-500/[0.12]" />
          </div>
          <div className="relative mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
