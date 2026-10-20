"use client";

import { useEffect, useRef } from "react";

/**
 * Attach an IntersectionObserver to a sentinel element and fire `onIntersect`
 * whenever it scrolls into view.
 *
 * This is the "load on scroll" primitive the list pages share: a sentinel
 * rendered after the last row is observed, and when it appears the page appends
 * the next slice. The observer disconnects while `disabled` is true (no more
 * pages, or a request already in flight), so a list at its end never spins.
 *
 * Returns the sentinel ref to spread onto a trailing <div>.
 */
export function useInfiniteScroll(
  onIntersect: () => void,
  { disabled = false, rootMargin = "200px" }: { disabled?: boolean; rootMargin?: string } = {}
) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  // Keep the latest callback without re-creating the observer every render --
  // the observer only needs to exist once per `disabled` transition. The ref is
  // updated in an effect, not during render, so its value never changes as a
  // side effect of rendering.
  const callbackRef = useRef(onIntersect);

  useEffect(() => {
    callbackRef.current = onIntersect;
  }, [onIntersect]);

  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || disabled) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          callbackRef.current();
        }
      },
      { rootMargin }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [disabled, rootMargin]);

  return sentinelRef;
}
