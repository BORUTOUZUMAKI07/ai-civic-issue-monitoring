"use client"

import { useState } from "react"
import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { AuthShell } from "@/components/auth/auth-shell"
import { auth, getErrorMessage } from "@/lib/api"
import { Landmark, MailCheck } from "lucide-react"

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
})
type ForgotFormData = z.infer<typeof schema>

function ForgotPasswordForm() {
  const [sent, setSent] = useState(false)
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ForgotFormData>({ resolver: zodResolver(schema) })

  async function onSubmit(data: ForgotFormData) {
    try {
      await auth.forgotPassword(data.email)
      setSent(true)
    } catch (err: unknown) {
      setError("root", { message: getErrorMessage(err, "Could not send reset link") })
    }
  }

  if (sent) {
    return (
      <AuthShell>
        <div className="flex flex-col items-center text-center">
          <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500">
            <MailCheck className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Check your inbox</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            If that email is registered, we&apos;ve sent a link to reset your password.
          </p>
          <Button asChild variant="link" className="mt-4">
            <Link href="/login">Back to sign in</Link>
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
        <h1 className="text-2xl font-semibold tracking-tight">Reset your password</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Enter your email and we&apos;ll send you a reset link.
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
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="you@example.com"
              {...register("email")}
              className="h-10"
            />
            {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
          </div>

          <Button type="submit" className="h-10 w-full" disabled={isSubmitting}>
            {isSubmitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      </div>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Remembered it?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />
}