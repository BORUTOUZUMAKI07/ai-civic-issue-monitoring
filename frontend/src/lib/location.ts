/**
 * Keyboard controls for the map pin. Kept separate from the Leaflet component
 * so the behaviour is testable without a real map or DOM.
 *
 * A fixed angular nudge is deliberate: it works at every zoom level and keeps
 * keyboard control independent of the tile provider's projection.
 */
export const FALLBACK_CENTER: [number, number] = [22.3072, 73.1812]

const NUDGE_DEGREES = 0.0005

/** Return the next pin position for a navigation key, or null for other keys. */
export function nudgeLocation(
  position: readonly [number, number],
  key: string,
): [number, number] | null {
  const [lat, lng] = position
  switch (key) {
    case "ArrowUp":
      return [Math.min(90, lat + NUDGE_DEGREES), lng]
    case "ArrowDown":
      return [Math.max(-90, lat - NUDGE_DEGREES), lng]
    case "ArrowLeft":
      return [lat, Math.max(-180, lng - NUDGE_DEGREES)]
    case "ArrowRight":
      return [lat, Math.min(180, lng + NUDGE_DEGREES)]
    default:
      return null
  }
}
