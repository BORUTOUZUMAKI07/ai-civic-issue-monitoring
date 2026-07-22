"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/auth";
import { toast } from "sonner";
import { User, Bell, Shield } from "lucide-react";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const [saved, setSaved] = useState(false);

  function handleSave() {
    setSaved(true);
    toast.success("Settings saved");
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <div className="space-y-6 p-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your account and preferences</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <User className="h-4 w-4" /> Profile
          </CardTitle>
          <CardDescription>Your account information</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Full Name</Label>
            <Input value={user?.full_name || ""} readOnly className="bg-muted/50" />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input value={user?.email || ""} readOnly className="bg-muted/50" />
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <Input value={user?.role?.replace("_", " ") || ""} readOnly className="bg-muted/50 capitalize" />
          </div>
          <div className="space-y-2">
            <Label>Account Created</Label>
            <Input value={user?.created_at ? new Date(user.created_at).toLocaleDateString() : ""} readOnly className="bg-muted/50" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bell className="h-4 w-4" /> Notifications
          </CardTitle>
          <CardDescription>Configure how you receive updates</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-lg border border-border/50">
            <div>
              <p className="text-sm font-medium">Real-time WebSocket</p>
              <p className="text-xs text-muted-foreground">Instant in-app notifications</p>
            </div>
            <Badge>Active</Badge>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border border-border/50">
            <div>
              <p className="text-sm font-medium">Email Notifications</p>
              <p className="text-xs text-muted-foreground">Receive email for critical issues</p>
            </div>
            <Badge variant="secondary">Coming Soon</Badge>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="h-4 w-4" /> Security
          </CardTitle>
          <CardDescription>Authentication and access settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-lg border border-border/50">
            <div>
              <p className="text-sm font-medium">Password</p>
              <p className="text-xs text-muted-foreground">Last changed: Never</p>
            </div>
            <Button variant="outline" size="sm">Change</Button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border border-border/50">
            <div>
              <p className="text-sm font-medium">Two-Factor Auth</p>
              <p className="text-xs text-muted-foreground">Add extra security to your account</p>
            </div>
            <Badge variant="secondary">Coming Soon</Badge>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave}>{saved ? "Saved!" : "Save Changes"}</Button>
      </div>
    </div>
  );
}
