import { describe, it, expect } from "vitest"
import { safeInternalPath } from "@/lib/safe-redirect"

describe("safeInternalPath", () => {
  it("passes through same-site absolute paths", () => {
    expect(safeInternalPath("/issues")).toBe("/issues")
    expect(safeInternalPath("/issues/12/edit?tab=photos")).toBe("/issues/12/edit?tab=photos")
    expect(safeInternalPath("/")).toBe("/")
  })

  it("falls back when the value is missing or empty", () => {
    expect(safeInternalPath(null)).toBe("/dashboard")
    expect(safeInternalPath(undefined)).toBe("/dashboard")
    expect(safeInternalPath("")).toBe("/dashboard")
  })

  it("rejects absolute and scheme URLs", () => {
    expect(safeInternalPath("https://evil.example")).toBe("/dashboard")
    expect(safeInternalPath("http://evil.example/x")).toBe("/dashboard")
    expect(safeInternalPath("javascript:alert(1)")).toBe("/dashboard")
  })

  it("rejects scheme-relative and backslash-smuggled targets", () => {
    expect(safeInternalPath("//evil.example")).toBe("/dashboard")
    expect(safeInternalPath("/\\evil.example")).toBe("/dashboard")
    expect(safeInternalPath("//evil.example/%2e%2e/steal")).toBe("/dashboard")
  })

  it("honours a custom fallback", () => {
    expect(safeInternalPath(null, "/login")).toBe("/login")
    expect(safeInternalPath("//evil.example", "/issues")).toBe("/issues")
  })
})
