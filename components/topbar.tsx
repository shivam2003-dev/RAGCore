"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCircle2, LogOut, Menu, Search, Settings2, X } from "lucide-react";
import Link from "next/link";
import { kimbalApi, type ActivityMetric, type UserOut } from "@/lib/kimbal-api";

function firstName(name: string) {
  return name.trim().split(/\s+/)[0] || "there";
}

export function TopBar({ user, onLogout }: { user: UserOut; onLogout: () => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<ActivityMetric[]>([]);

  useEffect(() => {
    async function load() {
      if (user.role !== "admin") return;
      try {
        await kimbalApi.ensureSession();
        const metrics = await kimbalApi.metricsOverview();
        setNotifications(metrics.recent_activity.slice(0, 5));
      } catch {
        setNotifications([]);
      }
    }
    void load();
  }, [user.role]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (trimmed) router.push(`/?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <header className="kimbal-topbar sticky top-0 z-20 flex h-[64px] items-center justify-between border-b border-line bg-canvas/80 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <button type="button" onClick={() => window.dispatchEvent(new Event("cvum:open-navigation"))} aria-label="Open navigation" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-500 hover:bg-white lg:hidden"><Menu size={19} /></button>
      <p className="truncate text-[14px] text-ink-500">
        Welcome back, <span className="font-semibold text-ink-900">{firstName(user.full_name)}</span>
      </p>
      </div>

      <div className="relative flex items-center gap-3">
        {user.role === "admin" && (
          <button
            type="button"
            onClick={() => setShowNotifications((open) => !open)}
            className="relative flex h-10 w-10 items-center justify-center rounded-[12px] text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]"
            aria-label="Notifications"
            aria-expanded={showNotifications}
          >
            <Bell size={18} strokeWidth={2} />
            {notifications.length > 0 && (
              <span className="absolute right-1.5 top-1.5 flex h-[15px] w-[15px] items-center justify-center rounded-full bg-rose-500 text-[9px] font-bold text-white ring-2 ring-canvas">
                {notifications.length}
              </span>
            )}
          </button>
        )}

        <form
          onSubmit={submit}
          className="hidden h-10 w-[min(300px,32vw)] cursor-text items-center gap-2.5 rounded-[12px] border border-line bg-white px-3.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50 sm:flex"
        >
          <Search size={16} className="text-ink-400" strokeWidth={2.2} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search anything..."
            className="min-w-0 flex-1 bg-transparent text-[13.5px] text-ink-900 outline-none placeholder:text-ink-400"
          />
          <kbd className="rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px] font-medium text-ink-400">
            Enter
          </kbd>
        </form>

        {user.role === "admin" && (
          <Link
            href="/settings"
            className="flex h-10 w-10 items-center justify-center rounded-[12px] text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]"
            aria-label="Settings"
          >
            <Settings2 size={18} strokeWidth={2} />
          </Link>
        )}

        <button
          type="button"
          onClick={onLogout}
          className="flex h-10 w-10 items-center justify-center rounded-[12px] text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]"
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut size={18} strokeWidth={2} />
        </button>

        {user.role === "admin" && showNotifications && (
          <div className="absolute right-0 top-12 w-80 rounded-[14px] border border-line bg-white p-3 shadow-[var(--shadow-pop)]">
            <div className="flex items-center justify-between px-1 pb-2">
              <p className="text-[13px] font-bold text-ink-900">Notifications</p>
              <button
                type="button"
                onClick={() => setShowNotifications(false)}
                aria-label="Close notifications"
                className="text-ink-400 transition hover:text-ink-700"
              >
                <X size={15} />
              </button>
            </div>
            <ul className="space-y-1">
              {notifications.map((item) => (
                <li key={`${item.action}-${item.created_at}`} className="flex items-center gap-2 rounded-[10px] bg-canvas px-3 py-2 text-[12.5px] font-medium text-ink-700">
                  <CheckCircle2 size={14} className="text-emerald-500" />
                  {item.detail || item.action}
                </li>
              ))}
              {!notifications.length && (
                <li className="rounded-[10px] bg-canvas px-3 py-2 text-[12.5px] font-medium text-ink-500">
                  No recent activity yet.
                </li>
              )}
            </ul>
          </div>
        )}
      </div>
    </header>
  );
}
