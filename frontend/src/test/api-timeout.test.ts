/**
 * Browser API requests must never leave a page spinning in a loading skeleton.
 *
 * @vitest-environment node
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { apiFetch } from "@/lib/api"

function jsonRes(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe("browser API timeouts", () => {
  it("bounds every proxied request with an abort signal", async () => {
    const controller = new AbortController()
    const timeoutSpy = vi.spyOn(AbortSignal, "timeout").mockReturnValue(controller.signal)
    const fetchMock = vi.fn().mockResolvedValue(jsonRes({ ok: true }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(apiFetch("/ping")).resolves.toEqual({ ok: true })

    expect(timeoutSpy).toHaveBeenCalledWith(10_000)
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
  })

  it("rejects instead of hanging when the request times out", async () => {
    const reason = new DOMException("timed out", "TimeoutError")
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(AbortSignal.abort(reason))
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      const signal = init.signal as AbortSignal
      return Promise.reject(signal.reason ?? reason)
    })
    vi.stubGlobal("fetch", fetchMock)

    await expect(apiFetch("/ping")).rejects.toMatchObject({ name: "TimeoutError" })
  })

  it("bounds the shared refresh call after a 401", async () => {
    const controller = new AbortController()
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(controller.signal)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockImplementationOnce((_url: string, init: RequestInit) => {
        const signal = init.signal as AbortSignal
        return Promise.reject(signal.reason ?? new Error("refresh timeout"))
      })
    vi.stubGlobal("fetch", fetchMock)

    await expect(apiFetch("/issues")).rejects.toThrow("Session expired. Please login again.")

    expect(fetchMock.mock.calls[1][0]).toBe("/api/proxy/auth/refresh")
    expect(fetchMock.mock.calls[1][1].signal).toBe(controller.signal)
  })

  it("bounds the retry fetch after a successful refresh", async () => {
    const controller = new AbortController()
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(controller.signal)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(jsonRes({ items: [] }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(apiFetch("/issues")).resolves.toEqual({ items: [] })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal)
    expect(fetchMock.mock.calls[1][1].signal).toBe(controller.signal)
    expect(fetchMock.mock.calls[2][1].signal).toBe(controller.signal)
  })
})
