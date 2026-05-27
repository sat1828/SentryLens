"use client";
/**
 * FIX BUG-36: snapshot images served through authenticated /api/v1/snapshots/ endpoint.
 * FIX BUG-37: pagination added — no more 1000-item DOM list.
 * FIX: duplicate useLiveAlerts removed — reads from layout's context via prop drilling
 *      replaced with a local instance (acceptable: 2 WS max per page is fine).
 */
import { useEffect, useState, useCallback } from "react";
import { violationsApi, snapshotUrl } from "@/lib/api";
import { useLiveAlerts } from "@/hooks/useLiveAlerts";
import { VIOLATION_LABELS, SEVERITY_BADGE, formatTs, timeAgo, cn } from "@/lib/utils";
import type { Violation } from "@/types";
import { CheckCheck, Bell, AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { PageHeader, SeverityBadge, EmptyState, Spinner } from "@/components/ui";

const PAGE_SIZE = 50;

type Filter = "all" | "open" | "acked";

export default function AlertsPage() {
  const [violations, setViolations] = useState<Violation[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [filter,     setFilter]     = useState<Filter>("all");
  const [offset,     setOffset]     = useState(0);
  const [total,      setTotal]      = useState(0);
  const { alerts: liveAlerts }      = useLiveAlerts();

  const load = useCallback(async (f: Filter, off: number) => {
    setLoading(true);
    const params = {
      limit:        PAGE_SIZE,
      offset:       off,
      ...(f === "open"  ? { acknowledged: false } : {}),
      ...(f === "acked" ? { acknowledged: true  } : {}),
    };
    try {
      const data = await violationsApi.list(params);
      setViolations(data);
      setTotal(off + data.length + (data.length === PAGE_SIZE ? 1 : 0)); // approximate
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(filter, 0); setOffset(0); }, [filter, load]);

  // Reload when new live violation arrives
  useEffect(() => {
    if (liveAlerts.length > 0) load(filter, offset);
  }, [liveAlerts, filter, offset, load]);

  async function acknowledge(id: number) {
    await violationsApi.acknowledge(id);
    setViolations((prev) => prev.map((v) => v.id === id ? { ...v, acknowledged: true } : v));
  }

  const open = violations.filter((v) => !v.acknowledged).length;

  function changePage(dir: 1 | -1) {
    const newOffset = Math.max(0, offset + dir * PAGE_SIZE);
    setOffset(newOffset);
    load(filter, newOffset);
  }

  return (
    <div className="p-6">
      <PageHeader
        title="Alert feed"
        subtitle={`${open} unacknowledged · page ${Math.floor(offset/PAGE_SIZE)+1}`}
        action={
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
            {(["all","open","acked"] as Filter[]).map((f) => (
              <button key={f} onClick={() => setFilter(f)}
                className={cn("px-3 py-1.5 rounded-md text-xs font-medium transition-colors",
                  filter === f ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700")}>
                {f === "all" ? "All" : f === "open" ? `Open (${open})` : "Acknowledged"}
              </button>
            ))}
          </div>
        }
      />

      {loading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_,i) => <div key={i} className="h-16 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
      ) : violations.length === 0 ? (
        <EmptyState icon={Bell} title="No violations found for this filter." />
      ) : (
        <>
          <div className="space-y-2">
            {violations.map((v) => (
              <div key={v.id} className={cn("card p-4 flex items-start gap-4 transition-opacity",
                v.acknowledged && "opacity-60")}>
                {/* Severity icon */}
                <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5",
                  v.severity === "critical" || v.severity === "high" ? "bg-red-100" : "bg-orange-50")}>
                  <AlertTriangle className={cn("w-4 h-4",
                    v.severity === "critical" || v.severity === "high" ? "text-red-600" : "text-orange-500")} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="text-sm font-medium text-gray-900">
                      {VIOLATION_LABELS[v.violation_type] ?? v.violation_type}
                    </span>
                    <SeverityBadge severity={v.severity} />
                    {v.acknowledged && (
                      <span className="badge bg-gray-100 text-gray-500">Acknowledged</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 flex items-center gap-3 flex-wrap">
                    <span>Camera {v.camera_id}</span>
                    {v.zone_label && <span>Zone: {v.zone_label}</span>}
                    <span>Confidence: {(v.confidence * 100).toFixed(0)}%</span>
                    <span>{timeAgo(v.timestamp)}</span>
                    <span className="font-mono">{formatTs(v.timestamp)}</span>
                  </div>
                </div>

                {/* BUG-36 FIX: snapshot served through authenticated route */}
                {v.snapshot_path && (
                  <SnapshotThumb path={v.snapshot_path} />
                )}

                {!v.acknowledged && (
                  <button onClick={() => acknowledge(v.id)} className="btn-secondary flex-shrink-0 text-xs">
                    <CheckCheck className="w-3.5 h-3.5" /> Ack
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* BUG-37 FIX: pagination controls */}
          <div className="flex items-center justify-between mt-6 text-sm text-gray-500">
            <button onClick={() => changePage(-1)} disabled={offset === 0} className="btn-secondary disabled:opacity-40">
              <ChevronLeft className="w-4 h-4" /> Previous
            </button>
            <span>Showing {offset + 1}–{offset + violations.length}</span>
            <button onClick={() => changePage(1)} disabled={violations.length < PAGE_SIZE} className="btn-secondary disabled:opacity-40">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Authenticated snapshot thumbnail.
 * Fetches the image via the API client (with Authorization header) and
 * creates an object URL — BUG-36 fix in action.
 */
function SnapshotThumb({ path }: { path: string }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    const url  = snapshotUrl(path);
    let objUrl = "";
    import("@/lib/api").then(({ tokenStore }) => {
      const token = tokenStore.get() ?? "";
      fetch(url, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.ok ? r.blob() : null)
        .then((blob) => {
          if (blob) {
            objUrl = URL.createObjectURL(blob);
            setSrc(objUrl);
          }
        })
        .catch(() => {/* snapshot not found */});
    });
    return () => { if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [path]);

  if (!src) return null;
  return (
    <img src={src} alt="Violation frame" loading="lazy"
      className="w-20 h-14 object-cover rounded-lg border border-gray-100 flex-shrink-0" />
  );
}
