"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, LockKeyhole, Mail } from "lucide-react";
import { CVUMMark } from "@/components/brand-icons";
import { ApiError, kimbalApi } from "@/lib/kimbal-api";

const ASK_PATH = "/ask";

function safeNext(next: string | null, isAdmin: boolean) {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next === "/login") {
    return isAdmin ? "/" : ASK_PATH;
  }
  return isAdmin ? next : ASK_PATH;
}

export function LoginClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function redirectIfLoggedIn() {
      try {
        const user = await kimbalApi.ensureSession();
        if (!cancelled) router.replace(safeNext(searchParams.get("next"), user.role === "admin"));
      } catch {
        kimbalApi.clearSession();
      }
    }
    void redirectIfLoggedIn();
    return () => {
      cancelled = true;
    };
  }, [router, searchParams]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedEmail = email.trim().toLowerCase();
    setError("");
    if (!normalizedEmail.endsWith("@cvum.io")) {
      setError("Use your cvum.io email address.");
      return;
    }
    setSubmitting(true);
    try {
      const user = await kimbalApi.login(normalizedEmail, password);
      router.replace(safeNext(searchParams.get("next"), user.role === "admin"));
    } catch (cause) {
      if (cause instanceof ApiError) {
        setError(cause.message);
      } else {
        setError("Login failed. Check your email and password.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-5 py-8">
      <section className="w-full max-w-[420px] rounded-[16px] border border-line bg-white p-7 shadow-[var(--shadow-card)]">
        <div className="mb-6 flex items-center gap-3">
          <CVUMMark size={38} />
          <div>
            <h1 className="text-[24px] font-bold text-ink-900">CVUM Knowledge Hub</h1>
            <p className="mt-0.5 text-[13px] font-medium text-ink-500">Sign in with your cvum.io account.</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-[12px] font-bold uppercase tracking-[0.08em] text-ink-400">
              Email
            </span>
            <span className="flex h-11 items-center gap-2.5 rounded-[10px] border border-line bg-canvas px-3 transition focus-within:border-brand-300 focus-within:bg-white">
              <Mail size={16} className="text-ink-400" />
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                autoComplete="email"
                required
                placeholder="name@cvum.io"
                className="min-w-0 flex-1 bg-transparent text-[14px] text-ink-900 outline-none placeholder:text-ink-400"
              />
            </span>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-[12px] font-bold uppercase tracking-[0.08em] text-ink-400">
              Password
            </span>
            <span className="flex h-11 items-center gap-2.5 rounded-[10px] border border-line bg-canvas px-3 transition focus-within:border-brand-300 focus-within:bg-white">
              <LockKeyhole size={16} className="text-ink-400" />
              <input
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                type="password"
                autoComplete="current-password"
                required
                className="min-w-0 flex-1 bg-transparent text-[14px] text-ink-900 outline-none"
              />
            </span>
          </label>

          {error && (
            <p className="rounded-[10px] border border-rose-100 bg-rose-50 px-3 py-2 text-[12.5px] font-semibold text-rose-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-[10px] bg-brand-500 px-4 text-[14px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.5)] transition hover:bg-brand-600 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Signing in" : "Sign in"}
            <ArrowRight size={16} />
          </button>
        </form>
      </section>
    </main>
  );
}
