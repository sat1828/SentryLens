// ─── Auth ──────────────────────────────────────────────────────────
export interface User {
  id:        number;
  email:     string;
  full_name: string;
  phone:     string | null;
  is_admin:  boolean;
}
export interface AuthTokens {
  access_token:  string;
  refresh_token: string;
  token_type:    string;
}

// ─── Site ──────────────────────────────────────────────────────────
// FIX: SITE_ID no longer hardcoded — read from user store
export interface Site {
  id:   number;
  name: string;
}

// ─── Camera ────────────────────────────────────────────────────────
export type CameraStatus = "online" | "offline" | "degraded";
export interface Camera {
  id:             number;
  name:           string;
  rtsp_url:       string;
  site_id:        number;
  zone:           string;
  location_label: string;
  status:         CameraStatus;
  is_active:      boolean;
  last_seen:      string | null;
  config:         Record<string, unknown> | null;
}

// ─── Violations ────────────────────────────────────────────────────
export type ViolationType =
  | "missing_helmet" | "missing_vest" | "missing_harness"
  | "restricted_zone" | "scaffold_overcrowd" | "near_miss";
export type Severity = "low" | "medium" | "high" | "critical";
export interface Violation {
  id:             number;
  camera_id:      number;
  violation_type: ViolationType;
  confidence:     number;
  severity:       Severity;
  bounding_box:   number[] | null;
  snapshot_path:  string | null;
  worker_id:      string | null;
  zone_label:     string | null;
  acknowledged:   boolean;
  timestamp:      string;
}

// ─── Alerts ────────────────────────────────────────────────────────
export type AlertStatus = "pending" | "sent" | "failed";
export interface Alert {
  id:              number;
  violation_id:    number;
  camera_id:       number;
  recipient_phone: string;
  status:          AlertStatus;
  twilio_sid:      string | null;
  message_body:    string;
  sent_at:         string | null;
  created_at:      string;
}

// ─── Reports ───────────────────────────────────────────────────────
export interface ReportSummary {
  site_id:           number;
  report_date:       string;
  period:            string;
  total_violations:  number;
  acknowledged:      number;
  open:              number;
  by_type:           Record<string, number>;
  by_camera:         Record<string, number>;
  camera_count:      number;
  generated_at:      string;
}
export interface ComplianceReport {
  id:            number;
  site_id:       number;
  report_date:   string;
  period:        string;
  summary:       ReportSummary;
  pdf_available: boolean;
  generated_at:  string;
}

// ─── WebSocket frames ──────────────────────────────────────────────
export interface LiveViolation {
  type:       ViolationType | null;
  confidence: number;
  severity:   Severity | null;
  bbox:       number[];
}
export interface LiveFrame {
  type:         "frame";
  camera_id:    number;
  frame_id:     number;
  jpeg_b64:     string;
  violations:   LiveViolation[];
  person_count: number;
  inference_ms: number;
  timestamp:    string;
}
export interface LiveAlert {
  type:           "violation";
  camera_id:      number;
  violation_type: ViolationType | null;
  confidence:     number;
  timestamp:      string;
}
export type WsMessage = LiveFrame | LiveAlert | { type: "heartbeat" };

// ─── Stats ─────────────────────────────────────────────────────────
export type ViolationStats = Record<string, number>;

// ─── Site config ───────────────────────────────────────────────────
export interface SiteConfig {
  VIOLATION_CONFIDENCE_THRESHOLD: number;
  ALERT_COOLDOWN_SECONDS:         number;
  SCAFFOLD_OVERCROWD_THRESHOLD:   number;
  DEFAULT_ALERT_RECIPIENTS:       string;
  DASHBOARD_URL:                  string;
}
