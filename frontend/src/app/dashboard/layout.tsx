"use client";
import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import {
  Video, Bell, BarChart2, Map, Camera,
  FileText, Settings, LogOut, ShieldCheck, ChevronRight,
} from "lucide-react";
import { useAuthStore } from "@/lib/store";
import { useLiveAlerts } from "@/hooks/useLiveAlerts";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard/live",       label: "Live feeds",  icon: Video },
  { href: "/dashboard/alerts",     label: "Alerts",      icon: Bell,      badge: true },
  { href: "/dashboard/compliance", label: "Compliance",  icon: BarChart2 },
  { href: "/dashboard/zones",      label: "Zone map",    icon: Map },
  { href: "/dashboard/cameras",    label: "Cameras",     icon: Camera },
  { href: "/dashboard/reports",    label: "Reports",     icon: FileText },
  { href: "/dashboard/settings",   label: "Settings",    icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router   = useRouter();
  const pathname = usePathname();
  const { user, loading, hydrate, logout } = useAuthStore();
  const { alerts } = useLiveAlerts();
  const [unread,  setUnread]  = useState(0);
  // mounted prevents SSR/client HTML mismatch on auth-dependent UI
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    hydrate().then(() => {
      const u = useAuthStore.getState().user;
      if (!u) router.replace("/login");
    });
  }, [hydrate, router]);

  // Count new live violation alerts as unread
  useEffect(() => {
    if (alerts.length > 0) setUnread((n) => n + 1);
  }, [alerts]);

  // Show nothing until mounted (avoids hydration mismatch)
  if (!mounted || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="w-5 h-5 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return null;

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 flex flex-col bg-white border-r border-gray-100 overflow-y-auto">
        <div className="px-4 py-4 border-b border-gray-100 flex items-center gap-2.5">
          <div className="w-8 h-8 bg-gray-900 rounded-lg flex items-center justify-center flex-shrink-0">
            <ShieldCheck className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900 leading-none">SentryLens</div>
            <div className="text-[11px] text-gray-400 mt-0.5 truncate max-w-[148px]">{user.full_name}</div>
          </div>
        </div>

        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon, badge }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => { if (badge) setUnread(0); }}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                  active
                    ? "bg-gray-900 text-white"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900",
                )}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span className="flex-1">{label}</span>
                {badge && unread > 0 && (
                  <span className="text-[10px] font-semibold bg-red-500 text-white rounded-full px-1.5 py-0.5 min-w-[18px] text-center leading-none">
                    {unread > 99 ? "99+" : unread}
                  </span>
                )}
                {active && <ChevronRight className="w-3.5 h-3.5 opacity-40" />}
              </Link>
            );
          })}
        </nav>

        <div className="px-2 pb-4 border-t border-gray-100 pt-2">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-900 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">{children}</main>
    </div>
  );
}
