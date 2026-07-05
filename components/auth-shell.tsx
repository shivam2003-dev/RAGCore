"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AppPreferences } from "@/components/app-preferences";
import { Sidebar } from "@/components/sidebar";
import { TopBar } from "@/components/topbar";
import { ApiError, kimbalApi, type UserOut } from "@/lib/kimbal-api";

const LOGIN_PATH = "/login";
const ASK_PATH = "/ask";

function loginHref(pathname: string) {
  if (pathname === LOGIN_PATH) return LOGIN_PATH;
  return `${LOGIN_PATH}?next=${encodeURIComponent(pathname || ASK_PATH)}`;
}

export function AuthShell({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [checking, setChecking] = useState(true);
  const [pathname] = useState(() => {
    if (typeof window === "undefined") return null;
    return window.location.pathname || ASK_PATH;
  });

  const isLogin = pathname === LOGIN_PATH;
  const isAdmin = user?.role === "admin";
  const userCanViewPath = isAdmin || pathname === ASK_PATH;

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
        const currentUser = await kimbalApi.ensureSession();
        if (cancelled) return;
        setUser(currentUser);
        if (currentUser.role !== "admin" && pathname !== ASK_PATH) {
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
  }, [isLogin, pathname]);

  async function logout() {
    await kimbalApi.logout();
    setUser(null);
    window.location.replace(LOGIN_PATH);
  }

  if (isLogin && pathname) {
    return <>{children}</>;
  }

  if (!pathname || checking || !user || !userCanViewPath) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas px-6">
        <div className="rounded-[14px] border border-line bg-white px-5 py-4 text-[13.5px] font-semibold text-ink-600 shadow-[var(--shadow-card)]">
          Loading secure workspace...
        </div>
      </div>
    );
  }

  return (
    <>
      <AppPreferences />
      <Sidebar user={user} onLogout={() => void logout()} />
      <div className="kimbal-shell pl-[248px]">
        <TopBar user={user} onLogout={() => void logout()} />
        <main className="mx-auto max-w-[1440px] px-8 py-7">{children}</main>
      </div>
    </>
  );
}
