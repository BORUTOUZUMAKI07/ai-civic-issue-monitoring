"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useWebSocket, type WebSocketMessage } from "@/hooks/useWebSocket";
import { usePreferences } from "@/lib/preferences";
import { auth } from "@/lib/api";
import { humanize } from "@/lib/format";
import {
  pushNotification,
  setStreamConnected,
  setStreamEnabled,
} from "@/lib/notifications";

// Review actions arrive as machine tokens ("approve", "change_type"); map them to
// readable copy rather than interpolating the raw value.
const REVIEW_TITLES: Record<string, string> = {
  approve: "Issue approved",
  reject: "Issue rejected",
  change_type: "Issue reclassified",
};

const REVIEW_VERBS: Record<string, string> = {
  approve: "approved",
  reject: "rejected",
  change_type: "reclassified",
};

interface IssueEvent {
  title: string;
  description: string;
  href: string;
  tone: "info" | "success";
  /** Whether this event also deserves a transient toast, not just a bell entry. */
  toast: boolean;
}

/** Turn a raw socket frame into notification copy, or null for unknown frames. */
function describeEvent(msg: WebSocketMessage): IssueEvent | null {
  const payload = msg.payload ?? {};
  const id = payload.id;
  const href = id != null ? `/issues/${id}` : "/issues";
  const type = humanize(String(payload.issue_type ?? "issue"));

  switch (msg.type) {
    case "issue_created":
      return {
        title: "New issue reported",
        description: `${type} · severity ${payload.severity ?? "?"}`,
        href,
        tone: "info",
        toast: true,
      };
    case "issue_reviewed": {
      const action = String(payload.action ?? "reviewed");
      return {
        title: REVIEW_TITLES[action] ?? "Issue reviewed",
        description: `${type} was ${
          REVIEW_VERBS[action] ?? "reviewed"
        } in the review queue`,
        href,
        tone: action === "approve" ? "success" : "info",
        toast: true,
      };
    }
    case "issue_deleted":
      return {
        title: "Issue deleted",
        description:
          id != null ? `Report #${id} was removed` : "A report was removed",
        href: "/issues",
        tone: "info",
        // Deletions stay in the bell only — a toast for a removal is more noise
        // than signal.
        toast: false,
      };
    default:
      return null;
  }
}

/**
 * Owns the single application WebSocket.
 *
 * Mounted once in the authenticated shell, it feeds the notification store and
 * keeps issue-derived queries fresh. Because it lives above the pages, the
 * header bell and the issues feed share one connection instead of each opening
 * their own — and events are still received while the user is on the dashboard,
 * map or admin screens, which the old per-page socket could not do.
 */
export function IssueStream() {
  const qc = useQueryClient();
  const router = useRouter();
  const { realtimeAlerts } = usePreferences();

  const getToken = useCallback(async () => {
    try {
      const { ticket } = await auth.wsTicket();
      return ticket;
    } catch {
      return null;
    }
  }, []);

  const onMessage = useCallback(
    (msg: WebSocketMessage) => {
      if (msg.type === "pong") return;

      // Any issue event can affect the list, the detail view and the
      // dashboard/heatmap aggregates, so refresh them all.
      qc.invalidateQueries({ queryKey: ["issues"] });
      qc.invalidateQueries({ queryKey: ["issue"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
      qc.invalidateQueries({ queryKey: ["heatmap"] });
      qc.invalidateQueries({ queryKey: ["review-queue"] });

      const event = describeEvent(msg);
      if (!event) return;

      pushNotification({
        type: msg.type,
        title: event.title,
        description: event.description,
        href: event.href,
      });

      if (event.toast) {
        const options = {
          description: event.description,
          action: { label: "View", onClick: () => router.push(event.href) },
        };
        if (event.tone === "success") toast.success(event.title, options);
        else toast.info(event.title, options);
      }
    },
    [qc, router]
  );

  const onConnect = useCallback(() => setStreamConnected(true), []);
  const onDisconnect = useCallback(() => setStreamConnected(false), []);

  const wsBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const wsUrl = wsBase.replace(/^http/, "ws") + "/api/v1/ws/issues";

  useWebSocket({
    url: wsUrl,
    getToken,
    onMessage,
    onConnect,
    onDisconnect,
    reconnectAttempts: 3,
    reconnectInterval: 5000,
    enabled: realtimeAlerts,
  });

  // Mirror the preference into the store and make sure the badge reads
  // "offline" when alerts are switched off, not a stale "live".
  useEffect(() => {
    setStreamEnabled(realtimeAlerts);
    if (!realtimeAlerts) setStreamConnected(false);
  }, [realtimeAlerts]);

  return null;
}
