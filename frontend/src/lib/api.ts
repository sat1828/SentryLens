/**
 * SentryLens API Client
 * FIX BUG-32: PDF downloaded via fetch with Authorization header — no token in URL
 * FIX BUG-33: auto-refresh logic — retries original request after token refresh
 * FIX BUG-18: WS URLs include ?token= query param for server-side auth
 */
import type {
  AuthTokens, User, Camera, Violation, ComplianceReport,
  ViolationStats, SiteConfig,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_V1   = `${API_BASE}/api/v1`;

const isBrowser = () => typeof window !== "undefined";

// ─── Token Store ───────────────────────────────────────────────────
export const tokenStore = {
  get:          (): string | null  => isBrowser() ? localStorage.getItem("sl_access_token")  : null,
  getRefresh:   (): string | null  => isBrowser() ? localStorage.getItem("sl_refresh_token") : null,
  set:          (t: string)        => isBrowser() && localStorage.setItem("sl_access_token",  t),
  setRefresh:   (t: string)        => isBrowser() && localStorage.setItem("sl_refresh_token", t),
  clear:        ()                 => { if (!isBrowser()) return; localStorage.removeItem("sl_access_token"); localStorage.removeItem("sl_refresh_token"); },
  setTokens:    (t: AuthTokens)    => { if (!isBrowser()) return; localStorage.setItem("sl_access_token", t.access_token); localStorage.setItem("sl_refresh_token", t.refresh_token); },
};

// ─── Token refresh ─────────────────────────────────────────────────
let _refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    const rt = tokenStore.getRefresh();
    if (!rt) return false;
    try {
      const res = await fetch(`${API_V1}/auth/refresh`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return false;
      const tokens: AuthTokens = await res.json();
      tokenStore.setTokens(tokens);
      return true;
    } catch {
      return false;
    } finally {
      _refreshing = null;
    }
  })();
  return _refreshing;
}

// ─── Base fetch with auto-refresh ─────────────────────────────────
async function apiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const token   = tokenStore.get();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_V1}${path}`, { ...options, headers });

  // BUG-33 FIX: on 401 try refresh once, then retry
  if (res.status === 401 && retry) {
    const refreshed = await tryRefresh();
    if (refreshed) return apiFetch<T>(path, options, false);
    tokenStore.clear();
    if (isBrowser()) window.location.href = "/login";
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API error");
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ─── Auth ──────────────────────────────────────────────────────────
export const authApi = {
  login: async (email: string, password: string): Promise<AuthTokens> => {
    const body = new URLSearchParams({ username: email, password });
    const res  = await fetch(`${API_V1}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
    if (!res.ok) { const e = await res.json().catch(()=>({})); throw new Error(e.detail ?? "Login failed"); }
    const tokens: AuthTokens = await res.json();
    tokenStore.setTokens(tokens);
    return tokens;
  },
  logout:          () => tokenStore.clear(),
  me:              (): Promise<User>    => apiFetch("/auth/me"),
  registerAdmin:   (data: { email: string; password: string; full_name: string; phone?: string }): Promise<User> =>
    apiFetch("/auth/register/admin", { method: "POST", body: JSON.stringify(data) }),
};

// ─── Cameras ───────────────────────────────────────────────────────
export const camerasApi = {
  list:         (siteId?: number, limit = 50): Promise<Camera[]> =>
    apiFetch(`/cameras/?limit=${limit}${siteId ? `&site_id=${siteId}` : ""}`),
  create:       (data: { name: string; rtsp_url: string; site_id: number; zone?: string; location_label?: string; config?: Record<string, unknown> }): Promise<Camera> =>
    apiFetch("/cameras/", { method: "POST", body: JSON.stringify(data) }),
  delete:       (id: number): Promise<void>  => apiFetch(`/cameras/${id}`, { method: "DELETE" }),
  statuses:     (): Promise<Record<string, { status: string; frame_count: number; last_frame_at: string | null }>> =>
    apiFetch("/cameras/status"),
  updateConfig: (id: number, config: Record<string, unknown>): Promise<void> =>
    apiFetch(`/cameras/${id}/config`, { method: "PUT", body: JSON.stringify(config) }),
};

// ─── Violations ────────────────────────────────────────────────────
export const violationsApi = {
  list: (params?: { camera_id?: number; violation_type?: string; acknowledged?: boolean; since?: string; limit?: number; offset?: number }): Promise<Violation[]> => {
    const q = new URLSearchParams();
    if (params?.camera_id      !== undefined) q.set("camera_id",      String(params.camera_id));
    if (params?.violation_type !== undefined) q.set("violation_type", params.violation_type);
    if (params?.acknowledged   !== undefined) q.set("acknowledged",   String(params.acknowledged));
    if (params?.since)                        q.set("since",          params.since);
    if (params?.limit)                        q.set("limit",          String(params.limit));
    if (params?.offset)                       q.set("offset",         String(params.offset));
    return apiFetch(`/violations/?${q.toString()}`);
  },
  acknowledge: (id: number): Promise<Violation> => apiFetch(`/violations/${id}/acknowledge`, { method: "PATCH" }),
  stats: (siteId?: number, days = 7): Promise<ViolationStats> => {
    const q = new URLSearchParams({ days: String(days) });
    if (siteId) q.set("site_id", String(siteId));
    return apiFetch(`/violations/stats?${q.toString()}`);
  },
};

// ─── Reports ───────────────────────────────────────────────────────
export const reportsApi = {
  list:         (siteId?: number): Promise<ComplianceReport[]> =>
    apiFetch(`/reports/${siteId ? `?site_id=${siteId}` : ""}`),
  dailySummary: (siteId: number)  => apiFetch(`/reports/daily/summary?site_id=${siteId}`),
  generateNow:  (siteId: number)  => apiFetch(`/reports/generate?site_id=${siteId}`, { method: "POST" }),

  // BUG-32 FIX: download PDF via fetch+blob — no JWT in URL
  downloadPdf: async (reportId: number): Promise<void> => {
    if (!isBrowser()) return;
    const token = tokenStore.get();
    const res   = await fetch(`${API_V1}/reports/${reportId}/pdf`, {
      headers: { Authorization: `Bearer ${token ?? ""}` },
    });
    if (!res.ok) { alert("PDF not available yet. Try generating the report first."); return; }
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `sentrylens_report_${reportId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  },
};

// ─── Runtime config (settings page) ───────────────────────────────
export const configApi = {
  get:    (): Promise<SiteConfig> => apiFetch("/config/"),
  update: (data: Partial<SiteConfig>): Promise<{ ok: boolean }> =>
    apiFetch("/config/", { method: "PUT", body: JSON.stringify({ settings: data }) }),
};

// ─── Snapshots (authenticated) ─────────────────────────────────────
export function snapshotUrl(path: string): string {
  // BUG-36 FIX: route through authenticated API, not public /snapshots/
  return `${API_V1}/snapshots/${path}`;
}

// ─── WebSocket (with token auth) ───────────────────────────────────
const WS_BASE = (): string => {
  const base = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
  return `${base}/api/v1`;
};

// BUG-18 FIX: token appended as query param — authenticated WS
export const createCameraWs = (cameraId: number): WebSocket => {
  const token = tokenStore.get() ?? "";
  return new WebSocket(`${WS_BASE()}/streams/${cameraId}/live?token=${encodeURIComponent(token)}`);
};

export const createAlertsWs = (): WebSocket => {
  const token = tokenStore.get() ?? "";
  return new WebSocket(`${WS_BASE()}/streams/alerts/live?token=${encodeURIComponent(token)}`);
};
