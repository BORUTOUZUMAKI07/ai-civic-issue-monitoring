"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { useAuthStore } from "@/store/auth";
import { apiFetch } from "@/lib/api";
import type { MlInfo } from "@/lib/api";
import { toast } from "sonner";
import {
  AtSign,
  Bell,
  Brain,
  CalendarDays,
  CheckCircle,
  KeyRound,
  Mail,
  Radio,
  ShieldCheck,
  TriangleAlert,
  User,
  Wrench,
} from "lucide-react";
import { formatDate, initials } from "@/lib/format";

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof User;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-background px-4 py-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-medium capitalize">{value}</p>
      </div>
    </div>
  );
}

function ToggleRow({
  icon: Icon,
  title,
  description,
  checked,
  onCheckedChange,
}: {
  icon: typeof Bell;
  title: string;
  description: string;
  checked: boolean;
  onCheckedChange?: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border px-4 py-3.5">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm font-medium">{title}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const [webSocket, setWebSocket] = useState(true);
  const [emailNotif, setEmailNotif] = useState(false);
  const [twoFactor, setTwoFactor] = useState(false);

  const roleLabel = (user?.role ?? "field_worker").replace("_", " ");

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Profile header */}
      <Card>
        <CardContent className="flex flex-col items-center gap-4 p-6 sm:flex-row sm:items-center">
          <Avatar size="xl">
            <AvatarFallback className="bg-primary text-base font-semibold text-primary-foreground">
              {initials(user?.full_name ?? "User")}
            </AvatarFallback>
          </Avatar>
          <div className="text-center sm:text-left">
            <h2 className="text-lg font-semibold tracking-tight">{user?.full_name}</h2>
            <p className="text-sm text-muted-foreground">{user?.email}</p>
            <div className="mt-2 flex justify-center gap-2 sm:justify-start">
              <Badge variant="secondary" className="gap-1.5">
                <Wrench className="h-3 w-3" />
                {roleLabel}
              </Badge>
              <Badge
                variant="secondary"
                className="border-transparent bg-emerald-50 text-emerald-700"
              >
                <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                Active
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="profile">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="profile" className="gap-1.5">
            <User className="h-3.5 w-3.5" /> Profile
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-1.5">
            <Bell className="h-3.5 w-3.5" /> Notifications
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" /> Security
          </TabsTrigger>
          <TabsTrigger value="ml" className="gap-1.5">
            <Brain className="h-3.5 w-3.5" /> ML Model
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Account details</CardTitle>
              <CardDescription>
                Information associated with your CivicPulse account.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <InfoRow icon={User} label="Full name" value={user?.full_name ?? "—"} />
              <InfoRow icon={AtSign} label="Email" value={user?.email ?? "—"} />
              <InfoRow icon={Wrench} label="Role" value={roleLabel} />
              <InfoRow
                icon={CalendarDays}
                label="Member since"
                value={user?.created_at ? formatDate(user.created_at) : "—"}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Member ID</CardTitle>
              <CardDescription>Your unique identifier in the system.</CardDescription>
            </CardHeader>
            <CardContent className="flex items-center gap-3">
              <span className="rounded-md bg-muted px-3 py-1.5 font-mono text-sm">
                #CIV-{String(user?.id ?? 0).padStart(4, "0")}
              </span>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Notification preferences</CardTitle>
              <CardDescription>
                Choose how you want to be alerted about civic issues.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ToggleRow
                icon={Radio}
                title="Real-time updates"
                description="Instant WebSocket alerts when an issue is reported or updated."
                checked={webSocket}
                onCheckedChange={(v) => {
                  setWebSocket(v);
                  toast.success(v ? "Real-time alerts enabled" : "Real-time alerts paused");
                }}
              />
              <ToggleRow
                icon={Mail}
                title="Email notifications"
                description="Receive a summary email for critical issues in your zone."
                checked={emailNotif}
                onCheckedChange={(v) => {
                  setEmailNotif(v);
                  toast.success(v ? "Email notifications enabled" : "Email notifications disabled");
                }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="mt-4 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Security</CardTitle>
              <CardDescription>
                Keep your account protected with these options.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-start justify-between gap-4 rounded-lg border px-4 py-3.5">
                <div className="flex items-start gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                    <KeyRound className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Password</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Use a strong, unique password for your account.
                    </p>
                  </div>
                </div>
                <Button variant="outline" size="sm" disabled>
                  Change
                </Button>
              </div>

              <ToggleRow
                icon={ShieldCheck}
                title="Two-factor authentication"
                description="Add an extra layer of security to sign-ins."
                checked={twoFactor}
                onCheckedChange={(v) => {
                  setTwoFactor(v);
                  toast.info("Two-factor authentication is coming soon");
                  setTwoFactor(false);
                }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ml" className="mt-4 space-y-4">
          <MlModelHealth />
        </TabsContent>
      </Tabs>

      <Separator />

      <p className="text-center text-xs text-muted-foreground">
        CivicPulse · Vadodara Municipal Corporation · Secure session
      </p>
    </div>
  );
}

function MlModelHealth() {
  const { data: info, isLoading, error } = useQuery<MlInfo>({
    queryKey: ["ml-info"],
    queryFn: () => apiFetch("/api/v1/ml/info"),
    retry: false,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model health</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
          <div className="h-4 w-1/2 animate-pulse rounded bg-muted" />
        </CardContent>
      </Card>
    );
  }

  if (error || !info) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 py-6 text-muted-foreground">
          <TriangleAlert className="h-4 w-4" />
          <p className="text-sm">Could not load ML model information.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Brain className="h-4 w-4" />
          Model health
        </CardTitle>
        <CardDescription>
          Current inference model status and configuration.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <InfoRow
            icon={CheckCircle}
            label="Model file"
            value={info.model_exists ? `${info.model_size_mb} MB` : "Not found"}
          />
          <InfoRow
            icon={CheckCircle}
            label="ONNX model"
            value={info.onnx_exists ? "Available" : "Not exported"}
          />
          <InfoRow
            icon={CheckCircle}
            label="LoRA adapter"
            value={info.adapter_exists ? "Available" : "Not loaded"}
          />
          <InfoRow
            icon={Brain}
            label="Classes"
            value={`${info.num_classes ?? (info.classes ?? []).length} categories`}
          />
        </div>

        <Separator />

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Class labels
          </p>
          <div className="flex flex-wrap gap-2">
            {(info.classes ?? []).map((name) => (
              <Badge key={name} variant="secondary" className="capitalize">
                {name.replace(/_/g, " ")}
              </Badge>
            ))}
          </div>
        </div>

        <Separator />

        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Intake gate thresholds
          </p>
          {info.default_threshold != null ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Accept</p>
                <Progress value={(info.default_threshold ?? 0.7) * 100} className="h-1.5" />
                <p className="text-xs font-mono text-right">
                  {((info.default_threshold ?? 0.7) * 100).toFixed(0)}%
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Review</p>
                <Progress value={(info.review_threshold ?? 0.4) * 100} className="h-1.5" />
                <p className="text-xs font-mono text-right">
                  {((info.review_threshold ?? 0.4) * 100).toFixed(0)}%
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Reject</p>
                <Progress value={(info.reject_threshold ?? 0.15) * 100} className="h-1.5" />
                <p className="text-xs font-mono text-right">
                  {((info.reject_threshold ?? 0.15) * 100).toFixed(0)}%
                </p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Thresholds are configured server-side in backend settings.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
