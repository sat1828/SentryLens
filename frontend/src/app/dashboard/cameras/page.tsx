"use client";
import { useEffect, useState } from "react";
import { camerasApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { STATUS_DOT, cn } from "@/lib/utils";
import type { Camera } from "@/types";
import { Plus, Trash2, Wifi, AlertCircle } from "lucide-react";
import { PageHeader, EmptyState, Spinner } from "@/components/ui";

interface FormState {
  name: string; rtsp_url: string; zone: string; location_label: string;
}
const EMPTY: FormState = { name: "", rtsp_url: "", zone: "General", location_label: "" };

export default function CamerasPage() {
  const siteId = useAuthStore((s) => s.siteId);
  const [cameras,   setCameras]   = useState<Camera[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [showForm,  setShowForm]  = useState(false);
  const [form,      setForm]      = useState<FormState>(EMPTY);
  const [adding,    setAdding]    = useState(false);
  const [error,     setError]     = useState<string | null>(null);

  useEffect(() => {
    camerasApi.list(siteId).then((c) => { setCameras(c); setLoading(false); });
  }, [siteId]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true); setError(null);
    try {
      const cam = await camerasApi.create({ ...form, site_id: siteId });
      setCameras((prev) => [...prev, cam]);
      setForm(EMPTY); setShowForm(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to add camera");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Remove this camera? Streaming will stop immediately.")) return;
    try {
      await camerasApi.delete(id);
      setCameras((prev) => prev.filter((c) => c.id !== id));
    } catch {
      alert("Failed to delete camera.");
    }
  }

  if (loading) return <div className="p-6 flex justify-center"><Spinner /></div>;

  return (
    <div className="p-6">
      <PageHeader
        title="Cameras"
        subtitle={`${cameras.length} registered · Site ${siteId}`}
        action={
          <button onClick={() => setShowForm(!showForm)} className="btn-primary">
            <Plus className="w-4 h-4" /> Add camera
          </button>
        }
      />

      {showForm && (
        <div className="card p-5 mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Register new camera</h2>
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-100 rounded-lg text-xs text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
            </div>
          )}
          <form onSubmit={handleAdd} className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Camera name *</label>
              <input className="input" placeholder="Entry gate CAM-01"
                value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} required />
            </div>
            <div>
              <label className="label">Zone</label>
              <input className="input" placeholder="Scaffold North"
                value={form.zone} onChange={(e) => setForm({...form, zone: e.target.value})} />
            </div>
            <div className="col-span-2">
              <label className="label">
                RTSP URL *
                <span className="text-gray-400 font-normal ml-1">(must start with rtsp://)</span>
              </label>
              <input className="input font-mono text-xs" placeholder="rtsp://admin:password@192.168.1.10:554/stream1"
                value={form.rtsp_url} onChange={(e) => setForm({...form, rtsp_url: e.target.value})} required />
            </div>
            <div>
              <label className="label">Location label</label>
              <input className="input" placeholder="NW corner, floor 3"
                value={form.location_label} onChange={(e) => setForm({...form, location_label: e.target.value})} />
            </div>
            <div className="flex items-end gap-2">
              <button type="button" onClick={() => setShowForm(false)} className="btn-secondary flex-1">Cancel</button>
              <button type="submit" disabled={adding} className="btn-primary flex-1">{adding ? "Adding…" : "Add camera"}</button>
            </div>
          </form>
          <div className="mt-4 p-3 bg-amber-50 border border-amber-100 rounded-lg text-xs text-amber-700">
            SentryLens will attempt to connect immediately. If the camera doesn't appear in Live Feeds
            within 30 seconds, verify the RTSP URL is reachable from the server and that the camera
            uses H.264 encoding on port 554.
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        {cameras.length === 0 ? (
          <EmptyState icon={Wifi} title="No cameras configured. Add one above." />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {["Name","Zone","RTSP URL","Status",""].map((h, i) => (
                  <th key={i} className={`text-xs font-medium text-gray-500 px-5 py-3 ${i === 4 ? "" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {cameras.map((cam) => (
                <tr key={cam.id} className="hover:bg-gray-50/50">
                  <td className="px-5 py-3 font-medium text-gray-900">{cam.name}</td>
                  <td className="px-5 py-3 text-gray-600">{cam.zone}</td>
                  <td className="px-5 py-3 max-w-xs">
                    <span className="font-mono text-xs text-gray-500 truncate block">{cam.rtsp_url}</span>
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-1.5">
                      <div className={cn("w-2 h-2 rounded-full", STATUS_DOT[cam.status] ?? "bg-gray-300")} />
                      <span className="text-gray-600 capitalize text-xs">{cam.status}</span>
                    </div>
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button onClick={() => handleDelete(cam.id)}
                      className="text-gray-400 hover:text-red-600 transition-colors" aria-label="Remove camera">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
