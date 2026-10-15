"use client";

import { useSyncExternalStore } from "react";

/**
 * Client-side notification centre.
 *
 * A single WebSocket connection (owned by `<IssueStream />`) feeds this store,
 * and every consumer — the header bell and the issues page's connection badge —
 * reads from the same module-level source of truth via `useSyncExternalStore`.
 * Keeping it in one place is what lets the bell and the feed agree on both the
 * event list and whether the stream is actually up, instead of each widget
 * opening its own socket.
 */
export interface NotificationItem {
  id: string;
  /** Backend event type, e.g. "issue_created". */
  type: string;
  title: string;
  description: string;
  /** Where clicking the notification should navigate. */
  href?: string;
  createdAt: string;
  read: boolean;
}

export interface NotificationState {
  items: NotificationItem[];
  /** True while the WebSocket is open. */
  connected: boolean;
  /** True when real-time alerts are switched on in preferences. */
  enabled: boolean;
}

/** Bounded so a long-lived session cannot grow the list without limit. */
const MAX_ITEMS = 20;

const STORAGE_KEY = "civicpulse:notifications";

const EMPTY: NotificationState = { items: [], connected: false, enabled: true };

let state: NotificationState = EMPTY;
let hydrated = false;
const listeners = new Set<() => void>();

/**
 * Restore the previous session's notifications. `sessionStorage` (not
 * `localStorage`) is deliberate: the list survives an in-app refresh, which is
 * the case that matters, but does not linger for the next browser session or
 * across account switches on a shared machine. `connected` is never persisted —
 * it is a live fact, not stored state.
 */
function hydrate(): void {
  if (hydrated) return;
  hydrated = true;
  if (typeof window === "undefined") return;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as Partial<NotificationState>;
    state = {
      items: Array.isArray(parsed.items) ? parsed.items.slice(0, MAX_ITEMS) : [],
      connected: false,
      enabled: parsed.enabled ?? true,
    };
  } catch {
    // Corrupt storage should never break the UI.
  }
}

function persist(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ items: state.items, enabled: state.enabled })
    );
  } catch {
    /* ignore quota / private-mode errors */
  }
}

function commit(next: NotificationState, shouldPersist = true): void {
  state = next;
  if (shouldPersist) persist();
  listeners.forEach((listener) => listener());
}

export function getNotificationState(): NotificationState {
  hydrate();
  return state;
}

export function pushNotification(
  input: Omit<NotificationItem, "id" | "createdAt" | "read"> & {
    id?: string;
    createdAt?: string;
  }
): void {
  hydrate();
  const item: NotificationItem = {
    ...input,
    id: input.id ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    createdAt: input.createdAt ?? new Date().toISOString(),
    read: false,
  };
  commit({ ...state, items: [item, ...state.items].slice(0, MAX_ITEMS) });
}

export function markAllRead(): void {
  hydrate();
  if (state.items.every((item) => item.read)) return;
  commit({
    ...state,
    items: state.items.map((item) => (item.read ? item : { ...item, read: true })),
  });
}

export function setStreamConnected(connected: boolean): void {
  if (state.connected === connected) return;
  // Connection status is transient, so it is not written back to storage.
  commit({ ...state, connected }, false);
}

export function setStreamEnabled(enabled: boolean): void {
  hydrate();
  if (state.enabled === enabled) return;
  commit({ ...state, enabled });
}

export function clearNotifications(): void {
  hydrated = true;
  commit({ ...EMPTY }, false);
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getServerSnapshot(): NotificationState {
  return EMPTY;
}

export function useNotifications(): NotificationState {
  return useSyncExternalStore(subscribe, getNotificationState, getServerSnapshot);
}
