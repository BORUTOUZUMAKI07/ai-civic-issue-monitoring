"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => { console.error(error) }, [error])

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center p-6">
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-12 text-center">
        <h2 className="mb-2 text-lg font-semibold text-destructive">Issues Error</h2>
        <p className="mb-6 max-w-md text-sm text-muted-foreground">
          {error.message || "Failed to load issues."}
        </p>
        <Button onClick={reset} variant="destructive">
          Try Again
        </Button>
      </div>
    </div>
  )
}
