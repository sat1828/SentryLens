"use client";
/**
 * FIX BUG-34: canvas dimensions set only on first frame or resolution change — no flicker.
 * FIX BUG-35: single Image object reused across frames — no per-frame GC pressure.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { createCameraWs } from "@/lib/api";
import type { LiveFrame, LiveViolation } from "@/types";

interface UseCameraReturn {
  canvasRef:   React.RefObject<HTMLCanvasElement>;
  violations:  LiveViolation[];
  personCount: number;
  inferenceMs: number;
  fps:         number;
  connected:   boolean;
  lastFrameAt: Date | null;
}

export function useCamera(cameraId: number | null): UseCameraReturn {
  const canvasRef       = useRef<HTMLCanvasElement>(null);
  const wsRef           = useRef<WebSocket | null>(null);
  const reconnectRef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const frameTs         = useRef<number[]>([]);
  const mountedRef      = useRef(true);
  // BUG-34,35 FIX: one Image instance, reused every frame
  const imgRef          = useRef<HTMLImageElement | null>(null);

  const [violations,  setViolations]  = useState<LiveViolation[]>([]);
  const [personCount, setPersonCount] = useState(0);
  const [inferenceMs, setInferenceMs] = useState(0);
  const [fps,         setFps]         = useState(0);
  const [connected,   setConnected]   = useState(false);
  const [lastFrameAt, setLastFrameAt] = useState<Date | null>(null);

  const drawFrame = useCallback((jpeg_b64: string) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // BUG-35 FIX: reuse single Image instance
    if (!imgRef.current) imgRef.current = new Image();
    const img = imgRef.current;

    img.onload = () => {
      if (!mountedRef.current) return;
      // BUG-34 FIX: only resize canvas when dimensions actually change
      if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
        canvas.width  = img.naturalWidth;
        canvas.height = img.naturalHeight;
      }
      ctx.drawImage(img, 0, 0);
    };
    img.src = `data:image/jpeg;base64,${jpeg_b64}`;
  }, []);

  const connect = useCallback(() => {
    if (!cameraId || !mountedRef.current) return;
    const ws = createCameraWs(cameraId);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setConnected(true);
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        else clearInterval(ping);
      }, 20_000);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg: LiveFrame = JSON.parse(event.data as string);
        if (msg.type !== "frame") return;
        drawFrame(msg.jpeg_b64);
        setViolations(msg.violations);
        setPersonCount(msg.person_count);
        setInferenceMs(msg.inference_ms);
        setLastFrameAt(new Date());
        const now = Date.now();
        frameTs.current.push(now);
        if (frameTs.current.length > 10) frameTs.current.shift();
        if (frameTs.current.length >= 2) {
          const span = (frameTs.current.at(-1)! - frameTs.current[0]) / 1000;
          setFps(Math.round((frameTs.current.length - 1) / span));
        }
      } catch { /* malformed — skip */ }
    };

    ws.onerror  = () => { if (mountedRef.current) setConnected(false); };
    ws.onclose  = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      reconnectRef.current = setTimeout(connect, 3_000);
    };
  }, [cameraId, drawFrame]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      wsRef.current?.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [connect]);

  return { canvasRef, violations, personCount, inferenceMs, fps, connected, lastFrameAt };
}
