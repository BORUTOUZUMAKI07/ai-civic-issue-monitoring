"use client";

import { Button } from "@/components/ui/button";
import { TriangleAlert } from "lucide-react";
import { getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Consistent failure state for a page-level query. Without this a failed fetch
 * rendered the same empty UI as "no data", which hid 500s and RBAC 403s behind a
 * blank dashboard.
 */
export function QueryError({
  error,
  onRetry,
  title = "Something went wrong",
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border bg-card px-6 py-12 text-center",
        className
      )}
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-full bg-destructive/10">
        <TriangleAlert className="h-5 w-5 text-destructive" />
      </div>
      <div className="space-y-1">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-sm text-muted-foreground">
          {getErrorMessage(error, "Please try again.")}
        </p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
