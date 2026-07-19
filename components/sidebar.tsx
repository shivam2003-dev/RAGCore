"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  MessageSquare,
  Database,
  FileText,
  BookmarkCheck,
  BarChart3,
  Gauge,
  PieChart,
  HeartPulse,
  MessagesSquare,
  Server,
  Users,
  Settings,
  Workflow,
  FolderKanban,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  type LucideIcon,
} from "lucide-react";
import { CVUMMark } from "./brand-icons";
import { cx } from "./ui";
import type { UserOut } from "@/lib/kimbal-api";

type Item = { label: string; href: string; icon: LucideIcon };

const SIDEBAR_COLLAPSED_KEY = "kimbal.sidebar.collapsed.v1";

const groups: Array<{ label?: string; items: Item[] }> = [
  {
    items: [{ label: "Home", href: "/admin", icon: Home }],
  },
  {
    label: "Knowledge",
    items: [
      { label: "Ask CVUM (RAG)", href: "/", icon: MessageSquare },
      { label: "Knowledge Sources", href: "/knowledge-sources", icon: Database },
      { label: "Documents", href: "/documents", icon: FileText },
      { label: "Saved Answers", href: "/saved-answers", icon: BookmarkCheck },
    ],
  },
  {
    label: "Dashboard",
    items: [
      { label: "Analytics", href: "/analytics", icon: BarChart3 },
      { label: "Evals", href: "/evals", icon: Gauge },
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
      { label: "Projects", href: "/projects", icon: FolderKanban },
      { label: "Settings", href: "/settings", icon: Settings },
      { label: "Integrations", href: "/integrations", icon: Workflow },
    ],
  },
];

function initials(name: string) {
  return name.split(" ").filter(Boolean).map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "U";
}

function titleForRole(role: string) {
  if (role === "admin") return "Super admin";
  if (role === "editor") return "Editor";
  return "Ask access";
}

export function Sidebar({ user, onLogout }: { user: UserOut; onLogout: () => void }) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const visibleGroups = user.role === "admin"
    ? groups
    : [{
        items: [
          { label: "Ask CVUM", href: "/", icon: MessageSquare },
          ...(user.role === "editor" ? [{ label: "Projects", href: "/projects", icon: FolderKanban }] : []),
        ],
      }];

  useEffect(() => {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    return () => {
      document.body.classList.remove("sidebar-collapsed");
    };
  }, [collapsed]);

  useEffect(() => {
    const open = () => setMobileOpen(true);
    window.addEventListener("cvum:open-navigation", open);
    return () => window.removeEventListener("cvum:open-navigation", open);
  }, []);

  return (
    <>
      {mobileOpen && <button type="button" aria-label="Close navigation" onClick={() => setMobileOpen(false)} className="fixed inset-0 z-30 bg-ink-900/30 backdrop-blur-[1px] lg:hidden" />}
      <aside
      className={cx(
        "kimbal-sidebar fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-line bg-white/95 backdrop-blur-xl transition-[width,transform] lg:translate-x-0 lg:bg-white/70",
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        collapsed ? "lg:w-[72px]" : "lg:w-[248px]"
      )}
    >
      <div className={cx("flex items-center gap-2.5 px-5 pb-5 pt-6", collapsed ? "lg:justify-center lg:px-3" : "lg:px-6")}>
        <Link href={user.role === "admin" ? "/admin" : "/"} className="flex items-center gap-2.5" aria-label="Home">
          <CVUMMark size={30} />
          <span className={cx("text-[21px] font-bold text-ink-900", collapsed && "lg:hidden")}>CVUM</span>
        </Link>
        <button type="button" onClick={() => setMobileOpen(false)} aria-label="Close navigation" className="ml-auto flex h-8 w-8 items-center justify-center rounded-lg text-ink-400 hover:bg-canvas lg:hidden"><X size={17} /></button>
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          title={collapsed ? "Expand navigation" : "Collapse navigation"}
          className={cx(
            "ml-auto hidden h-8 w-8 items-center justify-center rounded-[9px] text-ink-400 transition hover:bg-canvas hover:text-ink-900 lg:flex",
            collapsed && "ml-0"
          )}
        >
          {collapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
      </div>

      <nav className={cx("flex-1 overflow-y-auto px-3.5 pb-4", collapsed && "lg:px-2")}>
        {visibleGroups.map((g, gi) => (
          <div key={gi} className={gi > 0 ? "mt-5" : ""}>
            {g.label && (
              <p className={cx("px-2.5 pb-2 text-[10.5px] font-bold uppercase tracking-[0.12em] text-ink-400", collapsed && "lg:hidden")}>
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
                      onClick={() => setMobileOpen(false)}
                      title={collapsed ? it.label : undefined}
                      className={cx(
                        "group flex items-center gap-3 rounded-[10px] py-[9px] text-[13.5px] font-medium transition-colors",
                        collapsed ? "px-2.5 lg:justify-center lg:px-2" : "px-2.5",
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
                      <span className={cx(collapsed && "lg:hidden")}>{it.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div
        title={collapsed ? user.full_name : undefined}
        className={cx(
          "mx-3.5 mb-4 flex items-center gap-3 rounded-[14px] border border-line bg-white p-2.5 text-left shadow-[var(--shadow-card)] transition hover:border-brand-200",
          collapsed && "lg:justify-center lg:px-2"
        )}
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-[13px] font-bold text-white">
          {initials(user.full_name)}
        </span>
        <span className={cx("flex-1", collapsed && "lg:hidden")}>
          <span className="block text-[13px] font-semibold text-ink-900">{user.full_name}</span>
          <span className="block text-[11.5px] text-ink-500">{titleForRole(user.role)}</span>
        </span>
        <span className={cx(collapsed && "lg:hidden")}>
          <button type="button" onClick={onLogout} aria-label="Sign out" title="Sign out" className="flex h-7 w-7 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-canvas hover:text-ink-900"><LogOut size={15} /></button>
        </span>
        {collapsed && (
          <button
            type="button"
            onClick={onLogout}
            aria-label="Sign out"
            title="Sign out"
            className="absolute bottom-16 left-5 hidden h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-canvas hover:text-ink-900 lg:flex"
          >
            <LogOut size={15} />
          </button>
        )}
      </div>
    </aside>
    </>
  );
}
