"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { apiFetch, auth, getErrorMessage } from "@/lib/api";
import type { MlInfo } from "@/lib/api";
import { toast } from "sonner";
import {
  AtSign,
  Bell,
  Brain,
  CalendarDays,
  CheckCircle,
  Copy,
  KeyRound,
  Mail,
  Radio,
  ShieldCheck,
  TriangleAlert,
  User,
  Wrench,
} from "lucide-react";
import { formatDate, initials } from "@/lib/format";
import { QRCodeSVG } from "qrcode.react";

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
  const queryClient = useQueryClient();
  const [webSocket, setWebSocket] = useState(true);
  const [emailNotif, setEmailNotif] = useState(false);

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
              <InfoRow icon={User} label="Full name" value={user?.full_name ?? "\u2014"} />
              <InfoRow icon={AtSign} label="Email" value={user?.email ?? "\u2014"} />
              <InfoRow icon={Wrench} label="Role" value={roleLabel} />
              <InfoRow
                icon={CalendarDays}
                label="Member since"
                value={user?.created_at ? formatDate(user.created_at) : "\u2014"}
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

              <TwoFactorSection />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ml" className="mt-4 space-y-4">
          <MlModelHealth />
        </TabsContent>
      </Tabs>

      <Separator />

      <p className="text-center text-xs text-muted-foreground">
        CivicPulse &middot; Vadodara Municipal Corporation &middot; Secure session
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  2FA Section                                                        */
/* ------------------------------------------------------------------ */

type TwoFactorState =
  | { step: "idle" }
  | { step: "setup"; secret: string; provisioningUri: string }
  | { step: "confirm"; secret: string }
  | { step: "done"; recoveryCodes: string[] }
  | { step: "disable-confirm" };

function TwoFactorSection() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const queryClient = useQueryClient();
  const [state, setState] = useState<TwoFactorState>({ step: "idle" });
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enabled = user?.two_factor_enabled ?? false;

  async function handleEnable() {
    setLoading(true);
    setError(null);
    try {
      const res = await auth.twofaEnable();
      setState({ step: "setup", secret: res.secret, provisioningUri: res.provisioning_uri });
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Failed to enable 2FA"));
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmSetup(e: React.FormEvent) {
    e.preventDefault();
    if (code.length < 6) return;
    setLoading(true);
    setError(null);
    try {
      const res = await auth.twofaConfirm(code);
      setState({ step: "done", recoveryCodes: res.recovery_codes });
      const fresh = await auth.me();
      setUser(fresh);
      queryClient.invalidateQueries({ queryKey: ["me"] });
      toast.success("Two-factor authentication enabled");
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Invalid code"));
    } finally {
      setLoading(false);
    }
  }

  async function handleStartDisable() {
    setState({ step: "disable-confirm" });
    setCode("");
    setError(null);
  }

  async function handleConfirmDisable(e: React.FormEvent) {
    e.preventDefault();
    if (code.length < 6) return;
    setLoading(true);
    setError(null);
    try {
      await auth.twofaDisable(code);
      setState({ step: "idle" });
      const fresh = await auth.me();
      setUser(fresh);
      queryClient.invalidateQueries({ queryKey: ["me"] });
      toast.success("Two-factor authentication disabled");
    } catch (err: unknown) {
      setError(getErrorMessage(err, "Invalid code"));
    } finally {
      setLoading(false);
    }
  }

  function handleCopyCodes() {
    const text = state.step === "done" ? state.recoveryCodes.join("\n") : "";
    navigator.clipboard.writeText(text);
    toast.success("Recovery codes copied to clipboard");
  }

  // -- Render --

  // Done state: show recovery codes once
  if (state.step === "done") {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 space-y-3">
        <div className="flex items-start gap-3">
          <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
          <div className="space-y-2">
            <p className="text-sm font-medium text-emerald-800">2FA enabled</p>
            <p className="text-xs text-emerald-700">Save these recovery codes somewhere safe. Each code can only be used once.</p>
          </div>
        </div>
        <div className="rounded-md bg-white border p-3 font-mono text-xs space-y-1">
          {state.recoveryCodes.map((c, i) => (
            <div key={i}>{c}</div>
          ))}
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={handleCopyCodes} className="gap-1.5">
            <Copy className="h-3 w-3" /> Copy
          </Button>
          <Button size="sm" onClick={() => setState({ step: "idle" })}>Done</Button>
        </div>
      </div>
    );
  }

  // Setup flow: scan QR / enter code
  if (state.step === "setup") {
    return (
      <div className="rounded-lg border border-primary/25 bg-primary/5 p-4 space-y-3">
        <p className="text-sm font-medium">Set up two-factor authentication</p>
        <p className="text-xs text-muted-foreground">Scan this QR code with your authenticator app, or enter the secret manually.</p>
        <div className="flex justify-center">
          <div className="rounded-md border bg-white p-2">
            <QRCodeSVG
              value={state.provisioningUri}
              size={176}
              level="M"
              marginSize={1}
            />
          </div>
        </div>
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">Manual entry key:</p>
          <code className="block rounded bg-muted px-3 py-1.5 font-mono text-xs break-all">{state.secret}</code>
        </div>
        <Button size="sm" variant="outline" onClick={() => { setState({ step: "confirm", secret: state.secret }); setCode(""); setError(null); }}>
          I&apos;ve scanned it &mdash; enter code
        </Button>
      </div>
    );
  }

  if (state.step === "confirm") {
    return (
      <div className="rounded-lg border border-primary/25 bg-primary/5 p-4 space-y-3">
        <p className="text-sm font-medium">Confirm setup</p>
        <p className="text-xs text-muted-foreground">Enter the 6-digit code from your authenticator app.</p>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <form onSubmit={handleConfirmSetup} className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <Label htmlFor="confirm-code" className="sr-only">Code</Label>
            <Input
              id="confirm-code"
              type="text"
              inputMode="numeric"
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="h-9 font-mono tracking-widest"
              maxLength={6}
              autoFocus
            />
          </div>
          <Button type="submit" size="sm" disabled={loading || code.length < 6}>
            {loading ? "Verifying\u2026" : "Verify"}
          </Button>
        </form>
      </div>
    );
  }

  // Disable confirmation
  if (state.step === "disable-confirm") {
    return (
      <div className="rounded-lg border border-destructive/25 bg-destructive/5 p-4 space-y-3">
        <p className="text-sm font-medium">Disable two-factor authentication</p>
        <p className="text-xs text-muted-foreground">Enter your current TOTP code to confirm.</p>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <form onSubmit={handleConfirmDisable} className="flex items-end gap-2">
          <div className="flex-1 space-y-1">
            <Label htmlFor="disable-code" className="sr-only">Code</Label>
            <Input
              id="disable-code"
              type="text"
              inputMode="numeric"
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="h-9 font-mono tracking-widest"
              maxLength={6}
              autoFocus
            />
          </div>
          <Button type="submit" size="sm" variant="destructive" disabled={loading || code.length < 6}>
            {loading ? "Disabling\u2026" : "Disable"}
          </Button>
        </form>
        <button
          type="button"
          className="text-xs text-muted-foreground hover:underline"
          onClick={() => { setState({ step: "idle" }); setCode(""); setError(null); }}
        >
          Cancel
        </button>
      </div>
    );
  }

  // Idle: show toggle
  return (
    <ToggleRow
      icon={ShieldCheck}
      title="Two-factor authentication"
      description={enabled ? "Enabled \u2014 your account is protected with an extra layer of security." : "Add an extra layer of security to sign-ins."}
      checked={enabled}
      onCheckedChange={(v) => {
        if (v) {
          handleEnable();
        } else {
          handleStartDisable();
        }
      }}
    />
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
