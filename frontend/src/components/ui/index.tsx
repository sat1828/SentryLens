"use client";
/**
 * Shared UI components — Badge, Card, StatCard, EmptyState, Spinner, Toast.
 * All pages import from here instead of inlining styles.
 */
import { cn } from "@/lib/utils";
import type { Severity, ViolationType } from "@/types";
import { VIOLATION_LABELS, SEVERITY_BADGE } from "@/lib/utils";

// ─── Spinner ───────────────────────────────────────────────────────
export function Spinner({ className }: { className?: string }) {
  return (
    <div
      aria-label="Loading"
      className={cn("w-5 h-5 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin", className)}
    />
  );
}

// ─── PageHeader ────────────────────────────────────────────────────
export function PageHeader({
  title, subtitle, action,
}: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        {subtitle && <p className="text-sm text-gray-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

// ─── StatCard ──────────────────────────────────────────────────────
export function StatCard({
  label, value, sub, valueClass,
}: { label: string; value: string | number; sub?: string; valueClass?: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={cn("text-2xl font-semibold text-gray-900", valueClass)}>{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

// ─── EmptyState ────────────────────────────────────────────────────
export function EmptyState({
  icon: Icon, title, action,
}: { icon: React.ElementType; title: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-gray-400">
      <Icon className="w-10 h-10 mb-3 opacity-30" aria-hidden="true" />
      <p className="text-sm mb-3">{title}</p>
      {action}
    </div>
  );
}

// ─── ViolationBadge ────────────────────────────────────────────────
export function ViolationBadge({ type }: { type: ViolationType | string }) {
  const label = VIOLATION_LABELS[type as ViolationType] ?? type;
  return <span className="badge bg-red-100 text-red-700">{label}</span>;
}

// ─── SeverityBadge ────────────────────────────────────────────────
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={cn("badge", SEVERITY_BADGE[severity])}>{severity}</span>
  );
}

// ─── InfoBanner ───────────────────────────────────────────────────
export function InfoBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-6 p-4 bg-amber-50 border border-amber-100 rounded-xl text-xs text-amber-700 leading-relaxed">
      {children}
    </div>
  );
}

// ─── Table ────────────────────────────────────────────────────────
export function Table({
  headers, children, className,
}: { headers: string[]; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("card overflow-hidden", className)}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            {headers.map((h, i) => (
              <th key={i} className={cn("text-xs font-medium text-gray-500 px-5 py-3", i > 0 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">{children}</tbody>
      </table>
    </div>
  );
}
