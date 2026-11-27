/**
 * Direct-to-object-storage upload flow. The important assertion is that image
 * bytes go to the presigned Neon URL, while the BFF only receives the object
 * key and its signed handoff token — Vercel never sees a multipart photo.
 *
 * @vitest-environment node
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { issues, resolution } from "@/lib/api"

const fetchMock = vi.fn()

const PRESIGNED = {
  method: "PUT" as const,
  upload_url: "https://storage.example.com/presigned-put",
  image_url: "/uploads/issues/abc.jpg",
  upload_token: "token-abc",
  required_headers: { "Content-Type": "image/jpeg" },
  expires_in: 900,
}

const ISSUE = {
  id: 1,
  issue_type: "pothole",
  confidence: 0.9,
  severity: 3,
  status: "reported",
  latitude: 1,
  longitude: 2,
  description: "desc",
  image_url: PRESIGNED.image_url,
  review_required: false,
  ward_id: 1,
  reporter_id: 1,
  created_at: "2026-01-01T00:00:00Z",
  assigned_to: null,
  engineer_name: null,
  model_used: null,
  probabilities: null,
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  })
}

function photo() {
  return new File(["fake-image-bytes"], "pothole.jpg", { type: "image/jpeg" })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("direct uploads", () => {
  it("PUTs bytes to Neon and sends only the key/token through the BFF", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(PRESIGNED))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(ISSUE))

    const result = await issues.upload(photo(), 1, 2, "desc", false, "key-1")

    expect(result.id).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)

    const presignCall = fetchMock.mock.calls[0]
    expect(presignCall[0]).toBe("/api/proxy/uploads/presign")
    expect(JSON.parse(presignCall[1].body)).toMatchObject({
      filename: "pothole.jpg",
      purpose: "issue",
      idempotency_key: "key-1",
    })

    const putCall = fetchMock.mock.calls[1]
    expect(putCall[0]).toBe(PRESIGNED.upload_url)
    expect(putCall[1].method).toBe("PUT")
    expect(putCall[1].headers).toEqual(PRESIGNED.required_headers)
    expect(putCall[1].body).toBeInstanceOf(File)

    const createCall = fetchMock.mock.calls[2]
    expect(createCall[0]).toBe("/api/proxy/issues/upload")
    expect(createCall[1].headers).toEqual({
      "Idempotency-Key": "key-1",
      "X-Correlation-ID": expect.stringMatching(/^[0-9a-f-]{36}$/i),
    })
    const form = createCall[1].body as FormData
    expect(form.get("file")).toBeNull()
    expect(form.get("image_url")).toBe(PRESIGNED.image_url)
    expect(form.get("upload_token")).toBe(PRESIGNED.upload_token)
  })

  it("falls back to multipart when presign is unavailable", async () => {
    fetchMock
      .mockRejectedValueOnce(new Error("501 Direct uploads require object storage"))
      .mockResolvedValueOnce(jsonResponse(ISSUE))

    await issues.upload(photo(), 1, 2)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const form = fetchMock.mock.calls[1][1].body as FormData
    expect(form.get("file")).toBeInstanceOf(File)
  })

  it("uses a resolution-scoped presign for proof photos", async () => {
    const resolutionPresign = {
      ...PRESIGNED,
      image_url: "/uploads/resolutions/abc.jpg",
    }
    fetchMock
      .mockResolvedValueOnce(jsonResponse(resolutionPresign))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        jsonResponse({ id: 5, issue_id: 1, status: "resolved", message: "ok", resolved_at: "2026-01-01T00:00:00Z" })
      )

    await resolution.resolve(1, photo(), "fixed")

    const presignBody = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(presignBody.purpose).toBe("resolution")
    const form = fetchMock.mock.calls[2][1].body as FormData
    expect(form.get("file")).toBeNull()
    expect(form.get("after_image_url")).toBe(resolutionPresign.image_url)
    expect(form.get("notes")).toBe("fixed")
  })
})
