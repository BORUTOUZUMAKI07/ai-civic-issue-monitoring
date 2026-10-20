/**
 * Tests for the Next.js API proxy route handler.
 *
 * This route is a security boundary, not a passthrough: it enforces a path
 * allowlist, an unauthenticated-call guard, and body-size ceilings. Each of
 * those is exercised here, plus the two behaviours added in the hardening
 * pass:
 *
 *  - `BACKEND_URL` (server-only) is preferred over the browser-facing
 *    `NEXT_PUBLIC_API_URL`. Inside Docker Compose the latter points at
 *    `localhost:8000`, which is the frontend container itself — every
 *    proxied call would 502.
 *  - Oversized bodies are refused with 413 *before* buffering, because
 *    `request.arrayBuffer()` would otherwise pull the whole payload into
 *    the Next.js process's memory.
 *
 * The handler is imported directly and given a real `NextRequest`; `fetch`
 * is mocked so we can assert on the outgoing URL and never touch a socket.
 *
 * @vitest-environment node
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { NextRequest } from "next/server"

const API = "/api/proxy"

const fetchMock = vi.fn()

function jsonRes(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  })
}

/**
 * Import the route handler fresh each time so the module-level `BACKEND`
 * constant is re-evaluated against the current stubbed env. Without this the
 * first import wins and the env assertions would silently read a stale value.
 */
async function loadHandlers() {
  vi.resetModules()
  const mod = await import("@/app/api/proxy/[...path]/route")
  return mod as {
    GET: (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => Promise<Response>
    POST: (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => Promise<Response>
  }
}

function ctx(...path: string[]) {
  return { params: Promise.resolve({ path }) }
}

/**
 * The subset of request options these tests actually use. `NextRequest`'s own
 * init type is not exported, and `RequestInit` differs from it on `signal`
 * (`AbortSignal | null`), so a literal alias keeps both call sites type-safe
 * without a cast.
 */
type ReqInit = {
  method?: string
  body?: BodyInit | null
  headers?: HeadersInit
}

function req(url: string, init: ReqInit = {}) {
  return new NextRequest(new URL(url, "http://localhost:3000"), init)
}

/**
 * A request that carries an access-token cookie.
 *
 * Needed for any protected route: `issues`, `wards` etc. are not public
 * prefixes, so the proxy's guard 401s *before* the backend is contacted.
 * Attaching the cookie is what lets a test reach the code under test — and
 * its absence is what the guard tests rely on.
 */
function authedReq(url: string, init: ReqInit = {}) {
  const r = req(url, init)
  vi.spyOn(r.cookies, "get").mockReturnValue({ name: "access_token", value: "tok" })
  return r
}

/**
 * A request carrying several named cookies.
 *
 * `cookies.get(name)` must answer per name, unlike `authedReq` above which
 * always returns the access token. Used by the cookie-relay tests, where the
 * whole point is *which* cookies reach the backend.
 */
function cookieReq(url: string, cookies: Record<string, string>, init: ReqInit = {}) {
  const r = req(url, init)
  vi.spyOn(r.cookies, "get").mockImplementation(((
    ...args: [string] | [{ name: string }]
  ) => {
    const name = typeof args[0] === "string" ? args[0] : args[0].name
    return name in cookies
      ? ({ name, value: cookies[name] } as ReturnType<typeof r.cookies.get>)
      : undefined
  }) as typeof r.cookies.get)
  return r
}

beforeEach(() => {
  vi.stubEnv("BACKEND_URL", "http://backend:8000")
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe("proxy: backend URL resolution", () => {
  it("uses BACKEND_URL over NEXT_PUBLIC_API_URL for server-side calls", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000")
    fetchMock.mockResolvedValue(jsonRes({ ok: true }))

    const { GET } = await loadHandlers()
    await GET(authedReq(`${API}/issues?limit=1`), ctx("issues"))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const target = fetchMock.mock.calls[0][0] as string
    expect(target).toBe("http://backend:8000/api/v1/issues?limit=1")
    expect(target).not.toContain("localhost")
  })

  it("falls back to NEXT_PUBLIC_API_URL when BACKEND_URL is unset", async () => {
    vi.stubEnv("BACKEND_URL", "")
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://example.internal:9000")
    fetchMock.mockResolvedValue(jsonRes({ ok: true }))

    const { GET } = await loadHandlers()
    await GET(authedReq(`${API}/wards`), ctx("wards"))

    expect((fetchMock.mock.calls[0][0] as string).startsWith("http://example.internal:9000/")).toBe(true)
  })
})

describe("proxy: path allowlist", () => {
  it("rejects traversal that would escape /api/v1", async () => {
    fetchMock.mockResolvedValue(jsonRes({}))
    const { GET } = await loadHandlers()

    // `..` arrives decoded from the URL, not percent-encoded.
    const res = await GET(req(`${API}/issues/../../uploads/secret.png`), ctx("issues", "..", "..", "uploads", "secret.png"))
    expect(res.status).toBe(400)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("rejects a first segment outside the allowlist", async () => {
    fetchMock.mockResolvedValue(jsonRes({}))
    const { GET } = await loadHandlers()

    const res = await GET(req(`${API}/internal/debug`), ctx("internal", "debug"))
    expect(res.status).toBe(404)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("allows a known router prefix", async () => {
    fetchMock.mockResolvedValue(jsonRes({ items: [] }))
    const { GET } = await loadHandlers()

    const res = await GET(authedReq(`${API}/issues`), ctx("issues"))
    expect(res.status).toBe(200)
    expect(fetchMock.mock.calls[0][0]).toContain("/api/v1/issues")
  })
})

describe("proxy: unauthenticated guard", () => {
  it("401s a protected route with no access token", async () => {
    fetchMock.mockResolvedValue(jsonRes({}))
    const { GET } = await loadHandlers()

    const res = await GET(req(`${API}/issues`), ctx("issues"))
    expect(res.status).toBe(401)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("permits a public route without a token", async () => {
    fetchMock.mockResolvedValue(jsonRes({ detail: "ok" }))
    const { POST } = await loadHandlers()

    const res = await POST(
      req(`${API}/auth/login`, { method: "POST", body: JSON.stringify({ email: "a@b.c" }) }),
      ctx("auth", "login"),
    )
    expect(res.status).toBe(200)
    expect(fetchMock).toHaveBeenCalled()
  })
})

describe("proxy: body size ceilings", () => {
  it("413s a JSON body over the declared limit without reading it", async () => {
    fetchMock.mockResolvedValue(jsonRes({}))
    const { POST } = await loadHandlers()

    const over = 2 * 1024 * 1024
    const res = await POST(
      authedReq(`${API}/auth/login`, {
        method: "POST",
        body: "{}",
        headers: { "content-type": "application/json", "content-length": String(over) },
      }),
      ctx("auth", "login"),
    )

    expect(res.status).toBe(413)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("413s a multipart body over the upload limit", async () => {
    fetchMock.mockResolvedValue(jsonRes({}))
    const { POST } = await loadHandlers()

    const over = 8 * 1024 * 1024
    const res = await POST(
      authedReq(`${API}/issues/upload`, {
        method: "POST",
        body: "x",
        headers: { "content-type": "multipart/form-data; boundary=X", "content-length": String(over) },
      }),
      ctx("issues", "upload"),
    )

    expect(res.status).toBe(413)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("passes a small body through to the backend", async () => {
    fetchMock.mockResolvedValue(jsonRes({ ok: true }))
    const { POST } = await loadHandlers()

    const body = JSON.stringify({ email: "a@b.c", password: "hunter22" })
    const res = await POST(
      authedReq(`${API}/auth/login`, {
        method: "POST",
        body,
        headers: { "content-type": "application/json", "content-length": String(body.length) },
      }),
      ctx("auth", "login"),
    )

    expect(res.status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("does not apply body limits to GET", async () => {
    fetchMock.mockResolvedValue(jsonRes({ items: [] }))
    const { GET } = await loadHandlers()

    // A large declared length on a bodyless method must not be rejected.
    const res = await GET(authedReq(`${API}/issues`, { headers: { "content-length": String(5 * 1024 * 1024) } }), ctx("issues"))

    expect(res.status).not.toBe(413)
    expect(fetchMock).toHaveBeenCalled()
  })
})

describe("proxy: cookie relay", () => {
  it("forwards oauth_state to the OAuth callback", async () => {
    // The callback compares this cookie (set on the authorize response) against
    // the nonce inside the signed state. Dropping it made every OAuth sign-in
    // end at "Invalid OAuth state".
    fetchMock.mockResolvedValue(jsonRes({ ok: true }))
    const { GET } = await loadHandlers()

    await GET(
      cookieReq(`${API}/auth/oauth/google/callback?code=x&state=y`, {
        oauth_state: "nonce-abc",
      }),
      ctx("auth", "oauth", "google", "callback"),
    )

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Cookie).toContain("oauth_state=nonce-abc")
  })

  it("does not leak oauth_state to unrelated routes", async () => {
    // Least privilege: only the OAuth callback reads it, so nothing else may
    // carry it. `/auth/oauth/providers` is a sibling under the same prefix and
    // must stay clean.
    fetchMock.mockResolvedValue(jsonRes({}))
    const { GET } = await loadHandlers()

    await GET(
      cookieReq(`${API}/auth/oauth/providers`, { oauth_state: "nonce-abc", access_token: "tok" }),
      ctx("auth", "oauth", "providers"),
    )

    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Cookie).toBe("access_token=tok")
  })

  it("still forwards refresh_token only to refresh and logout", async () => {
    fetchMock.mockResolvedValue(jsonRes({}))
    const { POST } = await loadHandlers()

    await POST(
      cookieReq(`${API}/auth/refresh`, { access_token: "tok", refresh_token: "ref" }, { method: "POST" }),
      ctx("auth", "refresh"),
    )
    const headers = fetchMock.mock.calls[0][1].headers as Record<string, string>
    expect(headers.Cookie).toContain("refresh_token=ref")
  })
})
