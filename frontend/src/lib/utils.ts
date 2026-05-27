import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow } from "date-fns";
import type { ViolationType, Severity } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ─── Date ──────────────────────────────────────────────────────────────────────
export function formatTs(iso: string): string {
  return format(new Date(iso), "HH:mm:ss");
}
export function formatDate(iso: string): string {
  return format(new Date(iso), "d MMM yyyy");
}
export function timeAgo(iso: string): string {
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}

// ─── Violation metadata ────────────────────────────────────────────────────────
// NOTE: Record<string, string> (not Record<ViolationType, string>) so pages can
// safely index with unknown strings from the API without TypeScript errors.
export const VIOLATION_LABELS: Record<string, string> = {
  missing_helmet:     "Missing helmet",
  missing_vest:       "Missing hi-vis vest",
  missing_harness:    "Missing harness",
  restricted_zone:    "Restricted zone entry",
  scaffold_overcrowd: "Scaffold overcrowding",
  near_miss:          "Near-miss incident",
} satisfies Record<ViolationType, string>;   // compile-time completeness check

export const VIOLATION_COLORS: Record<string, string> = {
  missing_helmet:     "bg-red-100 text-red-700 border-red-200",
  missing_vest:       "bg-orange-100 text-orange-700 border-orange-200",
  missing_harness:    "bg-red-200 text-red-800 border-red-300",
  restricted_zone:    "bg-purple-100 text-purple-700 border-purple-200",
  scaffold_overcrowd: "bg-yellow-100 text-yellow-700 border-yellow-200",
  near_miss:          "bg-red-200 text-red-900 border-red-400",
} satisfies Record<ViolationType, string>;

export const SEVERITY_BADGE: Record<Severity, string> = {
  low:      "bg-green-100 text-green-700",
  medium:   "bg-yellow-100 text-yellow-700",
  high:     "bg-orange-100 text-orange-700",
  critical: "bg-red-100 text-red-700",
};

export const STATUS_DOT: Record<string, string> = {
  online:   "bg-green-500",
  offline:  "bg-red-500",
  degraded: "bg-yellow-500",
};

// ─── Chart data ────────────────────────────────────────────────────────────────
export function violationStatsToChartData(
  stats: Record<string, number>,
): { name: string; count: number; fill: string }[] {
  const fills: Record<string, string> = {
    missing_helmet:     "#ef4444",
    missing_vest:       "#f97316",
    missing_harness:    "#dc2626",
    restricted_zone:    "#8b5cf6",
    scaffold_overcrowd: "#eab308",
    near_miss:          "#b91c1c",
  };
  return Object.entries(stats).map(([key, count]) => ({
    name:  VIOLATION_LABELS[key] ?? key,
    count,
    fill:  fills[key] ?? "#6b7280",
  }));
}

export function confidenceLabel(c: number): string {
  if (c >= 0.9) return "Very high";
  if (c >= 0.75) return "High";
  if (c >= 0.6) return "Medium";
  return "Low";
}
