"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth";
import { useMe } from "@/queries/index";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { initials } from "@/lib/format";
import {
  LayoutDashboard,
  AlertTriangle,
  Map,
  Users,
  Settings,
  LogOut,
  X,
  Landmark,
  ShieldCheck,
} from "lucide-react";

const navSections = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/issues", label: "Issues", icon: AlertTriangle },
      { href: "/map", label: "Map", icon: Map },
    ],
  },
  {
    label: "Workspace",
    items: [
      { href: "/engineers", label: "Engineers", icon: Users },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

interface SidebarProps {
  open?: boolean;
  onClose?: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps = {}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);
  const { data: user } = useMe();

  const isOpen = open ?? internalOpen;
  const close = onClose ?? (() => setInternalOpen(false));

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden"
          onClick={close}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-border/80 bg-card transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 lg:shrink-0",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-border/70 px-5">
          <Link href="/dashboard" className="flex items-center gap-2.5" onClick={close}>
            <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-violet-500 to-indigo-600 text-white shadow-glow-primary">
              <Landmark className="h-5 w-5" />
              <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-card bg-emerald-500" />
            </div>
            <div>
              <h2 className="text-[15px] font-semibold leading-tight tracking-tight">
                CivicPulse
              </h2>
              <p className="text-[11px] leading-tight text-muted-foreground">
                Vadodara Municipal
              </p>
            </div>
          </Link>
          <button
            onClick={close}
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted lg:hidden"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
          {navSections.map((section) => (
            <div key={section.label}>
              <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
                {section.label}
              </p>
              <div className="space-y-1">
                {section.items.map((item) => {
                  const isActive =
                    pathname === item.href || pathname.startsWith(item.href + "/");
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={close}
                      className={cn(
                        "group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-200",
                        isActive
                          ? "bg-primary/[0.08] text-primary"
                          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
                      )}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-gradient-to-b from-indigo-500 to-violet-500" />
                      )}
                      <span
                        className={cn(
                          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors",
                          isActive
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "bg-muted/70 text-muted-foreground group-hover:bg-muted group-hover:text-foreground"
                        )}
                      >
                        <item.icon className="h-4 w-4" />
                      </span>
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="border-t border-border/70 p-3">
          <div className="flex items-center gap-3 rounded-xl px-2.5 py-2.5">
            <Avatar size="sm">
              <AvatarFallback className="bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
                {initials(user?.full_name ?? "User")}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium leading-tight">
                {user?.full_name ?? "Account"}
              </p>
              <p className="flex items-center gap-1 truncate text-xs capitalize text-muted-foreground">
                <ShieldCheck className="h-3 w-3 shrink-0" />
                {user?.role.replace("_", " ") ?? ""}
              </p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="mt-1 flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/70">
              <LogOut className="h-4 w-4" />
            </span>
            Sign Out
          </button>
        </div>
      </aside>
    </>
  );
}
