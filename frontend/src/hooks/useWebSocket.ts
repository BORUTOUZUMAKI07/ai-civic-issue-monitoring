"use client";

import { useEffect, useRef, useCallback, useState } from "react";

export interface WebSocketMessage {
  type: string;
  payload: Record<string, unknown>;
  timestamp?: string;
}

interface UseWebSocketOptions {
  url: string;
  token?: string;
  /**
   * Resolve a fresh credential at connection time. The access token lives in an
   * HttpOnly cookie the browser cannot read, so callers pass a callback that
   * fetches a short-lived ticket (see `auth.wsTicket`). Reconnects re-invoke it,
   * so an expired ticket never blocks a retry.
   */
  getToken?: () => Promise<string | null | undefined> | string | null | undefined;
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectAttempts?: number;
  reconnectInterval?: number;
  /** When false the hook stays disconnected (e.g. the user turned off alerts). */
  enabled?: boolean;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  sendMessage: (type: string, payload: Record<string, unknown>) => void;
  connect: () => void;
  disconnect: () => void;
}

export function useWebSocket({
  url,
  token,
  getToken,
  onMessage,
  onConnect,
  onDisconnect,
  reconnectAttempts = 5,
  reconnectInterval = 3000,
  enabled = true,
}: UseWebSocketOptions): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectRef = useRef<() => void>(() => {});
  const disconnectRef = useRef<() => void>(() => {});
  const enabledRef = useRef(enabled);
  // Distinguishes "we closed it" (unmount/toggle) from a dropped connection
  // that should be retried.
  const closedByUsRef = useRef(false);
  const disposedRef = useRef(false);

  const connect = useCallback(() => {
    const existing = wsRef.current;
    if (
      existing &&
      (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const open = (resolvedToken?: string | null) => {
      if (disposedRef.current) return;
      const credential = resolvedToken ?? token;
      const wsUrl = credential ? `${url}?token=${encodeURIComponent(credential)}` : url;
      const ws = new WebSocket(wsUrl);
      closedByUsRef.current = false;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectCountRef.current = 0;
        onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(message);
          onMessage?.(message);
        } catch {
          console.error("Failed to parse WebSocket message");
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        onDisconnect?.();

        if (
          !closedByUsRef.current &&
          enabledRef.current &&
          reconnectCountRef.current < reconnectAttempts
        ) {
          reconnectTimerRef.current = setTimeout(() => {
            reconnectCountRef.current += 1;
            connectRef.current();
          }, reconnectInterval);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    };

    if (getToken) {
      Promise.resolve(getToken())
        .then((fresh) => open(fresh))
        .catch(() => open(null));
    } else {
      open(token);
    }
  }, [url, token, getToken, onMessage, onConnect, onDisconnect, reconnectAttempts, reconnectInterval]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const disconnect = useCallback(() => {
    closedByUsRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectCountRef.current = reconnectAttempts;
    wsRef.current?.close();
    wsRef.current = null;
    setIsConnected(false);
  }, [reconnectAttempts]);

  useEffect(() => {
    disconnectRef.current = disconnect;
  }, [disconnect]);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const sendMessage = useCallback(
    (type: string, payload: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type, payload, timestamp: new Date().toISOString() }));
      }
    },
    []
  );

  // Auto-connect for the lifetime of the hook while `enabled` is true. Keyed on
  // only `enabled`/`url` so an unmemoized `getToken` does not cause churn.
  useEffect(() => {
    disposedRef.current = false;
    if (!enabled || !url) return;
    connectRef.current();
    return () => {
      disposedRef.current = true;
      disconnectRef.current();
    };
  }, [enabled, url]);

  return { isConnected, lastMessage, sendMessage, connect, disconnect };
}
