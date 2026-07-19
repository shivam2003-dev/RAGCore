"use client";

import { useEffect, useMemo, useState } from "react";
import { Bookmark, Search, Share2, Sparkles, Trash2 } from "lucide-react";
import { Badge, Card, PageHeader } from "@/components/ui";
import type { RagSource } from "@/lib/cvum-api";

type SavedAnswer = {
  id?: string;
  question: string;
  answer: string;
  sources?: RagSource[];
  savedAt?: string;
};

const STORAGE_KEY = "cvum.saved.answers.v1";

function loadSavedAnswers(): SavedAnswer[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is SavedAnswer => {
      return Boolean(item && typeof item.question === "string" && typeof item.answer === "string");
    });
  } catch {
    return [];
  }
}

function saveAll(items: SavedAnswer[]) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function formatSavedAt(value?: string) {
  if (!value) return "Saved locally";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Saved locally";
  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function SavedAnswersClient() {
  const [items, setItems] = useState<SavedAnswer[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setItems(loadSavedAnswers());
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => `${item.question} ${item.answer}`.toLowerCase().includes(needle));
  }, [items, query]);

  async function share(item: SavedAnswer) {
    const text = `${item.question}\n\n${item.answer}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: "CVUM saved answer", text });
      } else if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
      } else {
        throw new Error("Clipboard sharing is not available");
      }
      setStatus("Share text copied");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Share failed");
    }
  }

  function remove(item: SavedAnswer) {
    const next = items.filter((candidate) => candidate !== item);
    setItems(next);
    saveAll(next);
    setStatus("Saved answer deleted");
  }

  return (
    <div>
      <PageHeader
        title="Saved Answers"
        subtitle="Answers saved from Ask CVUM in this browser."
        actions={
          <span className="rounded-full border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-ink-500">
            {status || `${items.length} saved`}
          </span>
        }
      />

      <label className="mb-5 flex h-11 max-w-xl cursor-text items-center gap-2.5 rounded-[12px] border border-line bg-white px-4 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50 animate-rise-1">
        <Search size={15} className="text-ink-400" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search saved answers..."
          className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-ink-400"
        />
      </label>

      <div className="space-y-4 animate-rise-2">
        {filtered.map((item, index) => (
          <Card key={item.id ?? `${item.question}-${index}`} className="group p-5 transition hover:shadow-[var(--shadow-pop)]">
            <div className="flex items-start gap-4">
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] bg-brand-50 text-brand-500">
                <Sparkles size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <p className="text-[14.5px] font-bold text-ink-900 transition group-hover:text-brand-600">
                    {item.question}
                  </p>
                  <Badge tone="brand">Saved</Badge>
                </div>
                <p className="mt-1.5 line-clamp-3 text-[13px] leading-relaxed text-ink-500">{item.answer}</p>
                <div className="mt-3 flex items-center gap-4 text-[12px] text-ink-400">
                  <span>{item.sources?.length ?? 0} sources cited</span>
                  <span>Saved {formatSavedAt(item.savedAt)}</span>
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-brand-500" aria-label="Saved">
                  <Bookmark size={15} fill="currentColor" />
                </button>
                <button
                  type="button"
                  onClick={() => void share(item)}
                  className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-canvas hover:text-brand-500"
                  aria-label="Share"
                >
                  <Share2 size={15} />
                </button>
                <button
                  type="button"
                  onClick={() => remove(item)}
                  className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-rose-50 hover:text-rose-500"
                  aria-label="Delete"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          </Card>
        ))}

        {!filtered.length && (
          <Card className="p-8 text-center">
            <p className="text-[15px] font-bold text-ink-900">No saved answers yet</p>
            <p className="mt-1 text-[13px] text-ink-500">
              Save an answer from Ask CVUM and it will appear here.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
