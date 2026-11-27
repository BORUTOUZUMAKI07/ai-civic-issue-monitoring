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

function signalOf(fetchMock: ReturnType<typeof vi.fn>, call: number): AbortSignal {
  return fetchMock.mock.calls[call][1].signal as AbortSignal
}

function pendingFetch(signal: AbortSignal): Promise<Response> {
  return new Promise((_resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason ?? new Error("aborted"))
      return
    }
    signal.addEventListener("abort", () => reject(signal.reason ?? new Error("aborted")), { once: true })
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

    expect(timeoutSpy).toHaveBeenCalledWith(35_000)
    expect(signalOf(fetchMock, 0)).toBe(controller.signal)
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

  it("honors a caller signal without dropping the API timeout", async () => {
    const caller = new AbortController()
    const timeout = new AbortController()
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal)
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) =>
      pendingFetch(init.signal as AbortSignal)
    )
    vi.stubGlobal("fetch", fetchMock)

    const request = apiFetch("/slow", { signal: caller.signal })
    const combined = signalOf(fetchMock, 0)
    expect(combined).not.toBe(caller.signal)
    expect(combined).not.toBe(timeout.signal)

    caller.abort(new DOMException("caller cancelled", "AbortError"))
    await expect(request).rejects.toMatchObject({ name: "AbortError", message: "caller cancelled" })
    expect(timeout.signal.aborted).toBe(false)
  })

  it("still times out when the caller supplies its own signal", async () => {
    const caller = new AbortController()
    const timeout = new AbortController()
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal)
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) =>
      pendingFetch(init.signal as AbortSignal)
    )
    vi.stubGlobal("fetch", fetchMock)

    const request = apiFetch("/slow", { signal: caller.signal })
    timeout.abort(new DOMException("timed out", "TimeoutError"))

    await expect(request).rejects.toMatchObject({ name: "TimeoutError" })
    expect(caller.signal.aborted).toBe(false)
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
    expect(signalOf(fetchMock, 1)).toBe(controller.signal)
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
    expect(signalOf(fetchMock, 0)).toBe(controller.signal)
    expect(signalOf(fetchMock, 1)).toBe(controller.signal)
    expect(signalOf(fetchMock, 2)).toBe(controller.signal)
  })

  it("keeps the caller signal on the retry after a refresh", async () => {
    const caller = new AbortController()
    const timeout = new AbortController()
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(timeout.signal)
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockImplementationOnce((_url: string, init: RequestInit) =>
        pendingFetch(init.signal as AbortSignal)
      )
    vi.stubGlobal("fetch", fetchMock)

    const request = apiFetch("/issues", { signal: caller.signal })
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))

    const retrySignal = signalOf(fetchMock, 2)
    expect(retrySignal).not.toBe(caller.signal)
    caller.abort(new DOMException("caller cancelled", "AbortError"))
    await expect(request).rejects.toMatchObject({ name: "AbortError" })
    expect(retrySignal.aborted).toBe(true)
  })
})
