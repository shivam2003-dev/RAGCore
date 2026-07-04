"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpDown, Eye, FileText, Loader2, MoreHorizontal, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import { Card, PageHeader, PrimaryButton, GhostButton, Badge, cx } from "@/components/ui";
import { kimbalApi, type DocumentOut, type KnowledgeBase } from "@/lib/kimbal-api";

const freshTone = { indexed: "green", uploaded: "amber", failed: "red", deleted: "gray" } as const;
const LEGACY_SEED_KB_NAME = "Kimbal Local Runbook";

export function DocumentsClient() {
  const searchParams = useSearchParams();
  const kbFilter = searchParams.get("kb") ?? "";
  const sourceFilter = searchParams.get("source") ?? "";
  const fileInput = useRef<HTMLInputElement>(null);
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [docs, setDocs] = useState<Array<DocumentOut & { knowledge_base_name: string }>>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("Loading documents");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      await kimbalApi.ensureSession();
      let kbs = await kimbalApi.listKnowledgeBases();
      if (!kbs.length) {
        kbs = [await kimbalApi.ensureUploadKnowledgeBase()];
      }
      let visibleKbs = kbs.filter((item) => item.name !== LEGACY_SEED_KB_NAME);
      if (!visibleKbs.length) {
        visibleKbs = [await kimbalApi.ensureUploadKnowledgeBase()];
      }
      setKnowledgeBases(visibleKbs);
      setKb(visibleKbs.find((item) => item.name === "Kimbal Local Uploads") ?? visibleKbs[0]);
      const lists = await Promise.all(
        visibleKbs.map(async (item) => {
          const list = await kimbalApi.listDocuments(item.id);
          return list.items.map((doc) => ({ ...doc, knowledge_base_name: item.name }));
        })
      );
      const allDocs = lists.flat().sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      setDocs(allDocs);
      setStatus(`${allDocs.length} documents loaded`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load documents");
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setStatus(`Uploading ${file.name}`);
    try {
      const nextKb = kb?.name === "Kimbal Local Uploads" ? kb : await kimbalApi.ensureUploadKnowledgeBase();
      await kimbalApi.uploadDocument(nextKb.id, file);
      event.target.value = "";
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Upload failed");
      setBusy(false);
    }
  }

  async function reindex(doc: DocumentOut) {
    setStatus(`Re-indexing ${doc.title}`);
    await kimbalApi.reindexDocument(doc.id);
    await refresh();
  }

  async function remove(doc: DocumentOut) {
    setStatus(`Deleting ${doc.title}`);
    await kimbalApi.deleteDocument(doc.id);
    await refresh();
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const activeFilterLabel = useMemo(() => {
    if (kbFilter) return knowledgeBases.find((item) => item.id === kbFilter)?.name ?? "Selected source";
    if (sourceFilter) return sourceFilter;
    return "";
  }, [kbFilter, knowledgeBases, sourceFilter]);

  const filtered = useMemo(() => {
    const needle = query.toLowerCase().trim();
    return docs.filter((doc) => {
      if (kbFilter && doc.knowledge_base_id !== kbFilter) return false;
      if (sourceFilter && doc.knowledge_base_name.toLowerCase() !== sourceFilter.toLowerCase()) return false;
      if (!needle) return true;
      return (
        doc.title.toLowerCase().includes(needle) ||
        doc.status.toLowerCase().includes(needle) ||
        doc.source_type.toLowerCase().includes(needle) ||
        doc.knowledge_base_name.toLowerCase().includes(needle)
      );
    });
  }, [docs, kbFilter, query, sourceFilter]);

  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle={
          activeFilterLabel
            ? `Indexed documents from ${activeFilterLabel}.`
            : "Indexed documents across Jira, Confluence, and local uploads."
        }
        actions={
          <div className="flex items-center gap-2.5">
            <span className="rounded-full border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-ink-500">
              {activeFilterLabel ? `${filtered.length} documents in ${activeFilterLabel}` : status}
            </span>
            {activeFilterLabel && (
              <Link
                href="/documents"
                className="inline-flex items-center rounded-[10px] border border-line bg-white px-3 py-2 text-[12.5px] font-semibold text-ink-700 transition hover:border-brand-200 hover:text-brand-600"
              >
                Clear filter
              </Link>
            )}
            <input ref={fileInput} type="file" accept=".md,.txt,.pdf" className="hidden" onChange={(event) => void uploadFile(event)} />
            <PrimaryButton onClick={() => fileInput.current?.click()} disabled={busy}>
              <Upload size={15} /> Upload Documents
            </PrimaryButton>
          </div>
        }
      />

      <Card className="animate-rise-1">
        <div className="flex items-center gap-3 border-b border-line p-4">
          <label className="flex h-10 flex-1 cursor-text items-center gap-2.5 rounded-[10px] border border-line bg-canvas px-3.5 transition focus-within:border-brand-300 focus-within:bg-white focus-within:ring-4 focus-within:ring-brand-50">
            <Search size={15} className="text-ink-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search documents by title or status..."
              className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-ink-400"
            />
          </label>
          <GhostButton onClick={() => void refresh()} disabled={busy}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Refresh
          </GhostButton>
          <GhostButton onClick={() => setDocs((items) => [...items].sort((a, b) => b.updated_at.localeCompare(a.updated_at)))}>
            <ArrowUpDown size={14} /> Sort: Last updated
          </GhostButton>
        </div>

        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Document</th>
              <th className="font-bold">Source</th>
              <th className="font-bold">Version</th>
              <th className="font-bold">Last Updated</th>
              <th className="font-bold">Status</th>
              <th className="pr-5 text-right font-bold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {filtered.map((doc) => {
              const statusKey = doc.status.toLowerCase() as keyof typeof freshTone;
              return (
                <tr key={doc.id} className="group transition hover:bg-brand-50/30">
                  <td className="py-3.5 pl-5">
                    <span className="text-[13.5px] font-semibold text-ink-900 transition group-hover:text-brand-600">
                      {doc.title}
                    </span>
                    {doc.error && <p className="mt-1 text-[11.5px] text-rose-600">{doc.error}</p>}
                  </td>
                  <td>
                    <span className="inline-flex items-center gap-2 text-[13px] font-medium text-ink-700">
                      <FileText size={16} /> {doc.source_type}
                      <span className="text-ink-400">·</span>
                      <span className="max-w-[180px] truncate text-ink-500">{doc.knowledge_base_name}</span>
                    </span>
                  </td>
                  <td className="text-[13px] text-ink-700">v{doc.current_version}</td>
                  <td className="text-[13px] text-ink-500">{new Date(doc.updated_at).toLocaleString()}</td>
                  <td>
                    <Badge tone={freshTone[statusKey] ?? "gray"}>{doc.status}</Badge>
                  </td>
                  <td className="pr-5">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => void reindex(doc)}
                        className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500"
                        aria-label={`Reindex ${doc.title}`}
                      >
                        <Eye size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(doc)}
                        className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-rose-50 hover:text-rose-500"
                        aria-label={`Delete ${doc.title}`}
                      >
                        <Trash2 size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setStatus(`${doc.title} selected`)}
                        className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500"
                        aria-label="More actions"
                      >
                        <MoreHorizontal size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!filtered.length && (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-[13px] text-ink-500">
                  No documents match the current filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div className="flex items-center justify-between border-t border-line px-5 py-3.5 text-[12.5px] text-ink-500">
          <span>
            Showing {filtered.length} of {docs.length} indexed documents
            {activeFilterLabel ? ` · filtered by ${activeFilterLabel}` : ""}
          </span>
          <div className="flex gap-1.5">
            {["1"].map((page, index) => (
              <button
                key={page}
                type="button"
                className={cx(
                  "flex h-8 min-w-8 items-center justify-center rounded-[8px] px-2 text-[12.5px] font-semibold transition",
                  index === 0 ? "bg-brand-500 text-white" : "text-ink-500 hover:bg-canvas"
                )}
              >
                {page}
              </button>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
