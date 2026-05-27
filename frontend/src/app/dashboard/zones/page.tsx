"use client";
/**
 * FIX: Zone map now has a real canvas-based polygon editor.
 * Users can: select a camera, draw restricted zone polygons by clicking on a
 * background image, close the polygon, and save to camera config via API.
 * Polygons are stored as normalized 0-1 coordinates matching detector.py input.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { camerasApi } from "@/lib/api";
import type { Camera } from "@/types";
import { STATUS_DOT, cn } from "@/lib/utils";
import { MapPin, Plus, Trash2, Save, Info } from "lucide-react";
import { PageHeader, EmptyState, Spinner } from "@/components/ui";

type Point  = [number, number];  // normalised 0-1
type Polygon = Point[];

export default function ZonesPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef    = useRef<HTMLImageElement | null>(null);
  const fileRef   = useRef<HTMLInputElement>(null);

  const [cameras,       setCameras]       = useState<Camera[]>([]);
  const [selectedCam,   setSelectedCam]   = useState<Camera | null>(null);
  const [polygons,      setPolygons]      = useState<Polygon[]>([]);
  const [currentPoly,   setCurrentPoly]   = useState<Point[]>([]);
  const [drawing,       setDrawing]       = useState(false);
  const [bgImage,       setBgImage]       = useState<string | null>(null);
  const [saving,        setSaving]        = useState(false);
  const [savedMsg,      setSavedMsg]      = useState("");
  const [loading,       setLoading]       = useState(true);

  useEffect(() => {
    camerasApi.list().then((c) => { setCameras(c); setLoading(false); });
  }, []);

  // Load existing zones when camera selected
  useEffect(() => {
    if (!selectedCam) return;
    const zones = (selectedCam.config?.zones ?? []) as Polygon[];
    setPolygons(zones);
    setCurrentPoly([]);
    setDrawing(false);
  }, [selectedCam]);

  // Redraw canvas whenever polygons, currentPoly, or background changes
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // Background
    if (imgRef.current) {
      ctx.drawImage(imgRef.current, 0, 0, W, H);
    } else {
      ctx.fillStyle = "#f9fafb";
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#9ca3af";
      ctx.font      = "14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Upload a floor plan or site photo to use as background", W/2, H/2);
    }

    // Saved polygons
    polygons.forEach((poly, i) => {
      if (poly.length < 2) return;
      ctx.beginPath();
      ctx.moveTo(poly[0][0]*W, poly[0][1]*H);
      poly.slice(1).forEach(([x,y]) => ctx.lineTo(x*W, y*H));
      ctx.closePath();
      ctx.fillStyle   = "rgba(239,68,68,0.15)";
      ctx.strokeStyle = "#ef4444";
      ctx.lineWidth   = 2;
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#ef4444";
      ctx.font      = "12px sans-serif";
      ctx.textAlign = "center";
      const cx = poly.reduce((s,[x])=>s+x,0)/poly.length*W;
      const cy = poly.reduce((s,[,y])=>s+y,0)/poly.length*H;
      ctx.fillText(`Zone ${i+1}`, cx, cy);
    });

    // Current polygon being drawn
    if (currentPoly.length > 0) {
      ctx.beginPath();
      ctx.moveTo(currentPoly[0][0]*W, currentPoly[0][1]*H);
      currentPoly.slice(1).forEach(([x,y]) => ctx.lineTo(x*W, y*H));
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth   = 2;
      ctx.setLineDash([6,3]);
      ctx.stroke();
      ctx.setLineDash([]);
      // Draw vertex dots
      currentPoly.forEach(([x,y]) => {
        ctx.beginPath();
        ctx.arc(x*W, y*H, 5, 0, Math.PI*2);
        ctx.fillStyle = "#f59e0b";
        ctx.fill();
      });
    }
  }, [polygons, currentPoly, bgImage]);

  useEffect(() => { redraw(); }, [redraw]);

  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawing || !selectedCam) return;
    const canvas = canvasRef.current!;
    const rect   = canvas.getBoundingClientRect();
    const x      = (e.clientX - rect.left) / rect.width;
    const y      = (e.clientY - rect.top)  / rect.height;

    // Close polygon if clicking near first point (within 3% of canvas)
    if (currentPoly.length >= 3) {
      const [fx, fy] = currentPoly[0];
      if (Math.abs(x-fx) < 0.03 && Math.abs(y-fy) < 0.03) {
        setPolygons((prev) => [...prev, currentPoly]);
        setCurrentPoly([]);
        setDrawing(false);
        return;
      }
    }
    setCurrentPoly((prev) => [...prev, [x, y]]);
  }

  function removePolygon(i: number) {
    setPolygons((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function handleSave() {
    if (!selectedCam) return;
    setSaving(true);
    try {
      const newConfig = { ...(selectedCam.config ?? {}), zones: polygons };
      await camerasApi.updateConfig(selectedCam.id, newConfig);
      setSavedMsg("Zones saved! The detector will use these polygons immediately.");
      setTimeout(() => setSavedMsg(""), 4000);
      // Update local state
      setSelectedCam((c) => c ? { ...c, config: newConfig } : c);
      setCameras((cs) => cs.map((c) => c.id === selectedCam.id ? { ...c, config: newConfig } : c));
    } catch (e) {
      setSavedMsg("Save failed — check console.");
    } finally {
      setSaving(false);
    }
  }

  function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setBgImage(url);
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = url;
  }

  if (loading) return <div className="p-6 flex justify-center"><Spinner /></div>;

  return (
    <div className="p-6">
      <PageHeader
        title="Zone map"
        subtitle="Draw restricted zones on your site plan. Polygons are saved to camera config and used live by the detector."
      />

      <div className="grid grid-cols-3 gap-5">
        {/* Camera selector */}
        <div className="col-span-1">
          <div className="card p-4 mb-4">
            <div className="text-xs font-medium text-gray-700 mb-3">Select camera to configure</div>
            {cameras.length === 0 ? (
              <p className="text-xs text-gray-400">No cameras. Add one on the Cameras page.</p>
            ) : cameras.map((cam) => (
              <button
                key={cam.id}
                onClick={() => setSelectedCam(cam)}
                className={cn(
                  "w-full flex items-center gap-2 text-left px-3 py-2 rounded-lg text-sm mb-1 transition-colors",
                  selectedCam?.id === cam.id ? "bg-gray-900 text-white" : "hover:bg-gray-50 text-gray-700"
                )}
              >
                <div className={cn("w-2 h-2 rounded-full flex-shrink-0", STATUS_DOT[cam.status] ?? "bg-gray-300")} />
                <span className="flex-1 truncate">{cam.name}</span>
              </button>
            ))}
          </div>

          {selectedCam && (
            <div className="card p-4">
              <div className="text-xs font-medium text-gray-700 mb-3">
                Zones for {selectedCam.name}
              </div>
              {polygons.length === 0 ? (
                <p className="text-xs text-gray-400 mb-3">No zones defined.</p>
              ) : polygons.map((_, i) => (
                <div key={i} className="flex items-center justify-between py-1.5 text-sm">
                  <span className="text-gray-700">Restricted Zone {i+1}</span>
                  <button onClick={() => removePolygon(i)} className="text-gray-400 hover:text-red-600">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}

              <div className="flex gap-2 mt-3">
                <button
                  onClick={() => { setDrawing(true); setCurrentPoly([]); }}
                  disabled={drawing}
                  className="btn-secondary text-xs flex-1"
                >
                  <Plus className="w-3.5 h-3.5" />
                  {drawing ? "Click to draw…" : "Add zone"}
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="btn-primary text-xs flex-1"
                >
                  <Save className="w-3.5 h-3.5" />
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>

              {savedMsg && (
                <p className="text-xs text-green-600 mt-2">{savedMsg}</p>
              )}

              <div className="mt-3 text-xs text-gray-400 flex gap-1 items-start">
                <Info className="w-3 h-3 flex-shrink-0 mt-0.5" />
                <span>Click on canvas to add vertices. Click near first vertex to close the polygon.</span>
              </div>
            </div>
          )}
        </div>

        {/* Canvas editor */}
        <div className="col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImageUpload} />
            <button onClick={() => fileRef.current?.click()} className="btn-secondary text-xs">
              <Plus className="w-3.5 h-3.5" /> Upload floor plan
            </button>
            {drawing && (
              <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-1 rounded-full">
                Drawing mode — click to add points, click near start to close
              </span>
            )}
          </div>
          <div className="card overflow-hidden">
            <canvas
              ref={canvasRef}
              width={800}
              height={500}
              className={cn("w-full", drawing ? "cursor-crosshair" : "cursor-default")}
              onClick={handleCanvasClick}
              aria-label="Zone polygon editor"
            />
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Coordinates stored as normalised 0–1 values matching camera frame dimensions.
            Works directly with the YOLOv8 detector without any conversion.
          </p>
        </div>
      </div>
    </div>
  );
}
