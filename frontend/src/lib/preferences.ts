"use client";

import { useSyncExternalStore } from "react";

/**
 * Client-side UI preferences.
 *
 * These are local to the browser (real-time alerts on/off, email digest
 * preference) — not a copy of anything the server owns — so localStorage is the
 * right home for them. A module-level cache plus a subscriber set gives every
 * consumer one shared, reactive source of truth via `useSyncExternalStore`,
 * so the settings toggle and the issues feed cannot drift apart.
 */
export interface Preferences {
  realtimeAlerts: boolean;
  emailNotifications: boolean;
}

const STORAGE_KEY = "civicpulse:preferences";

const DEFAULTS: Preferences = {
  realtimeAlerts: true,
  emailNotifications: true,
};

let cache: Preferences | null = null;
const listeners = new Set<() => void>();

function read(): Preferences {
  if (typeof window === "undefined") return DEFAULTS;
  if (cache) return cache;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    cache = raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<Preferences>) } : DEFAULTS;
  } catch {
    // Corrupt or unavailable storage should never break the UI.
    cache = DEFAULTS;
  }
  return cache;
}

export function getPreferences(): Preferences {
  return read();
}

export function setPreference<K extends keyof Preferences>(
  key: K,
  value: Preferences[K]
): void {
  const next = { ...read(), [key]: value };
  cache = next;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      /* ignore quota / private-mode errors */
    }
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function usePreferences(): Preferences {
  return useSyncExternalStore(
    subscribe,
    getPreferences,
    () => DEFAULTS
  );
}
