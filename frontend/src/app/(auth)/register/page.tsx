"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useRegisterMutation } from "@/queries/index";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import Link from "next/link";
import { AuthShell } from "@/components/auth/auth-shell";
import { OAuthButtons } from "@/components/auth/oauth-buttons";
import { Landmark } from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const registerMutation = useRegisterMutation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await registerMutation.mutateAsync({
        email,
        password,
        full_name: fullName,
        role: "field_worker",
      });
      toast.success("Account created! Please sign in.");
      router.push("/login");
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Registration failed");
    }
  };

  return (
    <AuthShell>
      <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-glow-primary lg:hidden">
          <Landmark className="h-5 w-5 text-white" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Create your account</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Join the CivicPulse platform for Vadodara Municipal
        </p>
      </div>

      <OAuthButtons />

      <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-lift sm:p-7">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="fullName">Full Name</Label>
            <Input
              id="fullName"
              placeholder="Your full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              className="h-10"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="h-10"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Min 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="h-10"
            />
          </div>
          <Button type="submit" className="h-10 w-full" disabled={registerMutation.isPending}>
            {registerMutation.isPending ? "Creating account…" : "Create Account"}
          </Button>
        </form>
      </div>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
