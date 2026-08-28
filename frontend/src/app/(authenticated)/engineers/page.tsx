"use client";

import { useState } from "react";
import { useEngineers, useWards, useAdminUsers, useCreateEngineerMutation } from "@/queries/index";
import { useAuthStore } from "@/store/auth";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Clock,
  Construction,
  Droplets,
  HardHat,
  Lightbulb,
  MapPin,
  Plus,
  Trash2,
  Waves,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { humanize } from "@/lib/format";

const SPEC_ICONS: Record<string, LucideIcon> = {
  road_maintenance: Construction,
  garbage_collection: Trash2,
  streetlight: Lightbulb,
  waterlogging: Waves,
  sewage: Droplets,
  general: Wrench,
};

const SPECIALIZATIONS = ["general", "road_maintenance", "garbage_collection", "streetlight", "waterlogging", "sewage"];

function workloadColor(pct: number) {
  if (pct > 80) return "bg-red-500";
  if (pct > 50) return "bg-amber-500";
  return "bg-emerald-500";
}

export default function EngineersPage() {
  const { data: engineers, isLoading } = useEngineers();
  const { data: wards } = useWards();
  const currentUser = useAuthStore((s) => s.user);
  const isAdmin =
    currentUser?.role === "admin" || currentUser?.role === "super_admin";
  const createMutation = useCreateEngineerMutation();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [selectedWardId, setSelectedWardId] = useState<string>("");
  const [specialization, setSpecialization] = useState("general");
  const [maxWorkload, setMaxWorkload] = useState("10");

  const wardName = (id: number) =>
    wards?.find((w) => w.id === id)?.name ?? `Ward ${id}`;

  const list = engineers ?? [];
  const available = list.filter((e) => e.is_available).length;
  const busy = list.length - available;
  const avgResolution =
    list.length > 0
      ? list.reduce((sum, e) => sum + e.avg_resolution_hours, 0) / list.length
      : 0;

  const engineerUserIds = new Set(list.map((e) => e.user_id));

  const summary = [
    { label: "Engineers", value: list.length, icon: HardHat, chip: "bg-blue-50 text-blue-600" },
    { label: "Available", value: available, icon: Wrench, chip: "bg-emerald-50 text-emerald-600" },
    { label: "On assignment", value: busy, icon: Clock, chip: "bg-amber-50 text-amber-600" },
    {
      label: "Avg resolution",
      value: avgResolution ? `${avgResolution.toFixed(1)}h` : "—",
      icon: Clock,
      chip: "bg-violet-50 text-violet-600",
    },
  ];

  const handleCreate = async () => {
    if (!selectedUserId || !selectedWardId) {
      toast.error("Select a user and ward");
      return;
    }
    try {
      await createMutation.mutateAsync({
        user_id: Number(selectedUserId),
        ward_id: Number(selectedWardId),
        specialization,
        max_workload: Number(maxWorkload),
      });
      toast.success("Engineer added");
      setDialogOpen(false);
      setSelectedUserId("");
      setSelectedWardId("");
      setSpecialization("general");
      setMaxWorkload("10");
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to add engineer");
    }
  };

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="flex items-center justify-between">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 flex-1">
          {summary.map(({ label, value, icon: Icon, chip }) => (
            <Card key={label}>
              <CardContent className="flex items-center justify-between p-5">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">{label}</p>
                  <p className="mt-1.5 text-3xl font-semibold tracking-tight">{value}</p>
                </div>
                <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${chip}`}>
                  <Icon className="h-5 w-5" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        {isAdmin && (
          <Button className="ml-4 gap-2 shrink-0" onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Add Engineer
          </Button>
        )}
      </div>

      {/* Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-56 rounded-xl" />
          ))}
        </div>
      ) : list.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
              <HardHat className="h-7 w-7 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-base font-semibold">No engineers registered yet</h3>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {isAdmin ? "Click 'Add Engineer' to register the first field engineer." : "Engineers will appear here once added by an admin."}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {list.map((eng) => {
            const workloadPct =
              eng.max_workload > 0
                ? Math.min((eng.current_workload / eng.max_workload) * 100, 100)
                : 0;
            const SpecIcon = SPEC_ICONS[eng.specialization] ?? Wrench;
            const initials = humanize(eng.specialization ?? "General")
              .split(" ")
              .map((w) => w[0])
              .slice(0, 2)
              .join("")
              .toUpperCase();

            return (
              <Card key={eng.id} className="transition-all hover:-translate-y-0.5 hover:shadow-md">
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Avatar size="lg">
                        <AvatarFallback className="bg-primary/10 text-primary">
                          {initials || "EN"}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="text-sm font-semibold">
                          {humanize(eng.specialization ?? "General")}
                        </p>
                        <p className="text-xs text-muted-foreground">Team member #{eng.id}</p>
                      </div>
                    </div>
                    <Badge
                      variant="secondary"
                      className={
                        eng.is_available
                          ? "border-transparent bg-emerald-50 text-emerald-700"
                          : "border-transparent bg-muted text-muted-foreground"
                      }
                    >
                      <span
                        className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${
                          eng.is_available ? "bg-emerald-500" : "bg-slate-400"
                        }`}
                      />
                      {eng.is_available ? "Available" : "On assignment"}
                    </Badge>
                  </div>

                  <div className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 text-sm">
                    <SpecIcon className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Specialization</span>
                    <span className="ml-auto font-medium">
                      {humanize(eng.specialization ?? "General")}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-sm">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Zone</span>
                    <span className="ml-auto font-medium">{wardName(eng.ward_id)}</span>
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Workload</span>
                      <span className="font-medium">
                        {eng.current_workload}/{eng.max_workload} issues
                      </span>
                    </div>
                    <Progress
                      value={workloadPct}
                      indicatorClassName={workloadColor(workloadPct)}
                    />
                  </div>

                  <div className="flex items-center justify-between border-t pt-3 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      Avg resolution
                    </span>
                    <span className="font-medium text-foreground">
                      {eng.avg_resolution_hours.toFixed(1)} hours
                    </span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Add Engineer Dialog */}
      <AddEngineerDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        selectedUserId={selectedUserId}
        setSelectedUserId={setSelectedUserId}
        selectedWardId={selectedWardId}
        setSelectedWardId={setSelectedWardId}
        specialization={specialization}
        setSpecialization={setSpecialization}
        maxWorkload={maxWorkload}
        setMaxWorkload={setMaxWorkload}
        onSubmit={handleCreate}
        engineerUserIds={engineerUserIds}
        wards={wards ?? []}
      />
    </div>
  );
}

function AddEngineerDialog({
  open,
  onOpenChange,
  selectedUserId,
  setSelectedUserId,
  selectedWardId,
  setSelectedWardId,
  specialization,
  setSpecialization,
  maxWorkload,
  setMaxWorkload,
  onSubmit,
  engineerUserIds,
  wards,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  selectedUserId: string;
  setSelectedUserId: (v: string) => void;
  selectedWardId: string;
  setSelectedWardId: (v: string) => void;
  specialization: string;
  setSpecialization: (v: string) => void;
  maxWorkload: string;
  setMaxWorkload: (v: string) => void;
  onSubmit: () => void;
  engineerUserIds: Set<number>;
  wards: Array<{ id: number; name: string }>;
}) {
  const { data: usersData } = useAdminUsers({ limit: 100 });
  const users = (usersData?.items ?? []).filter(
    (u) => u.role !== "admin" && !engineerUserIds.has(u.id)
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Engineer</DialogTitle>
          <DialogDescription>
            Assign an existing user as a field engineer. They will be promoted to the engineer role.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">User</label>
            <Select value={selectedUserId} onValueChange={setSelectedUserId}>
              <SelectTrigger className="h-9 text-sm">
                <SelectValue placeholder="Select a user..." />
              </SelectTrigger>
              <SelectContent>
                {users.length === 0 && (
                  <SelectItem value="none" disabled className="text-sm">
                    No eligible users
                  </SelectItem>
                )}
                {users.map((u) => (
                  <SelectItem key={u.id} value={String(u.id)} className="text-sm">
                    {u.full_name} ({u.email})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Ward</label>
            <Select value={selectedWardId} onValueChange={setSelectedWardId}>
              <SelectTrigger className="h-9 text-sm">
                <SelectValue placeholder="Select a ward..." />
              </SelectTrigger>
              <SelectContent>
                {wards.map((w) => (
                  <SelectItem key={w.id} value={String(w.id)} className="text-sm">
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Specialization</label>
            <Select value={specialization} onValueChange={setSpecialization}>
              <SelectTrigger className="h-9 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SPECIALIZATIONS.map((s) => (
                  <SelectItem key={s} value={s} className="text-sm">
                    {humanize(s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Max workload</label>
            <Input
              type="number"
              min={1}
              max={50}
              value={maxWorkload}
              onChange={(e) => setMaxWorkload(e.target.value)}
              className="h-9 text-sm"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={!selectedUserId || !selectedWardId}>
            Add Engineer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
