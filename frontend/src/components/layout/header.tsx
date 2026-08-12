"use client"

import { useEffect, useRef, useState, type FormEvent } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { Bell, ChevronDown, LogOut, Menu, Search, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { useMe } from "@/queries/index"
import { useAuthStore } from "@/store/auth"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { PAGE_TITLES, initials } from "@/lib/format"

function useOutsideClick(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [onClose])
  return ref
}

export function Header({ onOpenSidebar }: { onOpenSidebar?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const { data: user } = useMe()
  const logout = useAuthStore((s) => s.logout)

  const [notifOpen, setNotifOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)
  const notifRef = useOutsideClick(() => setNotifOpen(false))
  const userRef = useOutsideClick(() => setUserOpen(false))

  const page = PAGE_TITLES[pathname] ?? { title: "", subtitle: "" }

  function handleSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const q = new FormData(e.currentTarget).get("q") as string
    router.push(`/issues${q ? `?q=${encodeURIComponent(q)}` : ""}`)
  }

  function handleLogout() {
    logout()
    router.push("/login")
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur sm:px-6">
      <button
        onClick={onOpenSidebar}
        className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground lg:hidden"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="min-w-0">
        <h1 className="truncate text-base font-semibold tracking-tight sm:text-lg">
          {page.title}
        </h1>
        {page.subtitle && (
          <p className="hidden truncate text-xs text-muted-foreground sm:block">
            {page.subtitle}
          </p>
        )}
      </div>

      <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
        <form
          onSubmit={handleSearch}
          className="hidden items-center md:flex"
          role="search"
        >
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              name="q"
              type="search"
              placeholder="Search issues…"
              className="h-9 w-52 rounded-lg border border-input bg-card pl-9 pr-3 text-sm outline-none transition-colors focus:border-ring lg:w-64"
            />
          </div>
        </form>

        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setNotifOpen((v) => !v)}
            className="relative rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-destructive" />
          </button>
          {notifOpen && (
            <div className="absolute right-0 mt-2 w-72 rounded-xl border bg-card p-3 shadow-lg">
              <p className="text-sm font-semibold">Notifications</p>
              <p className="mt-2 text-xs text-muted-foreground">
                No new notifications. You&apos;re all caught up.
              </p>
            </div>
          )}
        </div>

        <div className="relative" ref={userRef}>
          <button
            onClick={() => setUserOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg p-1.5 pr-2 hover:bg-muted"
            aria-label="Account menu"
          >
            <Avatar size="sm">
              <AvatarFallback className="bg-primary text-primary-foreground">
                {initials(user?.full_name ?? "User")}
              </AvatarFallback>
            </Avatar>
            <span className="hidden text-left sm:block">
              <span className="block max-w-[9rem] truncate text-sm font-medium leading-tight">
                {user?.full_name ?? "Account"}
              </span>
              <span className="block text-xs capitalize text-muted-foreground">
                {user?.role.replace("_", " ") ?? ""}
              </span>
            </span>
            <ChevronDown className="hidden h-4 w-4 text-muted-foreground sm:block" />
          </button>
          {userOpen && (
            <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-xl border bg-card shadow-lg">
              <div className="border-b px-3 py-3">
                <p className="truncate text-sm font-medium">{user?.full_name}</p>
                <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
              </div>
              <div className="p-1">
                <Link
                  href="/settings"
                  onClick={() => setUserOpen(false)}
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </Link>
                <button
                  onClick={handleLogout}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
