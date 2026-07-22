"use client"

import { Suspense, useEffect, useRef } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { auth, getErrorMessage } from "@/lib/api"
import { useAuthStore } from "@/store/auth"
import { setTokenCookie, setRefreshTokenCookie } from "@/lib/token-cookie"
import { loginSchema, type LoginFormData } from "@/lib/schemas"
import { Zap } from "lucide-react"

function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const setUser = useAuthStore((s) => s.setUser)

  const { register, handleSubmit, setError, formState: { errors, isSubmitting } } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  function redirectAfterLogin() {
    const redirect = searchParams.get("redirect") || "/dashboard"
    router.push(redirect)
  }

  const processedRef = useRef(false)

  useEffect(() => {
    if (processedRef.current) return
    const accessToken = searchParams.get("access_token")
    const refreshToken = searchParams.get("refresh_token")
    if (accessToken) {
      processedRef.current = true
      localStorage.setItem("access_token", accessToken)
      setTokenCookie(accessToken)
      if (refreshToken) {
        localStorage.setItem("refresh_token", refreshToken)
        setRefreshTokenCookie(refreshToken)
      }
      auth.me().then(setUser).then(redirectAfterLogin)
      return
    }
  }, [searchParams])

  async function onSubmit(data: LoginFormData) {
    try {
      const tokens = await auth.login(data.email, data.password)
      localStorage.setItem("access_token", tokens.access_token)
      setTokenCookie(tokens.access_token)
      if (tokens.refresh_token) {
        localStorage.setItem("refresh_token", tokens.refresh_token)
        setRefreshTokenCookie(tokens.refresh_token)
      }
      const user = await auth.me()
      setUser(user)
      redirectAfterLogin()
    } catch (err: unknown) {
      setError("root", { message: getErrorMessage(err, "Login failed") })
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-8">
        {/* Logo */}
        <div className="text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-primary flex items-center justify-center mb-4">
            <Zap className="h-6 w-6 text-primary-foreground" />
          </div>
          <h1 className="text-2xl font-bold">Welcome Back</h1>
          <p className="text-sm text-muted-foreground mt-1">Sign in to CivicPulse</p>
        </div>

        <Card className="border-border/50 shadow-lg">
          <CardContent className="p-6">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {errors.root && (
                <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3">
                  <p className="text-center text-sm text-destructive">{errors.root.message}</p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" placeholder="you@example.com" {...register("email")} className="h-10" />
                {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" placeholder="Enter your password" {...register("password")} className="h-10" />
                {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
              </div>

              <Button type="submit" className="w-full h-10" disabled={isSubmitting}>
                {isSubmitting ? "Signing in..." : "Sign In"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <p className="text-center text-sm text-muted-foreground">
          No account?{" "}
          <Link href="/register" className="font-medium text-primary hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
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
