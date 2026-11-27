import { NextRequest, NextResponse } from "next/server"

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

    const res = await fetch(`${BACKEND}/api/v1/observability/client-errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    })

    return new NextResponse(null, { status: res.status })
  } catch {
    // Never surface a telemetry failure to the user who already hit an error.
    return NextResponse.json({ detail: "Error report not delivered." }, { status: 202 })
  }
}
