"use client";
import { useEffect, useRef, useState } from "react";
import { createAlertsWs } from "@/lib/api";
import type { LiveAlert } from "@/types";

const MAX_ALERTS = 50;

export function useLiveAlerts() {
  const wsRef        = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef   = useRef(true);
  const [alerts,    setAlerts]    = useState<LiveAlert[]>([]);
  const [connected, setConnected] = useState(false);

  function connect() {
    if (!mountedRef.current) return;
    const ws = createAlertsWs();
    wsRef.current = ws;

    ws.onopen  = () => { if (mountedRef.current) setConnected(true); };
    ws.onmessage = (e) => {
      if (!mountedRef.current) return;
      try {
        const msg = JSON.parse(e.data as string);
        if (msg.type === "violation") {
          setAlerts((prev) => [msg as LiveAlert, ...prev].slice(0, MAX_ALERTS));
        }
      } catch { /* skip */ }
    };
    ws.onerror  = () => { if (mountedRef.current) setConnected(false); };
    ws.onclose  = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      reconnectRef.current = setTimeout(connect, 3_000);
    };
  }

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { alerts, connected };
}
