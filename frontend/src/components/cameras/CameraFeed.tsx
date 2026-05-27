"use client";
import { useCamera } from "@/hooks/useCamera";
import { cn, VIOLATION_LABELS } from "@/lib/utils";
import { WifiOff, Activity } from "lucide-react";
import type { Camera } from "@/types";

interface CameraFeedProps {
  camera:    Camera;
  className?: string;
}

export function CameraFeed({ camera, className }: CameraFeedProps) {
  const { canvasRef, violations, personCount, inferenceMs, fps, connected, lastFrameAt } =
    useCamera(camera.id);

  const hasViolation = violations.length > 0;

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className={cn("w-2 h-2 rounded-full flex-shrink-0",
          connected ? "bg-green-500" : "bg-red-500 animate-pulse")} />
        <span className="text-sm font-medium text-gray-800 flex-1 truncate">{camera.name}</span>
        {hasViolation && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 animate-pulse">
            {violations.length} violation{violations.length > 1 ? "s" : ""}
          </span>
        )}
        {!hasViolation && connected && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
            Clear
          </span>
        )}
        {!connected && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
            Offline
          </span>
        )}
      </div>

      {/* Video canvas */}
      <div className={cn(
        "relative rounded-xl overflow-hidden bg-gray-900 aspect-video border",
        hasViolation ? "border-red-400 ring-1 ring-red-400" : "border-gray-200",
      )}>
        {connected ? (
          <canvas
            ref={canvasRef}
            className="w-full h-full object-contain"
            aria-label={`Live feed: ${camera.name}`}
          />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-gray-500">
            <WifiOff className="w-8 h-8 opacity-30" />
            <div className="text-sm text-gray-400">Stream unavailable</div>
            {lastFrameAt && (
              <div className="text-xs text-gray-500 font-mono">
                Last frame: {lastFrameAt.toLocaleTimeString()}
              </div>
            )}
          </div>
        )}

        {/* Stats overlay */}
        {connected && (
          <div className="absolute top-2 left-2 flex items-center gap-1.5 pointer-events-none">
            <span className="text-[10px] bg-black/60 text-white px-1.5 py-0.5 rounded font-mono">
              {fps}fps · {Math.round(inferenceMs)}ms
            </span>
            <span className="text-[10px] bg-black/60 text-white px-1.5 py-0.5 rounded font-mono flex items-center gap-1">
              <Activity className="w-2.5 h-2.5" />{personCount}p
            </span>
          </div>
        )}

        {/* Zone + REC */}
        <div className="absolute bottom-2 left-2 text-[10px] bg-black/50 text-white/80 px-1.5 py-0.5 rounded font-mono pointer-events-none">
          {camera.zone} · RTSP
        </div>
        {connected && (
          <div className="absolute top-2 right-2 flex items-center gap-1 pointer-events-none">
            <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-[10px] text-white/80 font-mono">REC</span>
          </div>
        )}
      </div>

      {/* Active violation list */}
      {hasViolation && (
        <div className="space-y-1">
          {violations.map((v, i) => (
            <div key={i} className="flex items-center gap-2 text-xs bg-red-50 border border-red-100 rounded-lg px-2.5 py-1.5">
              <div className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
              <span className="text-red-700 font-medium flex-1">
                {v.type ? (VIOLATION_LABELS[v.type] ?? v.type) : "Unknown violation"}
              </span>
              <span className="text-red-400">{(v.confidence * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
