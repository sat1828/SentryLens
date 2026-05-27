"use client";
/**
 * FIX: SITE_ID from store. PDF download via fetch+blob (BUG-32 fix).
 */
import { useEffect, useState } from "react";
import { reportsApi } from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import type { ComplianceReport } from "@/types";
import { FileText, RefreshCw, Clock, Download } from "lucide-react";
import { formatDate } from "@/lib/utils";
import { PageHeader, EmptyState, Spinner } from "@/components/ui";

export default function ReportsPage() {
  const siteId     = useAuthStore((s) => s.siteId);   // FIX: no hardcoded 1
  const [reports,    setReports]    = useState<ComplianceReport[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (!siteId) return;
    reportsApi.list(siteId).then((r) => { setReports(r); setLoading(false); });
  }, [siteId]);

  async function generate() {
    setGenerating(true);
    try {
      await reportsApi.generateNow(siteId);
      // Poll for 5s then reload
      await new Promise((r) => setTimeout(r, 5000));
      const r = await reportsApi.list(siteId);
      setReports(r);
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <div className="p-6 flex justify-center"><Spinner /></div>;

  return (
    <div className="p-6">
      <PageHeader
        title="Compliance reports"
        subtitle="Generated daily at 00:05 UTC via Celery beat"
        action={
          <button onClick={generate} disabled={generating} className="btn-primary disabled:opacity-60">
            {generating
              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" />Generating…</>
              : <><RefreshCw className="w-3.5 h-3.5" />Generate now</>}
          </button>
        }
      />

      <div className="card overflow-hidden">
        {reports.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No reports yet. Click Generate now or wait for the midnight run."
          />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                {["Date","Period","Violations","Open","Generated","PDF"].map((h,i) => (
                  <th key={h} className={`text-xs font-medium text-gray-500 px-5 py-3 ${i > 1 ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {reports.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50/50">
                  <td className="px-5 py-3 font-medium text-gray-900">{formatDate(r.report_date)}</td>
                  <td className="px-5 py-3 text-gray-600 capitalize">{r.period}</td>
                  <td className="px-5 py-3 text-right font-mono">{r.summary?.total_violations ?? "–"}</td>
                  <td className={`px-5 py-3 text-right font-mono ${(r.summary?.open ?? 0) > 0 ? "text-red-600" : "text-gray-500"}`}>
                    {r.summary?.open ?? "–"}
                  </td>
                  <td className="px-5 py-3 text-right text-gray-500 text-xs">
                    <span className="flex items-center justify-end gap-1">
                      <Clock className="w-3 h-3" />{formatDate(r.generated_at)}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {r.pdf_available ? (
                      /* BUG-32 FIX: downloadPdf uses fetch+blob, not window.open with token in URL */
                      <button onClick={() => reportsApi.downloadPdf(r.id)} className="btn-secondary text-xs">
                        <Download className="w-3 h-3" /> PDF
                      </button>
                    ) : (
                      <span className="text-xs text-gray-400">Not ready</span>
                    )}
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
