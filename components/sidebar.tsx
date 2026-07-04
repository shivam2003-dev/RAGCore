"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Compass,
  MessageSquare,
  Database,
  FileText,
  BookmarkCheck,
  BarChart3,
  PieChart,
  HeartPulse,
  MessagesSquare,
  Server,
  Users,
  Settings,
  Workflow,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen,
  type LucideIcon,
} from "lucide-react";
import { KimbalMark } from "./brand-icons";
import { cx } from "./ui";

type Item = { label: string; href: string; icon: LucideIcon };

const groups: Array<{ label?: string; items: Item[] }> = [
  {
    items: [{ label: "Home", href: "/", icon: Home }],
  },
  {
    label: "Knowledge",
    items: [
      { label: "Discover", href: "/discover", icon: Compass },
      { label: "Ask Kimbal (RAG)", href: "/ask", icon: MessageSquare },
      { label: "Knowledge Sources", href: "/knowledge-sources", icon: Database },
      { label: "Documents", href: "/documents", icon: FileText },
      { label: "Saved Answers", href: "/saved-answers", icon: BookmarkCheck },
    ],
  },
  {
    label: "Dashboard",
    items: [
      { label: "Analytics", href: "/analytics", icon: BarChart3 },
      { label: "Usage & Insights", href: "/usage-insights", icon: PieChart },
      { label: "Content Health", href: "/content-health", icon: HeartPulse },
      { label: "Feedback", href: "/feedback", icon: MessagesSquare },
    ],
  },
  {
    label: "Admin",
    items: [
      { label: "Data Sources", href: "/data-sources", icon: Server },
      { label: "Access Control", href: "/access-control", icon: Users },
      { label: "Settings", href: "/settings", icon: Settings },
      { label: "Integrations", href: "/integrations", icon: Workflow },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem("kimbal.sidebar.collapsed.v1") === "true";
  });

  useEffect(() => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    window.localStorage.setItem("kimbal.sidebar.collapsed.v1", String(collapsed));
    return () => {
      document.body.classList.remove("sidebar-collapsed");
    };
  }, [collapsed]);

  return (
    <aside
      className={cx(
        "kimbal-sidebar fixed inset-y-0 left-0 z-30 flex flex-col border-r border-line bg-white/70 backdrop-blur-xl transition-[width]",
        collapsed ? "w-[72px]" : "w-[248px]"
      )}
    >
      <div className={cx("flex items-center gap-2.5 pb-5 pt-6", collapsed ? "justify-center px-3" : "px-6")}>
        <Link href="/" className="flex items-center gap-2.5" aria-label="Home">
          <KimbalMark size={30} />
          {!collapsed && <span className="text-[21px] font-bold tracking-[-0.02em] text-ink-900">kimbal</span>}
        </Link>
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          title={collapsed ? "Expand navigation" : "Collapse navigation"}
          className={cx(
            "ml-auto flex h-8 w-8 items-center justify-center rounded-[9px] text-ink-400 transition hover:bg-canvas hover:text-ink-900",
            collapsed && "ml-0"
          )}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className={cx("flex-1 overflow-y-auto pb-4", collapsed ? "px-2" : "px-3.5")}>
        {groups.map((g, gi) => (
          <div key={gi} className={gi > 0 ? "mt-5" : ""}>
            {g.label && !collapsed && (
              <p className="px-2.5 pb-2 text-[10.5px] font-bold uppercase tracking-[0.12em] text-ink-400">
                {g.label}
              </p>
            )}
            <ul className="space-y-0.5">
              {g.items.map((it) => {
                const active = pathname === it.href;
                return (
                  <li key={it.href}>
                    <Link
                      href={it.href}
                      title={collapsed ? it.label : undefined}
                      className={cx(
                        "group flex items-center gap-3 rounded-[10px] py-[9px] text-[13.5px] font-medium transition-colors",
                        collapsed ? "justify-center px-2" : "px-2.5",
                        active
                          ? "border border-brand-100 bg-brand-50 font-semibold text-brand-600"
                          : "border border-transparent text-ink-500 hover:bg-canvas hover:text-ink-900"
                      )}
                    >
                      <it.icon
                        size={17}
                        strokeWidth={2}
                        className={active ? "text-brand-500" : "text-ink-400 group-hover:text-ink-700"}
                      />
                      {!collapsed && it.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <Link
        href="/settings"
        title={collapsed ? "Shivam Kumar" : undefined}
        className={cx(
          "mx-3.5 mb-4 flex items-center gap-3 rounded-[14px] border border-line bg-white p-2.5 text-left shadow-[var(--shadow-card)] transition hover:border-brand-200",
          collapsed && "justify-center px-2"
        )}
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-[13px] font-bold text-white">
          SK
        </span>
        {!collapsed && (
          <>
            <span className="flex-1">
              <span className="block text-[13px] font-semibold text-ink-900">Shivam Kumar</span>
              <span className="block text-[11.5px] text-ink-500">DevSecOps Engineer</span>
            </span>
            <ChevronDown size={15} className="text-ink-400" />
          </>
        )}
      </Link>
    </aside>
  );
}
