/**
 * Focused tests for the UX hardening slice: WebSocket frame validation,
 * keyboard pin nudging, and complete admin role counts.
 *
 * @vitest-environment node
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { parseWebSocketMessage } from "@/hooks/useWebSocket"
import { nudgeLocation } from "@/lib/location"
import { admin } from "@/lib/api"

function jsonRes(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe("WebSocket frame validation", () => {
  it("accepts a well-formed frame", () => {
    expect(
      parseWebSocketMessage({
        type: "issue_created",
        payload: { id: 7 },
        timestamp: "2026-11-27T00:00:00Z",
      }),
    ).toEqual({
      type: "issue_created",
      payload: { id: 7 },
      timestamp: "2026-11-27T00:00:00Z",
    })
  })

  it.each([
    null,
    "text",
    42,
    [],
    {},
    { type: 7, payload: {} },
    { type: "", payload: {} },
    { type: "ok", payload: null },
    { type: "ok", payload: [] },
    { type: "ok", payload: {}, timestamp: 123 },
  ])("rejects malformed frame %j", (frame) => {
    expect(parseWebSocketMessage(frame)).toBeNull()
  })
})

describe("keyboard pin control", () => {
  it("nudges in every direction without wrapping past the coordinate bounds", () => {
    expect(nudgeLocation([20, 70], "ArrowUp")?.[0]).toBeGreaterThan(20)
    expect(nudgeLocation([20, 70], "ArrowDown")?.[0]).toBeLessThan(20)
    expect(nudgeLocation([20, 70], "ArrowLeft")?.[1]).toBeLessThan(70)
    expect(nudgeLocation([20, 70], "ArrowRight")?.[1]).toBeGreaterThan(70)
    expect(nudgeLocation([90, 180], "ArrowUp")).toEqual([90, 180])
    expect(nudgeLocation([-90, -180], "ArrowLeft")).toEqual([-90, -180])
  })

  it("ignores unrelated keys", () => {
    expect(nudgeLocation([20, 70], "Enter")).toBeNull()
    expect(nudgeLocation([20, 70], "a")).toBeNull()
  })
})

describe("admin user counts", () => {
  it("pages through the whole table instead of counting only the first page", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonRes({ items: [{ id: 1 }], total: 250 }))
      .mockResolvedValueOnce(jsonRes({ items: [{ id: 101 }], total: 250 }))
      .mockResolvedValueOnce(jsonRes({ items: [{ id: 201 }], total: 250 }))
    vi.stubGlobal("fetch", fetchMock)

    const users = await admin.listAllUsers()

    expect(users).toHaveLength(3)
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/proxy/admin/users?limit=100",
      "/api/proxy/admin/users?skip=100&limit=100",
      "/api/proxy/admin/users?skip=200&limit=100",
    ])
  })

  it("caps the number of pages so a huge table cannot stall the browser", async () => {
    const fetchMock = vi
      .fn()
      // A fresh Response per call: a Response body can only be read once.
      .mockImplementation(() => Promise.resolve(jsonRes({ items: [{ id: 1 }], total: 50_000 })))
    vi.stubGlobal("fetch", fetchMock)

    await admin.listAllUsers()

    expect(fetchMock).toHaveBeenCalledTimes(20)
  })
})
