import { Bell, Search, Settings2 } from "lucide-react";
import Link from "next/link";

export function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-[64px] items-center justify-between border-b border-line bg-canvas/80 px-8 backdrop-blur-xl">
      <p className="text-[14px] text-ink-500">
        Welcome back, <span className="font-semibold text-ink-900">Shivam</span> 👋
      </p>

      <div className="flex items-center gap-3">
        <button className="relative flex h-10 w-10 items-center justify-center rounded-[12px] text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]" aria-label="Notifications">
          <Bell size={18} strokeWidth={2} />
          <span className="absolute right-1.5 top-1.5 flex h-[15px] w-[15px] items-center justify-center rounded-full bg-rose-500 text-[9px] font-bold text-white ring-2 ring-canvas">
            3
          </span>
        </button>

        <label className="flex h-10 w-[300px] cursor-text items-center gap-2.5 rounded-[12px] border border-line bg-white px-3.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50">
          <Search size={16} className="text-ink-400" strokeWidth={2.2} />
          <input
            placeholder="Search anything..."
            className="min-w-0 flex-1 bg-transparent text-[13.5px] text-ink-900 outline-none placeholder:text-ink-400"
          />
          <kbd className="rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px] font-medium text-ink-400">
            ⌘K
          </kbd>
        </label>

        <Link
          href="/settings"
          className="flex h-10 w-10 items-center justify-center rounded-[12px] text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]"
          aria-label="Settings"
        >
          <Settings2 size={18} strokeWidth={2} />
        </Link>
      </div>
    </header>
  );
}
