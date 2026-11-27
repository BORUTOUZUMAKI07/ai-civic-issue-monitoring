/**
 * Browser error forwarding.
 *
 * Never send the New Relic ingest key to the browser: this module posts a small,
 * allowlisted error report to our own BFF, which forwards it to the backend's
 * structured logger (and therefore the same OTLP pipeline as backend errors).
 * Failures here are deliberately silent — telemetry must never break the UI.
 */

import { isValidCorrelationId } from "./correlation"

export type ClientEventType =
  | "react_error"
  | "api_error"
  | "unhandled_rejection"
  | "window_error"

export interface ClientErrorContext {
  event_type?: ClientEventType
  api_path?: string
  method?: string
  status_code?: number
  correlation_id?: string
}

function safeMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : typeof error === "string" ? error : "Unknown error"
  return raw.slice(0, 1_000) || "Unknown error"
}

function safePath(value: string | undefined): string | undefined {
  if (!value) return undefined
  // Query strings carry one-time OAuth codes and reset tokens; keep the path.
  return value.split("?")[0].split("#")[0].slice(0, 300)
}

export function reportClientError(error: unknown, context: ClientErrorContext = {}): void {
  if (typeof window === "undefined") return

  try {
    // Only a well-formed UUID survives: the backend discards anything else, so
    // forwarding a malformed ID would silently break the browser → BFF → API
    // log join instead of creating one.
    const correlationId = isValidCorrelationId(context.correlation_id) ? context.correlation_id : undefined

    const payload = {
      event_type: context.event_type ?? "react_error",
      message: safeMessage(error),
      error_name: error instanceof Error ? error.name.slice(0, 200) : undefined,
      path: safePath(window.location.pathname),
      api_path: safePath(context.api_path),
      method: context.method?.slice(0, 10),
      status_code: context.status_code,
      correlation_id: correlationId,
      stack: error instanceof Error ? error.stack?.slice(0, 4_000) : undefined,
      timestamp: new Date().toISOString(),
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (correlationId) headers["X-Correlation-ID"] = correlationId

    void fetch("/api/client-errors", {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      keepalive: true,
      cache: "no-store",
    }).catch(() => {
      // Telemetry is best-effort; there is nowhere useful to report a failed
      // error report without recursing.
    })
  } catch {
    // Private mode / blocked fetch / JSON failure: ignore.
  }
}
