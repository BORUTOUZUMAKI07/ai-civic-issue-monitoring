"use client"

import { Suspense, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { auth, getErrorMessage } from "@/lib/api"
import { useAuthStore } from "@/store/auth"
import { loginSchema, type LoginFormData } from "@/lib/schemas"
import { AuthShell } from "@/components/auth/auth-shell"
import { OAuthButtons } from "@/components/auth/oauth-buttons"
import { Landmark, ShieldCheck } from "lucide-react"

function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setUser = useAuthStore((s) => s.setUser)

  const [challenge, setChallenge] = useState<string | null>(null)
  const [totpCode, setTotpCode] = useState("")
  const [totpError, setTotpError] = useState<string | null>(null)
  const [isVerifying, setIsVerifying] = useState(false)

  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  function redirectAfterLogin() {
    const redirect = searchParams.get("redirect") || "/dashboard"
    router.push(redirect)
  }

  async function onSubmit(data: LoginFormData) {
    try {
      const res = await auth.login(data.email, data.password)
      if (res.challenge) {
        setChallenge(res.challenge)
        return
      }
      const user = await auth.me()
      setUser(user)
      redirectAfterLogin()
    } catch (err: unknown) {
      setError("root", { message: getErrorMessage(err, "Login failed") })
    }
  }

  async function onVerifyTotp(e: React.FormEvent) {
    e.preventDefault()
    if (!challenge || totpCode.length < 6) return
    setIsVerifying(true)
    setTotpError(null)
    try {
      await auth.twofaVerify(challenge, totpCode)
      const user = await auth.me()
      setUser(user)
      redirectAfterLogin()
    } catch (err: unknown) {
      setTotpError(getErrorMessage(err, "Invalid code"))
    } finally {
      setIsVerifying(false)
    }
  }

  return (
    <AuthShell>
      <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-glow-primary lg:hidden">
          <Landmark className="h-5 w-5 text-white" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Sign in to the CivicPulse command center
        </p>
      </div>

      <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-lift sm:p-7">
        {challenge ? (
          /* ---- 2FA code entry ---- */
          <form onSubmit={onVerifyTotp} className="space-y-4">
            <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-4 py-3">
              <ShieldCheck className="h-5 w-5 text-primary" />
              <div>
                <p className="text-sm font-medium">Two-factor authentication</p>
                <p className="text-xs text-muted-foreground">Enter the 6-digit code from your authenticator app, or a recovery code.</p>
              </div>
            </div>

            {totpError && (
              <div className="rounded-lg border border-destructive/25 bg-destructive/10 px-4 py-3">
                <p className="text-center text-sm text-destructive">{totpError}</p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="totp-code">Verification code</Label>
              <Input
                id="totp-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/[^0-9a-zA-Z-]/g, ""))}
                className="h-10 font-mono tracking-widest"
                autoFocus
                maxLength={14}
              />
            </div>

            <Button type="submit" className="h-10 w-full" disabled={isVerifying || totpCode.length < 6}>
              {isVerifying ? "Verifying\u2026" : "Verify"}
            </Button>

            <button
              type="button"
              className="w-full text-center text-xs text-muted-foreground hover:underline"
              onClick={() => { setChallenge(null); setTotpCode(""); setTotpError(null) }}
            >
              Back to sign in
            </button>
          </form>
        ) : (
          /* ---- normal login ---- */
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {errors.root && (
              <div className="rounded-lg border border-destructive/25 bg-destructive/10 px-4 py-3">
                <p className="text-center text-sm text-destructive">{errors.root.message}</p>
              </div>
            )}

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="email">Email</Label>
                <Link
                  href="/forgot-password"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <Input id="email" type="email" placeholder="you@example.com" {...register("email")} className="h-10" />
              {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" placeholder="Enter your password" {...register("password")} className="h-10" />
              {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
            </div>

            <Button type="submit" className="h-10 w-full" disabled={isSubmitting}>
              {isSubmitting ? "Signing in\u2026" : "Sign In"}
            </Button>
          </form>
        )}
      </div>

      {!challenge && <OAuthButtons />}

      <p className="mt-6 text-center text-sm text-muted-foreground">
        No account yet?{" "}
        <Link href="/register" className="font-medium text-primary hover:underline">
          Request access
        </Link>
      </p>
    </AuthShell>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <div className="size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    }>
      <LoginForm />
    </Suspense>
  )
}
