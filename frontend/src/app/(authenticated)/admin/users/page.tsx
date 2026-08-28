"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/auth";
import { useAdminUsers, useUpdateUserRoleMutation } from "@/queries/index";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Inbox, Search, ShieldCheck, UserCheck, UserX } from "lucide-react";
import { formatDate } from "@/lib/format";

const ROLE_OPTIONS = ["admin", "engineer", "field_worker", "viewer"] as const;

const ROLE_STYLES: Record<string, string> = {
  super_admin: "border-amber-200 bg-amber-50 text-amber-700",
  admin: "border-purple-200 bg-purple-50 text-purple-700",
  engineer: "border-blue-200 bg-blue-50 text-blue-700",
  field_worker: "border-emerald-200 bg-emerald-50 text-emerald-700",
  viewer: "border-slate-200 bg-slate-50 text-slate-700",
};

function UserRow({
  user,
  currentUserId,
  currentUserRole,
  onRoleChange,
  processing,
}: {
  user: { id: number; email: string; full_name: string; role: string; is_active: boolean; created_at: string };
  currentUserId: number;
  currentUserRole: string;
  onRoleChange: (userId: number, role: string) => void;
  processing: boolean;
}) {
  const isSelf = user.id === currentUserId;
  const isSuperAdmin = user.role === "super_admin";
  const canChangeRole = !isSelf && !isSuperAdmin;
  const availableRoles = currentUserRole === "super_admin"
    ? [...ROLE_OPTIONS]
    : ROLE_OPTIONS.filter((r) => r !== "admin");

  return (
    <div className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-muted/40">
      {/* Avatar */}
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-sm font-semibold text-white">
        {user.full_name
          .split(" ")
          .map((n) => n[0])
          .join("")
          .slice(0, 2)
          .toUpperCase()}
      </div>

      {/* Info */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{user.full_name}</span>
          <Badge variant="outline" className={ROLE_STYLES[user.role] ?? "border-slate-200 bg-slate-50 text-slate-700"}>
            {user.role.replace("_", " ")}
          </Badge>
          {!user.is_active && (
            <Badge variant="outline" className="border-red-200 bg-red-50 text-red-700">
              Inactive
            </Badge>
          )}
          {isSelf && (
            <Badge variant="outline" className="border-indigo-200 bg-indigo-50 text-indigo-700">
              You
            </Badge>
          )}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{user.email}</span>
          <span>Joined {formatDate(user.created_at)}</span>
        </div>
      </div>

      {/* Role change */}
      {canChangeRole && (
        <div className="shrink-0">
          <Select
            defaultValue={user.role}
            onValueChange={(v) => onRoleChange(user.id, v)}
            disabled={processing}
          >
            <SelectTrigger className="h-8 w-[140px] text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {availableRoles.map((r) => (
                <SelectItem key={r} value={r} className="text-xs">
                  {r.replace("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      {isSuperAdmin && !isSelf && (
        <span className="text-xs text-muted-foreground italic">Protected</span>
      )}
    </div>
  );
}

export default function AdminUsersPage() {
  const currentUser = useAuthStore((s) => s.user);
  const router = useRouter();
  if (currentUser && currentUser.role !== "admin" && currentUser.role !== "super_admin") {
    router.replace("/dashboard");
    return null;
  }
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("");
  const params = {
    limit: 50,
    ...(search && { search }),
    ...(roleFilter && { role: roleFilter }),
  };
  const { data, isLoading, refetch } = useAdminUsers(params);
  const roleMutation = useUpdateUserRoleMutation();
  const [processingId, setProcessingId] = useState<number | null>(null);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  const handleRoleChange = async (userId: number, role: string) => {
    setProcessingId(userId);
    try {
      await roleMutation.mutateAsync({ userId, role });
      toast.success(`Role updated to ${role.replace("_", " ")}`);
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to update role");
    } finally {
      setProcessingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header + summary */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {total} registered {total === 1 ? "user" : "users"}
        </p>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-4">
        {(["admin", "engineer", "field_worker", "viewer"] as const).map((r) => {
          const count = items.filter((u) => u.role === r).length;
          const Icon = r === "admin" ? ShieldCheck : r === "engineer" ? UserCheck : UserX;
          return (
            <Card key={r} className="flex items-center gap-3 px-4 py-3">
              <div className={`flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br ${
                r === "admin" ? "from-purple-500 to-indigo-500" :
                r === "engineer" ? "from-blue-500 to-cyan-500" :
                r === "field_worker" ? "from-emerald-500 to-teal-500" :
                "from-slate-400 to-slate-500"
              } text-white shadow-sm`}>
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="text-lg font-semibold leading-tight">{count}</p>
                <p className="text-xs capitalize text-muted-foreground">{r.replace("_", " ")}</p>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 h-9 text-sm"
          />
        </div>
        <Select value={roleFilter || "all"} onValueChange={(v) => setRoleFilter(v === "all" ? "" : v)}>
          <SelectTrigger className="h-9 w-[140px] text-sm">
            <SelectValue placeholder="All roles" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all" className="text-sm">All roles</SelectItem>
            {ROLE_OPTIONS.map((r) => (
              <SelectItem key={r} value={r} className="text-sm">
                {r.replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card>
        {isLoading ? (
          <div className="space-y-1 p-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-4 py-4">
                <Skeleton className="h-10 w-10 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-1/4" />
                  <Skeleton className="h-3 w-1/3" />
                </div>
                <Skeleton className="h-8 w-[140px] rounded" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <Inbox className="h-7 w-7 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-base font-semibold">No users found</h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {search || roleFilter ? "Try adjusting your filters." : "No users have registered yet."}
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {items.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                currentUserId={currentUser?.id ?? 0}
                currentUserRole={currentUser?.role ?? ""}
                onRoleChange={handleRoleChange}
                processing={processingId === user.id}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
