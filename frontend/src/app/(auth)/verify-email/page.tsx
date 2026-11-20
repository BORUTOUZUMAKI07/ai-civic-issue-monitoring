"use client"

import { Suspense, useEffect, useState } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { AuthShell } from "@/components/auth/auth-shell"
import { auth, getErrorMessage } from "@/lib/api"
import { Landmark, MailCheck } from "lucide-react"

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const token = searchParams.get("token") || ""
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    token ? "loading" : "error"
  )
  const [message, setMessage] = useState<string>(
    token ? "Verifying your email..." : "This verification link is missing a token."
  )

  useEffect(() => {
    if (!token) return
    let cancelled = false
    auth
      .verifyEmail(token)
      .then((res) => {
        if (cancelled) return
        setStatus("success")
        setMessage(res.detail || "Email verified. You can now sign in.")
      })
      .catch((err) => {
        if (cancelled) return
        setStatus("error")
        setMessage(getErrorMessage(err, "This verification link is invalid or has expired."))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <AuthShell>
      <div className="flex flex-col items-center text-center">
        <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 shadow-glow-primary lg:hidden">
          {status === "success" ? <MailCheck className="h-5 w-5 text-white" /> : <Landmark className="h-5 w-5 text-white" />}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {status === "loading"
            ? "Verifying email"
            : status === "success"
              ? "Email verified"
              : "Verification failed"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        <div className="mt-6 flex gap-2">
          <Button asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          {status === "error" && (
            <Button asChild variant="outline">
              <Link href="/register">Create account</Link>
            </Button>
          )}
        </div>
      </div>
    </AuthShell>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <div className="size-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  )
}
