/**
 * Correlation IDs must be UUIDs before they ever leave the browser. The
 * backend deliberately replaces malformed header values, which would silently
 * break browser → BFF → API log joins.
 *
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest"

import { isValidCorrelationId, newCorrelationId } from "@/lib/correlation"

describe("correlation ids", () => {
  it("generates a valid UUID even without crypto.randomUUID", () => {
    const id = newCorrelationId()
    expect(isValidCorrelationId(id)).toBe(true)
  })

  it("accepts canonical UUIDs and rejects arbitrary text", () => {
    expect(isValidCorrelationId("3f2504e0-4f89-41d3-9a0c-0305e82c3301")).toBe(true)
    expect(isValidCorrelationId("correlation-1")).toBe(false)
  })
})
