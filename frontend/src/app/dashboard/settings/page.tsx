"use client";
/**
 * FIX: Settings form now calls GET/PUT /api/v1/config — fully functional.
 * Shows success/error toast. SITE_ID from store, not hardcoded.
 */
import { useState, useEffect } from "react";
import { configApi } from "@/lib/api";
import type { SiteConfig } from "@/types";
import { Save, AlertTriangle, CheckCircle } from "lucide-react";
import { PageHeader, Spinner } from "@/components/ui";

type Toast = { type: "success" | "error"; message: string } | null;

export default function SettingsPage() {
  const [config,   setConfig]   = useState<Partial<SiteConfig>>({});
  const [loading,  setLoading]  = useState(true);
  const [saving,   setSaving]   = useState(false);
  const [toast,    setToast]    = useState<Toast>(null);

  useEffect(() => {
    configApi.get()
      .then((c) => { setConfig(c); setLoading(false); })
      .catch(() => { setLoading(false); });
  }, []);

  function showToast(type: "success" | "error", message: string) {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await configApi.update(config);
      showToast("success", "Settings saved and applied immediately.");
    } catch (err: unknown) {
      showToast("error", err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function field(key: keyof SiteConfig, label: string, hint: string, type: "number" | "text" = "text") {
    return (
      <div>
        <label className="label">{label}</label>
        <input
          className="input"
          type={type}
          value={String(config[key] ?? "")}
          onChange={(e) => setConfig((c) => ({
            ...c,
            [key]: type === "number" ? parseFloat(e.target.value) : e.target.value,
          }))}
          step={type === "number" ? "any" : undefined}
        />
        <p className="text-xs text-gray-400 mt-1">{hint}</p>
      </div>
    );
  }

  if (loading) return (
    <div className="p-6 flex justify-center">
      <Spinner />
    </div>
  );

  return (
    <div className="p-6 max-w-2xl">
      <PageHeader title="Settings" subtitle="Runtime-configurable thresholds. Changes apply immediately without restart." />

      {/* Toast */}
      {toast && (
        <div className={`mb-5 flex items-center gap-2 p-3 rounded-lg text-sm ${
          toast.type === "success"
            ? "bg-green-50 border border-green-100 text-green-700"
            : "bg-red-50 border border-red-100 text-red-700"
        }`}>
          <CheckCircle className="w-4 h-4 flex-shrink-0" />
          {toast.message}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-5">
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-800 mb-4">Detection thresholds</h2>
          <div className="grid grid-cols-2 gap-4">
            {field("VIOLATION_CONFIDENCE_THRESHOLD", "Confidence threshold", "0.50–0.95. Lower = more sensitive. Start at 0.70.", "number")}
            {field("ALERT_COOLDOWN_SECONDS", "Alert cooldown (seconds)", "Min gap between SMS alerts for same camera+violation.", "number")}
            {field("SCAFFOLD_OVERCROWD_THRESHOLD", "Scaffold overcrowd threshold", "Person count in a zone before overcrowding fires.", "number")}
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-gray-800 mb-4">Alerting</h2>
          <div className="space-y-4">
            {field("DEFAULT_ALERT_RECIPIENTS", "SMS recipients", "Comma-separated phone numbers in E.164 format: +919XXXXXXXXX,+447XXXXXXXXX")}
            {field("DASHBOARD_URL", "Dashboard URL", "Embedded in SMS alerts as the 'View' link. Must be publicly reachable.")}
          </div>
        </div>

        <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl flex gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-xs text-amber-700 leading-relaxed">
            Settings here update the running process immediately. They do NOT persist across restarts.
            To make permanent, update your <code className="bg-amber-100 px-1 rounded">.env</code> file
            and restart the backend container.
            Keys like <code className="bg-amber-100 px-1 rounded">SECRET_KEY</code>, <code className="bg-amber-100 px-1 rounded">DATABASE_URL</code>,
            and <code className="bg-amber-100 px-1 rounded">MODEL_PATH</code> require restart and are not exposed here.
          </p>
        </div>

        <button type="submit" disabled={saving} className="btn-primary">
          <Save className="w-4 h-4" />
          {saving ? "Saving…" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
