/**
 * Browser error forwarding: the browser reports to our BFF, and the BFF posts
 * to the backend's private intake. Neither half may leak a vendor key or a
 * query string (OAuth codes and reset tokens live there).
 *
 * @vitest-environment node
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { NextRequest } from "next/server"

import { reportClientError } from "@/lib/client-errors"

const VALID_CORRELATION_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(new Response(null, { status: 202 }))
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe("client error reporter", () => {
  it("posts a bounded report to the BFF without query strings", async () => {
    vi.stubGlobal("window", { location: { pathname: "/issues?code=oauth-secret" } })

    reportClientError(new Error("boom"), {
      event_type: "api_error",
      api_path: "/api/v1/auth/login?code=oauth-secret",
      method: "POST",
      status_code: 401,
      correlation_id: VALID_CORRELATION_ID,
    })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/client-errors")
    expect(init.headers).toMatchObject({ "X-Correlation-ID": VALID_CORRELATION_ID })
    const body = JSON.parse(init.body as string)
    expect(body).toMatchObject({
      event_type: "api_error",
      message: "boom",
      error_name: "Error",
      path: "/issues",
      api_path: "/api/v1/auth/login",
      method: "POST",
      status_code: 401,
      correlation_id: VALID_CORRELATION_ID,
    })
    expect(JSON.stringify(body)).not.toContain("oauth-secret")
  })

  it("drops malformed correlation ids instead of forwarding them", async () => {
    vi.stubGlobal("window", { location: { pathname: "/issues" } })

    reportClientError(new Error("boom"), { correlation_id: "correlation-1" })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers).not.toHaveProperty("X-Correlation-ID")
    expect(JSON.parse(init.body as string)).not.toHaveProperty("correlation_id")
  })

  it("stays silent when the browser has no window", () => {
    reportClientError(new Error("server render"))
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("client error BFF bridge", () => {
  it("forwards the report to the backend intake using BACKEND_URL", async () => {
    vi.stubEnv("BACKEND_URL", "http://backend.test")
    const { POST } = await import("@/app/api/client-errors/route")

    const request = new NextRequest("http://localhost/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_type: "react_error", message: "boom" }),
    })
    const response = await POST(request)

    expect(response.status).toBe(202)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe("http://backend.test/api/v1/observability/client-errors")
  })

  it("forwards a valid report correlation id as X-Correlation-ID", async () => {
    vi.stubEnv("BACKEND_URL", "http://backend.test")
    const { POST } = await import("@/app/api/client-errors/route")

    const request = new NextRequest("http://localhost/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: "boom", correlation_id: VALID_CORRELATION_ID }),
    })
    await POST(request)

    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({
      "X-Correlation-ID": VALID_CORRELATION_ID,
    })
  })

  it("ignores a malformed body id and a caller-supplied header", async () => {
    vi.stubEnv("BACKEND_URL", "http://backend.test")
    const { POST } = await import("@/app/api/client-errors/route")

    const request = new NextRequest("http://localhost/api/client-errors", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-ID": "caller-id",
      },
      body: JSON.stringify({ message: "boom", correlation_id: "body-id" }),
    })
    await POST(request)

    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty("X-Correlation-ID")
  })
})
