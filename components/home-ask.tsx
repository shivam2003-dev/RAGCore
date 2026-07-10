"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Send, Sparkles } from "lucide-react";
import { Card, CardLink } from "@/components/ui";

const suggestions = [
  "How to onboard a new engineer?",
  "Where is our CI/CD documentation?",
  "What is our incident response process?",
];

export function HomeAsk() {
  const router = useRouter();
  const [question, setQuestion] = useState("");

  function submit(event?: FormEvent<HTMLFormElement>, value = question) {
    event?.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    router.push(`/?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <Card className="relative overflow-hidden p-6 animate-rise-1">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-50/40 via-transparent to-sky-50/40" />
      <div className="relative">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-brand-50 text-brand-500">
            <Sparkles size={17} />
          </span>
          <div>
            <p className="text-[15px] font-semibold text-ink-900">
              Ask CVUM <span className="font-normal text-ink-500">(Powered by RAG)</span>
            </p>
            <p className="text-[12.5px] text-ink-500">Ask anything across your company knowledge</p>
          </div>
        </div>

        <form
          onSubmit={(event) => submit(event)}
          className="mt-4 flex items-center gap-2 rounded-[14px] border border-line bg-white py-1.5 pl-5 pr-1.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50"
        >
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a question... (e.g., How to deploy a service on Kubernetes?)"
            className="h-10 min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-400"
          />
          <button
            type="submit"
            aria-label="Ask"
            className="flex h-10 w-10 items-center justify-center rounded-[11px] bg-brand-500 text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.6)] transition hover:bg-brand-600"
          >
            <Send size={16} />
          </button>
        </form>

        <div className="mt-4 flex flex-wrap items-center gap-2.5">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => submit(undefined, suggestion)}
              className="rounded-full border border-line bg-white px-3.5 py-1.5 text-[12.5px] font-medium text-ink-700 transition hover:border-brand-200 hover:text-brand-600"
            >
              {suggestion}
            </button>
          ))}
          <CardLink href="/">View all suggestions</CardLink>
        </div>
      </div>
    </Card>
  );
}
