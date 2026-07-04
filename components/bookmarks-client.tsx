"use client";

import { Bookmark, ExternalLink } from "lucide-react";
import Link from "next/link";
import { Card, GhostButton, PageHeader } from "@/components/ui";

export function BookmarksClient() {
  return (
    <div>
      <PageHeader
        title="Bookmarks"
        subtitle="Pinned source documents are not implemented yet."
        actions={<GhostButton disabled><Bookmark size={15} /> New collection unavailable</GhostButton>}
      />

      <Card className="p-8 text-center animate-rise">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-[14px] bg-brand-50 text-brand-500">
          <Bookmark size={22} />
        </span>
        <p className="mt-4 text-[16px] font-bold text-ink-900">No document bookmarks API exists yet</p>
        <p className="mx-auto mt-1 max-w-lg text-[13px] leading-relaxed text-ink-500">
          This page no longer shows synthetic pinned documents. Saved answers are available today and persist locally from Ask Kimbal.
        </p>
        <Link
          href="/saved-answers"
          className="mt-5 inline-flex items-center gap-2 rounded-[10px] bg-brand-500 px-4 py-2.5 text-[13px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.5)] transition hover:bg-brand-600"
        >
          Open Saved Answers
          <ExternalLink size={14} />
        </Link>
      </Card>
    </div>
  );
}
