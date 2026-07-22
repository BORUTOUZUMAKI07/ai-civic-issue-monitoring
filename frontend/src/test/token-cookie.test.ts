import { describe, it, expect } from "vitest"
import { setTokenCookie, setRefreshTokenCookie, clearTokenCookies } from "@/lib/token-cookie"

describe("token-cookie", () => {
  it("sets access token cookie", () => {
    setTokenCookie("test-token")
    expect(document.cookie).toContain("access_token=test-token")
  })

  it("sets refresh token cookie", () => {
    setRefreshTokenCookie("test-refresh")
    expect(document.cookie).toContain("refresh_token=test-refresh")
  })

  it("clears cookies", () => {
    setTokenCookie("test-token")
    setRefreshTokenCookie("test-refresh")
    clearTokenCookies()
    expect(document.cookie).not.toContain("access_token=test-token")
    expect(document.cookie).not.toContain("refresh_token=test-refresh")
  })
})
