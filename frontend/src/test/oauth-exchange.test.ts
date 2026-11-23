/**
 * The OAuth callback now redirects with a one-time code instead of tokens.
 * These tests pin the client half of that handoff: the code is POSTed to the
 * exchange endpoint, and a rejected code is surfaced as-is rather than being
 * swallowed by the session-refresh bounce.
 *
 * @vitest-environment node
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { auth } from "@/lib/api"

const CODE = "c".repeat(43)

function jsonRes(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

describe("OAuth handoff exchange", () => {
  afterEach(() => vi.unstubAllGlobals())

  it("posts the code to the public exchange endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonRes({ detail: "Login successful", redirect: "/issues", user: null })
    )
    vi.stubGlobal("fetch", fetchMock)

    const result = await auth.exchangeOauth(CODE)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe("/api/proxy/auth/oauth/exchange")
    expect(init.method).toBe("POST")
    expect(JSON.parse(String(init.body))).toEqual({ code: CODE })
    expect(result.redirect).toBe("/issues")
  })

  it("does not trigger a refresh retry when the code is rejected", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonRes({ detail: "invalid code" }, 401))
    vi.stubGlobal("fetch", fetchMock)

    await expect(auth.exchangeOauth(CODE)).rejects.toThrow("invalid code")
    // A 401 here is a bad one-time secret, not an expired session: retrying
    // /auth/refresh would mint new cookies for an unrelated signed-in user.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
