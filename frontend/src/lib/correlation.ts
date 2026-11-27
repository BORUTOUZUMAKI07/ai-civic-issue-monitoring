/**
 * Correlation ID helpers shared by the API client and the browser-error bridge.
 *
 * The backend only accepts UUID-shaped IDs in `X-Correlation-ID`; anything else
 * is replaced with a new UUID. Generating and validating on the client keeps the
 * browser → BFF → backend → OTLP join intact.
 */

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function formatUuid(bytes: Uint8Array): string {
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function isValidCorrelationId(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value)
}

export function newCorrelationId(): string {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID()
    if (typeof crypto.getRandomValues === "function") {
      const bytes = crypto.getRandomValues(new Uint8Array(16))
      bytes[6] = (bytes[6]! & 0x0f) | 0x40
      bytes[8] = (bytes[8]! & 0x3f) | 0x80
      return formatUuid(bytes)
    }
  }

  // Very old browsers without Web Crypto still get a valid UUID rather than a
  // placeholder the backend would have to discard.
  const bytes = new Uint8Array(16)
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  return formatUuid(bytes)
}
