"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { AppPreferences } from "@/components/app-preferences";
import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/topbar";
import { ApiError, cvumApi, type UserOut } from "@/lib/cvum-api";

const LOGIN_PATH = "/login";
const ASK_PATH = "/";

function loginHref(pathname: string) {
  if (pathname === LOGIN_PATH) return LOGIN_PATH;
  return `${LOGIN_PATH}?next=${encodeURIComponent(pathname || ASK_PATH)}`;
}

export function AuthShell({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [checking, setChecking] = useState(true);
  const currentPathname = usePathname();
  const pathname = currentPathname || ASK_PATH;

  const isLogin = pathname === LOGIN_PATH;
  const isAsk = pathname === ASK_PATH || pathname === "/ask";
  const isProjectLens = pathname === "/projects";
  const isKnowledgeWorkflow = pathname === "/incident-copilot";
  const isAdmin = user?.role === "admin";
  const userCanViewPath = isAdmin || isAsk || isProjectLens || isKnowledgeWorkflow;

  useEffect(() => {
    let cancelled = false;

    async function checkSession() {
      if (!pathname) return;
      if (isLogin) {
        setChecking(false);
        return;
      }
      setChecking(true);
      try {
        const currentUser = await cvumApi.ensureSession();
        if (cancelled) return;
        setUser(currentUser);
        if (currentUser.role !== "admin" && !isAsk && !isProjectLens && !isKnowledgeWorkflow) {
          window.location.replace(ASK_PATH);
        }
      } catch (error) {
        if (cancelled) return;
        setUser(null);
        if (error instanceof ApiError && error.status === 401) {
          window.location.replace(loginHref(pathname));
        }
      } finally {
        if (!cancelled) setChecking(false);
      }
    }

    void checkSession();
    return () => {
      cancelled = true;
    };
  }, [isAsk, isKnowledgeWorkflow, isLogin, isProjectLens, pathname]);

  async function logout() {
    await cvumApi.logout();
    setUser(null);
    window.location.replace(LOGIN_PATH);
  }

  if (isLogin) {
    return <>{children}</>;
  }

  if (checking || !user || !userCanViewPath) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas px-6">
        <div className="rounded-[14px] border border-line bg-white px-5 py-4 text-[13.5px] font-semibold text-ink-600 shadow-[var(--shadow-card)]">
          Loading secure workspace...
        </div>
      </div>
    );
  }

  if (isAsk) {
    return (
      <>
        <AppPreferences />
        {children}
      </>
    );
  }

  return (
    <>
      <AppPreferences />
      <Sidebar user={user} onLogout={() => void logout()} />
      <div className="cvum-shell lg:pl-[248px]">
        <TopBar user={user} onLogout={() => void logout()} />
        <main className="mx-auto max-w-[1440px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">{children}</main>
      </div>
    </>
  );
}
