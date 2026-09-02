"use client"

import { Suspense, useState } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { AuthShell } from "@/components/auth/auth-shell"
import { auth, getErrorMessage } from "@/lib/api"
import { Landmark } from "lucide-react"

const schema = z
  .object({
    new_password: z.string().min(6, "Password must be at least 6 characters"),
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  })
type ResetFormData = z.infer<typeof schema>

function ResetPasswordForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token") || ""
  const [done, setDone] = useState(false)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ResetFormData>({ resolver: zodResolver(schema) })

  if (!token) {
    return (
      <AuthShell>
        <div className="text-center">
          <h1 className="text-2xl font-semibold">Invalid link</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            This password reset link is missing a token.
          </p>
          <Button asChild variant="link" className="mt-4">
            <Link href="/forgot-password">Request a new link</Link>
          </Button>
        </div>
      </AuthShell>
    )
  }

  async function onSubmit(data: ResetFormData) {
    try {
      await auth.resetPassword(token, data.new_password)
      setDone(true)
      router.push("/login")
    } catch (err: unknown) {
      setError("root", {
        message: getErrorMessage(err, "Could not reset password — the link may have expired."),
      })
    }
  }

  if (done) {
    return (
      <AuthShell>
        <div className="text-center">
          <h1 className="text-2xl font-semibold">Password updated</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            You can now sign in with your new password.
          </p>
          <Button asChild className="mt-4">
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell>
      <div className="mb-8 flex flex-col items-center text-center lg:items-start lg:text-left">
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 shadow-glow-primary lg:hidden">
          <Landmark className="h-5 w-5 text-white" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Choose a new password</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Pick a strong password you haven&apos;t used before.
        </p>
      </div>

      <div className="rounded-2xl border border-border/80 bg-card p-6 shadow-lift sm:p-7">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {errors.root && (
            <div className="rounded-lg border border-destructive/25 bg-destructive/10 px-4 py-3">
              <p className="text-center text-sm text-destructive">{errors.root.message}</p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="new_password">New password</Label>
            <Input
              id="new_password"
              type="password"
              placeholder="Min 6 characters"
              {...register("new_password")}
              className="h-10"
            />
            {errors.new_password && (
              <p className="text-xs text-destructive">{errors.new_password.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirm">Confirm new password</Label>
            <Input
              id="confirm"
              type="password"
              placeholder="Repeat new password"
              {...register("confirm")}
              className="h-10"
            />
            {errors.confirm && <p className="text-xs text-destructive">{errors.confirm.message}</p>}
          </div>

          <Button type="submit" className="h-10 w-full" disabled={isSubmitting}>
            {isSubmitting ? "Updating…" : "Update password"}
          </Button>
        </form>
      </div>
    </AuthShell>
  )
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <div className="size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  )
}