import { NextRequest, NextResponse } from "next/server"

import { isValidCorrelationId } from "@/lib/correlation"

/**
 * Browser → BFF → backend error bridge.
 *
 * Kept separate from the general /api/proxy catch-all so it needs no access
 * token (anonymous visitors hit error boundaries too) and carries no cookies.
 * The backend validates and scrubs every field before logging it.
 */

const BACKEND =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000"

const MAX_ERROR_BODY_BYTES = 64 * 1024

export async function POST(request: NextRequest) {
  try {
    const declared = Number(request.headers.get("content-length") ?? "0")
    if (Number.isFinite(declared) && declared > MAX_ERROR_BODY_BYTES) {
      return NextResponse.json({ detail: "Error report too large." }, { status: 413 })
    }

    const body = await request.arrayBuffer()
    if (body.byteLength > MAX_ERROR_BODY_BYTES) {
      return NextResponse.json({ detail: "Error report too large." }, { status: 413 })
    }

    // The BFF is the trust boundary: a caller-supplied header is ignored, and
    // only a UUID-shaped correlation_id from the (already bounded) body is
    // promoted to a header the backend middleware will bind into the request
    // context. Anything else is dropped so the backend generates its own ID.
    let correlationId: string | undefined
    try {
      const parsed = JSON.parse(new TextDecoder().decode(body)) as { correlation_id?: unknown }
      if (isValidCorrelationId(parsed.correlation_id)) correlationId = parsed.correlation_id
    } catch {
      // Malformed JSON: forward as-is; the backend schema returns 422.
    }

    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (correlationId) headers["X-Correlation-ID"] = correlationId

    const res = await fetch(`${BACKEND}/api/v1/observability/client-errors`, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
    })

    return new NextResponse(null, { status: res.status })
  } catch {
    // Never surface a telemetry failure to the user who already hit an error.
    return NextResponse.json({ detail: "Error report not delivered." }, { status: 202 })
  }
}
