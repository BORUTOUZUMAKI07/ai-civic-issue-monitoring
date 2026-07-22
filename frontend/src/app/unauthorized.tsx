import Link from "next/link"

export default function Unauthorized() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <h1 className="text-6xl font-bold text-muted-foreground">401</h1>
      <p className="mt-3 text-lg text-muted-foreground">You need to sign in to access this page.</p>
      <Link
        href="/login"
        className="mt-6 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Sign In
      </Link>
    </div>
  )
}
