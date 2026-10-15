"use client"

import { useState, type FormEvent } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  Bell,
  Command,
  LogOut,
  Menu,
  Search,
  Settings,
} from "lucide-react"
import { useMe, useLogoutMutation } from "@/queries/index"
import { useNotifications, markAllRead } from "@/lib/notifications"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/ui/theme-toggle"
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
import { PAGE_TITLES, initials, timeAgo } from "@/lib/format"

export function Header({ onOpenSidebar }: { onOpenSidebar?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const { data: user } = useMe()
  const logoutMutation = useLogoutMutation()
  const { items, connected } = useNotifications()
  const unread = items.filter((item) => !item.read).length
  const [notificationsOpen, setNotificationsOpen] = useState(false)

  const page = PAGE_TITLES[pathname] ?? { title: "CivicPulse", subtitle: "" }

  function handleSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const q = new FormData(e.currentTarget).get("q") as string
    router.push(`/issues${q ? `?q=${encodeURIComponent(q)}` : ""}`)
  }

  function handleLogout() {
    logoutMutation.mutate()
    router.push("/login")
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-border/70 bg-background/80 px-4 backdrop-blur-xl sm:px-6">
      <button
        onClick={onOpenSidebar}
        className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground lg:hidden"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="min-w-0">
        <h1 className="truncate text-[15px] font-semibold tracking-tight sm:text-base">
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
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/70" />
            <input
              name="q"
              type="search"
              placeholder="Search issues…"
              className="h-9 w-52 rounded-full border border-border/80 bg-card/70 pl-9 pr-8 text-sm shadow-sm outline-none transition-all placeholder:text-muted-foreground/70 focus:w-64 focus:border-ring focus:ring-2 focus:ring-ring/30 lg:w-60"
            />
            <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded border border-border/80 bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground lg:flex">
              <Command className="h-2.5 w-2.5" />
              K
            </kbd>
          </div>
        </form>

        <ThemeToggle />

        <Popover
          open={notificationsOpen}
          onOpenChange={(open) => {
            setNotificationsOpen(open)
            if (open) markAllRead()
          }}
        >
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="relative text-muted-foreground"
              aria-label={
                unread > 0 ? `Notifications (${unread} unread)` : "Notifications"
              }
            >
              <Bell className="h-[18px] w-[18px]" />
              {unread > 0 ? (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-none text-destructive-foreground">
                  {unread > 9 ? "9+" : unread}
                </span>
              ) : (
                connected && (
                  <span className="absolute right-2 top-2 h-2 w-2 rounded-full border-2 border-background bg-gradient-to-r from-emerald-500 to-teal-500" />
                )
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 p-0">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <p className="text-sm font-semibold">Notifications</p>
              <Badge
                variant={connected ? "secondary" : "outline"}
                className="gap-1 text-[10px]"
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    connected ? "bg-emerald-500" : "bg-muted-foreground/60"
                  }`}
                />
                {connected ? "Live" : "Offline"}
              </Badge>
            </div>
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-4 py-8 text-center">
                <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Bell className="h-5 w-5" />
                </div>
                <p className="mt-3 text-sm font-medium">No new notifications</p>
                <p className="text-xs text-muted-foreground">
                  Updates will appear here when issues are reported, reviewed, or
                  removed.
                </p>
              </div>
            ) : (
              <ul className="max-h-80 divide-y divide-border/70 overflow-y-auto">
                {items.map((item) => (
                  <li key={item.id}>
                    <Link
                      href={item.href ?? "/issues"}
                      className="flex gap-3 px-4 py-3 transition-colors hover:bg-muted/60"
                      onClick={() => setNotificationsOpen(false)}
                    >
                      <span
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                          item.read ? "bg-muted-foreground/30" : "bg-primary"
                        }`}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {item.title}
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {item.description}
                        </span>
                        <span className="mt-0.5 block text-[11px] text-muted-foreground/80">
                          {timeAgo(item.createdAt)}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </PopoverContent>
        </Popover>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              className="flex items-center gap-2 rounded-lg px-2"
              aria-label="Account menu"
            >
              <Avatar size="sm" className="ring-1 ring-border">
                <AvatarFallback className="bg-gradient-to-br from-emerald-500 to-teal-500 text-white">
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
                <AvatarFallback className="bg-gradient-to-br from-emerald-500 to-teal-500 text-white">
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
