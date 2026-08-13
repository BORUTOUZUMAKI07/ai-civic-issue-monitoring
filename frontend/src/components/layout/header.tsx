"use client"

import type { FormEvent } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  Bell,
  LogOut,
  Menu,
  Search,
  Settings,
  ShieldCheck,
} from "lucide-react"
import { useMe } from "@/queries/index"
import { useAuthStore } from "@/store/auth"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { Badge } from "@/components/ui/badge"
import { PAGE_TITLES, initials } from "@/lib/format"

export function Header({ onOpenSidebar }: { onOpenSidebar?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const { data: user } = useMe()
  const logout = useAuthStore((s) => s.logout)

  const page = PAGE_TITLES[pathname] ?? { title: "CivicPulse", subtitle: "" }

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
        <form onSubmit={handleSearch} className="hidden items-center md:flex" role="search">
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

        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="relative text-muted-foreground"
              aria-label="Notifications"
            >
              <Bell className="h-5 w-5" />
              <span className="absolute right-2 top-2 h-2 w-2 rounded-full border-2 border-background bg-primary" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 p-0">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <p className="text-sm font-semibold">Notifications</p>
              <Badge variant="secondary" className="text-[10px]">
                Live
              </Badge>
            </div>
            <div className="flex items-start gap-3 px-4 py-4">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-50 text-blue-600">
                <ShieldCheck className="h-4 w-4" />
              </div>
              <div className="space-y-0.5">
                <p className="text-sm font-medium">AI classification running</p>
                <p className="text-xs text-muted-foreground">
                  New reports are classified automatically by the model.
                </p>
              </div>
            </div>
            <div className="border-t bg-muted/40 px-4 py-2.5 text-center text-xs text-muted-foreground">
              You&apos;re all caught up
            </div>
          </PopoverContent>
        </Popover>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="flex items-center gap-2 rounded-lg px-2"
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
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel className="flex items-center gap-3 font-normal">
              <Avatar size="sm">
                <AvatarFallback className="bg-primary text-primary-foreground">
                  {initials(user?.full_name ?? "User")}
                </AvatarFallback>
              </Avatar>
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">
                  {user?.full_name}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {user?.email}
                </span>
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem asChild>
                <Link href="/settings" className="cursor-pointer">
                  <Settings className="mr-2 h-4 w-4" />
                  Settings
                </Link>
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer text-destructive focus:text-destructive"
              onSelect={handleLogout}
            >
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
