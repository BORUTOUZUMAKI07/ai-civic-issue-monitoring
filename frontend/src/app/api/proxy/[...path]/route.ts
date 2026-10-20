import { NextRequest, NextResponse } from "next/server"

/**
 * Where the backend actually lives, as seen from *this server*.
 *
 * `BACKEND_URL` is the server-only variable to set (Docker Compose sets it to
 * `http://backend:8000`, the in-network service name). `NEXT_PUBLIC_API_URL`
 * is kept only as a fallback for existing setups — it is a *browser* variable
 * (`http://localhost:8000`), and inside a container that resolves to the
 * container itself, not the backend. It is not inlined into client bundles
 * anywhere: the browser only ever talks to this proxy.
 */
const BACKEND =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000"

/**
 * Mirrors the backend's own ceilings (`backend/src/shared/uploads.py`), with
 * slack for the multipart envelope. Checked here so an oversized body is
 * refused before it is buffered: `request.arrayBuffer()` below would
 * otherwise pull the whole thing into the Next.js process's memory long
 * before the backend could reject it.
 */
const MAX_UPLOAD_BODY_BYTES = 7 * 1024 * 1024
const MAX_JSON_BODY_BYTES = 1024 * 1024

type RouteContext = { params: Promise<{ path: string[] }> }

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context)
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context)
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context)
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, context)
}

/**
 * Backend route prefixes this proxy is allowed to reach.
 *
 * An allowlist, not a denylist: the previous version interpolated caller
 * segments straight into `/api/v1/${path.join("/")}` and handed the result to
 * `new URL()`, which normalises `..` — so `/api/proxy/issues/../../uploads/x`
 * escaped the API prefix entirely and reached any backend route (health probe,
 * static `/uploads`, internal tooling). Requiring the first segment to be a
 * known router name confines every request to the API surface by construction.
 */
const ALLOWED_PREFIXES = new Set([
  "auth",
  "issues",
  "wards",
  "engineers",
  "resolution",
  "dashboard",
  "notifications",
  "admin",
  "ml",
])

/**
 * Routes that must carry the refresh cookie.
 *
 * The refresh token is a long-lived credential and forwarding it on *every*
 * proxied request — as this proxy used to — multiplies the blast radius of any
 * single leaked request (logs, tracing, an XSS'd fetch) from "one access
 * token" to "full account takeover until the refresh token expires".
 * `/auth/refresh` and `/auth/logout` are the only handlers that read it.
 */
const NEEDS_REFRESH = new Set(["auth/refresh", "auth/logout"])

/**
 * Paths that may be called without an access token.
 *
 * Beyond the auth flows, this includes the handful of read-only endpoints the
 * public marketing page renders before anyone has signed in. They are safe to
 * expose because they leak counts only, never rows: listing a path here is a
 * deliberate statement that the backend handler behind it needs no identity,
 * not a convenience.
 */
const PUBLIC_PREFIXES = [
  "auth/login",
  "auth/register",
  "auth/forgot-password",
  "auth/reset-password",
  "auth/2fa",
  "auth/oauth",
  "auth/refresh",
  "auth/logout",
  "dashboard/public-stats",
]

function isPublicRoute(key: string): boolean {
  return PUBLIC_PREFIXES.some((p) => key === p || key.startsWith(`${p}/`))
}

async function proxy(request: NextRequest, context: RouteContext) {
  try {
    const { path } = await context.params
    const accessToken = request.cookies.get("access_token")?.value
    const refreshToken = request.cookies.get("refresh_token")?.value

    // Normalise every segment: reject traversal, absolute URLs, NUL bytes and
    // anything that is not a plain path component before it is joined.
    const segments = path
      .map((raw) => {
        // `path` is already URL-decoded by Next, so `%2e%2e` arrives as `..`.
        const seg = raw.trim()
        if (seg === ".." || seg === "." || seg.includes("/") || seg.includes("\\") || seg.includes("\0")) {
          return null
        }
        return seg
      })
      // The type predicate is what gives `segments` a `string[]` type.
      // Without it `segments[0]` stays `string | null` and the prefix check
      // below does not compile; comparing against `path.length` preserves the
      // rejection signal that `.filter` would otherwise discard.
      .filter((seg): seg is string => seg !== null)

    if (segments.length !== path.length || segments.length === 0) {
      return NextResponse.json({ detail: "Invalid path." }, { status: 400 })
    }

    const key = segments.join("/")
    if (!ALLOWED_PREFIXES.has(segments[0])) {
      return NextResponse.json({ detail: "Not found." }, { status: 404 })
    }

    // Server-side auth guard. `middleware.ts` deliberately excludes `/api` from
    // its matcher, so nothing else checks this route — without this the proxy
    // was reachable unauthenticated and simply relayed whatever cookies it got.
    if (!isPublicRoute(key) && !accessToken) {
      return NextResponse.json({ detail: "Not authenticated." }, { status: 401 })
    }

    const targetPath = `/api/v1/${key}`
    const url = new URL(targetPath, BACKEND)
    url.search = request.nextUrl.search

    const headers: Record<string, string> = {}
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`
    }

    // Forward the auth cookies to the backend so endpoints that read them
    // server-side (/auth/refresh, /auth/logout) work. The browser sends the
    // access+refresh cookies to this proxy path, and we relay them to the
    // backend; the access token is also sent as a Bearer header above.
    const cookieParts: string[] = []
    if (accessToken) cookieParts.push(`access_token=${accessToken}`)
    if (refreshToken && NEEDS_REFRESH.has(key)) cookieParts.push(`refresh_token=${refreshToken}`)
    if (cookieParts.length > 0) {
      headers["Cookie"] = cookieParts.join("; ")
    }

    const contentType = request.headers.get("content-type")
    if (contentType) {
      headers["Content-Type"] = contentType
    }

    let body: ArrayBuffer | string | undefined
    if (request.method !== "GET" && request.method !== "HEAD") {
      // Cap the body before buffering it. A declared length over the ceiling
      // is refused outright; a missing or bogus one (chunked) is checked again
      // after the read, so neither path can walk off with the process.
      const declared = Number(request.headers.get("content-length") ?? "0")
      const limit = contentType?.includes("multipart/form-data")
        ? MAX_UPLOAD_BODY_BYTES
        : MAX_JSON_BODY_BYTES
      if (Number.isFinite(declared) && declared > limit) {
        return NextResponse.json(
          { detail: "Request body too large." },
          { status: 413 },
        )
      }
      try {
        const buf = await request.arrayBuffer()
        if (buf.byteLength > limit) {
          return NextResponse.json(
            { detail: "Request body too large." },
            { status: 413 },
          )
        }
        if (buf.byteLength > 0) {
          if (contentType?.includes("multipart/form-data")) {
            body = buf
          } else {
            body = new TextDecoder().decode(buf)
          }
        }
      } catch {
        // body not readable — proceed without
      }
    }

    const fetchInit: RequestInit = {
      method: request.method,
      headers,
      redirect: "manual",
    }
    if (body !== undefined) {
      fetchInit.body = body
    }

    const res = await fetch(url.toString(), fetchInit)

    const responseBody = await res.arrayBuffer()

    const headerEntries: [string, string][] = []
    res.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "set-cookie") {
        headerEntries.push([key, value])
      }
    })

    const rawSetCookies = res.headers.getSetCookie?.() ?? []
    const cookiesToForward =
      rawSetCookies.length > 0
        ? rawSetCookies
        : (() => {
            const single = res.headers.get("set-cookie")
            if (!single) return []
            return single.split(/,(?=[^;]+=)/).map((c) => c.trim())
          })()

    for (const sc of cookiesToForward) {
      const isSessionActive = sc.startsWith("session_active=")
      if (isSessionActive) {
        headerEntries.push(["Set-Cookie", sc])
      } else {
        const rewritten = sc.replace(/;\s*Path=\//i, "; Path=/api/proxy/")
        headerEntries.push(["Set-Cookie", rewritten])
      }
    }

    return new NextResponse(responseBody, {
      status: res.status,
      headers: headerEntries,
    })
  } catch (err) {
    console.error("PROXY_ERROR:", request.method, request.url, err)
    return NextResponse.json({ detail: "Proxy error" }, { status: 502 })
  }
}
