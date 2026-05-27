"use client";
/**
 * FIX: SITE_ID from store, not hardcoded. Reads useAuthStore().siteId.
 */
import { useEffect, useState } from "react";
import { violationsApi, reportsApi } from "@/lib/api";
import { violationStatsToChartData, VIOLATION_LABELS } from "@/lib/utils";
import { useAuthStore } from "@/lib/store";
import type { ViolationStats } from "@/types";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { TrendingDown, ShieldAlert, Download } from "lucide-react";
import { PageHeader, StatCard, Spinner } from "@/components/ui";

export default function CompliancePage() {
  const siteId = useAuthStore((s) => s.siteId);   // FIX: no hardcoded 1
  const [stats7,   setStats7]   = useState<ViolationStats>({});
  const [stats30,  setStats30]  = useState<ViolationStats>({});
  const [loading,  setLoading]  = useState(true);

  useEffect(() => {
    if (!siteId) return;
    Promise.all([
      violationsApi.stats(siteId, 7),
      violationsApi.stats(siteId, 30),
    ]).then(([s7, s30]) => {
      setStats7(s7); setStats30(s30); setLoading(false);
    }).catch(() => setLoading(false));
  }, [siteId]);

  const chart7  = violationStatsToChartData(stats7);
  const chart30 = violationStatsToChartData(stats30);
  const total7  = Object.values(stats7).reduce((a,b)=>a+b,0);
  const total30 = Object.values(stats30).reduce((a,b)=>a+b,0);
  const top30   = [...chart30].sort((a,b)=>b.count-a.count)[0];

  async function exportJSON() {
    try {
      const report = await reportsApi.dailySummary(siteId);
      const blob   = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url    = URL.createObjectURL(blob);
      const a      = document.createElement("a");
      a.href       = url;
      a.download   = `sentrylens_compliance_${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { alert("Failed to generate report."); }
  }

  if (loading) return <div className="p-6 flex justify-center"><Spinner /></div>;

  return (
    <div className="p-6">
      <PageHeader
        title="Compliance analytics"
        subtitle={`Site ${siteId} · Last 7 / 30 days`}
        action={
          <button onClick={exportJSON} className="btn-secondary">
            <Download className="w-3.5 h-3.5" /> Export JSON
          </button>
        }
      />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <StatCard label="Violations (7 days)"  value={total7}  />
        <StatCard label="Violations (30 days)" value={total30} />
        <StatCard
          label="Most common (30d)"
          value={top30 ? (VIOLATION_LABELS[top30.name as keyof typeof VIOLATION_LABELS] ?? top30.name) : "None"}
        />
      </div>

      <div className="card p-5 mb-4">
        <div className="text-sm font-medium text-gray-800 mb-4 flex items-center gap-2">
          <TrendingDown className="w-4 h-4 text-gray-500" />
          By type — last 7 days
        </div>
        {chart7.length === 0 ? (
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">No violations recorded.</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={chart7} margin={{ top: 0, right: 8, left: -20, bottom: 0 }}>
              <XAxis dataKey="name" tick={{ fontSize: 11 }} tickFormatter={(v: string) => v.split(" ").pop()!} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e5e7eb" }} />
              <Bar dataKey="count" radius={[4,4,0,0]}>
                {chart7.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-50 flex items-center gap-2">
          <ShieldAlert className="w-4 h-4 text-gray-500" />
          <span className="text-sm font-medium text-gray-800">Breakdown — last 30 days</span>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-50">
              <th className="text-left px-5 py-3 text-xs font-medium text-gray-500">Type</th>
              <th className="text-right px-5 py-3 text-xs font-medium text-gray-500">Count</th>
              <th className="text-right px-5 py-3 text-xs font-medium text-gray-500">Share</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {Object.entries(stats30).sort(([,a],[,b])=>b-a).map(([vtype, count]) => (
              <tr key={vtype} className="hover:bg-gray-50/50">
                <td className="px-5 py-3 text-gray-700">
                  {VIOLATION_LABELS[vtype as keyof typeof VIOLATION_LABELS] ?? vtype}
                </td>
                <td className="px-5 py-3 text-right font-mono">{count}</td>
                <td className="px-5 py-3 text-right text-gray-500">
                  {total30 > 0 ? `${((count/total30)*100).toFixed(1)}%` : "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
