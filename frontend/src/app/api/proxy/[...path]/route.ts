import { NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

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

async function proxy(request: NextRequest, context: RouteContext) {
  try {
    const { path } = await context.params
    const accessToken = request.cookies.get("access_token")?.value

    const targetPath = `/api/v1/${path.join("/")}`
    const url = new URL(targetPath, BACKEND)
    url.search = request.nextUrl.search

    const headers: Record<string, string> = {}
    if (accessToken) {
      headers["Authorization"] = `Bearer ${accessToken}`
    }

    const contentType = request.headers.get("content-type")
    if (contentType) {
      headers["Content-Type"] = contentType
    }

    let body: ArrayBuffer | string | undefined
    if (request.method !== "GET" && request.method !== "HEAD") {
      try {
        const buf = await request.arrayBuffer()
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
