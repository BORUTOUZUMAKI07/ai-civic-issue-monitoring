import { describe, it, expect, beforeEach, vi } from "vitest"
import {
  pushNotification,
  markAllRead,
  clearNotifications,
  setStreamConnected,
  setStreamEnabled,
  getNotificationState,
} from "@/lib/notifications"

describe("notifications store", () => {
  beforeEach(() => clearNotifications())

  it("stores the newest item first and starts unread", () => {
    pushNotification({ type: "issue_created", title: "First", description: "a" })
    pushNotification({ type: "issue_created", title: "Second", description: "b" })
    const { items } = getNotificationState()
    expect(items).toHaveLength(2)
    expect(items[0].title).toBe("Second")
    expect(items.every((item) => item.read === false)).toBe(true)
  })

  it("marks every item read", () => {
    pushNotification({ type: "issue_created", title: "A", description: "a" })
    pushNotification({ type: "issue_deleted", title: "B", description: "b" })
    markAllRead()
    expect(getNotificationState().items.every((item) => item.read)).toBe(true)
  })

  it("caps the list at 20 items", () => {
    for (let i = 0; i < 25; i += 1) {
      pushNotification({ type: "issue_created", title: `n${i}`, description: "" })
    }
    const { items } = getNotificationState()
    expect(items).toHaveLength(20)
    expect(items[0].title).toBe("n24")
  })

  it("tracks connection and preference independently", () => {
    setStreamConnected(true)
    setStreamEnabled(false)
    expect(getNotificationState().connected).toBe(true)
    expect(getNotificationState().enabled).toBe(false)
  })

  it("resets everything on clear", () => {
    pushNotification({ type: "issue_created", title: "A", description: "a" })
    setStreamConnected(true)
    clearNotifications()
    const state = getNotificationState()
    expect(state.items).toHaveLength(0)
    expect(state.connected).toBe(false)
  })

  it("persists across a reload but not the live connection flag", async () => {
    vi.resetModules()
    const first = await import("@/lib/notifications")
    first.clearNotifications()
    first.pushNotification({
      type: "issue_created",
      title: "Survives refresh",
      description: "x",
    })
    first.setStreamConnected(true)

    // Simulate a fresh page load: a new module instance reads sessionStorage.
    vi.resetModules()
    const reloaded = await import("@/lib/notifications")
    const state = reloaded.getNotificationState()
    expect(state.items[0]?.title).toBe("Survives refresh")
    expect(state.connected).toBe(false)

    reloaded.clearNotifications()
  })
})
