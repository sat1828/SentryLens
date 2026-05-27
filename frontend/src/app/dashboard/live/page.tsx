"use client";
import { useEffect, useState } from "react";
import { camerasApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { CameraFeed } from "@/components/cameras/CameraFeed";
import type { Camera } from "@/types";
import { Wifi, WifiOff, RefreshCw } from "lucide-react";
import { PageHeader, EmptyState, Spinner, InfoBanner } from "@/components/ui";

export default function LivePage() {
  const siteId = useAuthStore((s) => s.siteId);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    camerasApi.list(siteId).then((c) => { setCameras(c); setLoading(false); });
  };

  useEffect(() => { load(); }, [siteId]);

  const onlineCams  = cameras.filter((c) => c.status !== "offline");
  const offlineCams = cameras.filter((c) => c.status === "offline");

  if (loading) return <div className="p-6 flex justify-center"><Spinner /></div>;

  return (
    <div className="p-6">
      <PageHeader
        title="Live feeds"
        subtitle={`Real-time YOLOv8 inference · ${cameras.length} cameras · Site ${siteId}`}
        action={
          <div className="flex items-center gap-3 text-sm">
            <span className="flex items-center gap-1.5 text-green-600">
              <Wifi className="w-4 h-4" />{onlineCams.length} online
            </span>
            {offlineCams.length > 0 && (
              <span className="flex items-center gap-1.5 text-red-600">
                <WifiOff className="w-4 h-4" />{offlineCams.length} offline
              </span>
            )}
            <button onClick={load} className="btn-secondary">
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        }
      />

      {cameras.length === 0 ? (
        <EmptyState
          icon={Wifi}
          title="No cameras configured yet."
          action={<a href="/dashboard/cameras" className="text-sm text-gray-900 underline">Add a camera</a>}
        />
      ) : (
        <div className="grid grid-cols-2 gap-5">
          {cameras.map((cam) => (
            <CameraFeed key={cam.id} camera={cam} />
          ))}
        </div>
      )}

      <InfoBanner>
        <strong>Real accuracy note:</strong> Frames are annotated server-side by YOLOv8 and
        streamed as JPEG over authenticated WebSocket at ~10fps (30fps ÷ INFERENCE_EVERY_N_FRAMES=3).
        E2E latency: 250–600ms. Real-site accuracy on dusty/night feeds: 65–80% mAP, not the 95%
        quoted on clean benchmark datasets. Tune{" "}
        <code className="bg-amber-100 px-1 rounded">VIOLATION_CONFIDENCE_THRESHOLD</code> per camera
        in Settings before go-live. <strong>Harness and near-miss detection require a supplementary
        dataset</strong> — not detectable with the 10-class Roboflow dataset.
      </InfoBanner>
    </div>
  );
}
