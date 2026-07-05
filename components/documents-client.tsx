"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpDown, Eye, FileText, Loader2, MoreHorizontal, RefreshCw, Search, Trash2, Upload, X } from "lucide-react";
import { Card, PageHeader, PrimaryButton, GhostButton, Badge } from "@/components/ui";
import { kimbalApi, type DocumentLineage, type DocumentOut, type KnowledgeBase } from "@/lib/kimbal-api";

const freshTone = { ready: "green", processing: "amber", uploaded: "amber", failed: "red", deleted: "gray" } as const;
const LEGACY_SEED_KB_NAME = "Kimbal Local Runbook";
const PAGE_SIZE = 500;

export function DocumentsClient() {
  const searchParams = useSearchParams();
  const kbFilter = searchParams.get("kb") ?? "";
  const sourceFilter = searchParams.get("source") ?? "";
  const fileInput = useRef<HTMLInputElement>(null);
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [docs, setDocs] = useState<Array<DocumentOut & { knowledge_base_name: string }>>([]);
  const [totalDocs, setTotalDocs] = useState(0);
  const [page, setPage] = useState(0);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("Loading documents");
  const [busy, setBusy] = useState(false);
  const [lineage, setLineage] = useState<DocumentLineage | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);

  async function refresh(pageOverride = page) {
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
      const kbById = new Map(visibleKbs.map((item) => [item.id, item.name]));
      const sourceKb = sourceFilter
        ? visibleKbs.find((item) => item.name.toLowerCase() === sourceFilter.toLowerCase())
        : undefined;
      const selectedKbId = kbFilter || sourceKb?.id;
      const list = await kimbalApi.listDocuments(selectedKbId || undefined, PAGE_SIZE, pageOverride * PAGE_SIZE);
      const pageDocs = list.items.map((doc) => ({
        ...doc,
        knowledge_base_name: doc.knowledge_base_name ?? kbById.get(doc.knowledge_base_id) ?? "Unknown source",
      }));
      setDocs(pageDocs);
      setTotalDocs(list.total);
      setPage(pageOverride);
      setStatus(`${list.total} documents available across all pages`);
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
      await refresh(0);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Upload failed");
      setBusy(false);
    }
  }

  async function reindex(doc: DocumentOut) {
    setStatus(`Re-indexing ${doc.title}`);
    await kimbalApi.reindexDocument(doc.id);
    await refresh(page);
  }

  async function remove(doc: DocumentOut) {
    setStatus(`Deleting ${doc.title}`);
    await kimbalApi.deleteDocument(doc.id);
    await refresh(page);
  }

  async function showLineage(doc: DocumentOut) {
    setLineageLoading(true);
    setStatus(`Loading lineage for ${doc.title}`);
    try {
      setLineage(await kimbalApi.documentLineage(doc.id));
      setStatus(`Lineage loaded for ${doc.title}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load lineage");
    } finally {
      setLineageLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh(0);
    }, 0);
    return () => window.clearTimeout(timer);
    // Reload when URL source filters change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbFilter, sourceFilter]);

  const activeFilterLabel = kbFilter
    ? (knowledgeBases.find((item) => item.id === kbFilter)?.name ?? "Selected source")
    : sourceFilter;

  const pageCount = Math.max(1, Math.ceil(totalDocs / PAGE_SIZE));
  const canPrevious = page > 0;
  const canNext = page + 1 < pageCount;

  const needle = query.toLowerCase().trim();
  const filtered = docs.filter((doc) => {
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
              placeholder="Search loaded documents by title or status..."
              className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-ink-400"
            />
          </label>
          <GhostButton onClick={() => void refresh(page)} disabled={busy}>
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
                        onClick={() => void showLineage(doc)}
                        className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500"
                        aria-label={`View lineage for ${doc.title}`}
                      >
                        {lineageLoading ? <Loader2 size={15} className="animate-spin" /> : <Eye size={15} />}
                      </button>
                      <button
                        type="button"
                        onClick={() => void reindex(doc)}
                        className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500"
                        aria-label={`Reindex ${doc.title}`}
                      >
                        <RefreshCw size={15} />
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
            Showing {filtered.length} of {totalDocs} documents
            {activeFilterLabel ? ` · filtered by ${activeFilterLabel}` : ""}
          </span>
          <div className="flex gap-1.5">
            <button
              type="button"
              disabled={!canPrevious || busy}
              onClick={() => void refresh(page - 1)}
              className="flex h-8 min-w-8 items-center justify-center rounded-[8px] px-2 text-[12.5px] font-semibold text-ink-500 transition hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-45"
            >
              Previous
            </button>
            <span className="flex h-8 min-w-8 items-center justify-center rounded-[8px] bg-brand-500 px-2 text-[12.5px] font-semibold text-white">
              {page + 1} / {pageCount}
            </span>
            <button
              type="button"
              disabled={!canNext || busy}
              onClick={() => void refresh(page + 1)}
              className="flex h-8 min-w-8 items-center justify-center rounded-[8px] px-2 text-[12.5px] font-semibold text-ink-500 transition hover:bg-canvas disabled:cursor-not-allowed disabled:opacity-45"
            >
              Next
            </button>
          </div>
        </div>
      </Card>
      {lineage && <LineageDrawer lineage={lineage} onClose={() => setLineage(null)} />}
    </div>
  );
}

function LineageDrawer({ lineage, onClose }: { lineage: DocumentLineage; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end bg-ink-950/20 p-4 backdrop-blur-sm">
      <div className="max-h-[92vh] w-full max-w-[680px] overflow-auto rounded-[18px] border border-line bg-white shadow-soft">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-line bg-white p-5">
          <div>
            <p className="text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">Document lineage</p>
            <h2 className="mt-1 text-[20px] font-black tracking-[-0.02em] text-ink-950">{lineage.title}</h2>
            <p className="mt-1 text-[12.5px] font-semibold text-ink-500">{lineage.knowledge_base_name ?? "Unknown source"}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-[10px] text-ink-400 transition hover:bg-canvas hover:text-ink-900"
            aria-label="Close lineage"
          >
            <X size={17} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 p-5">
          <LineageMetric label="Source system" value={lineage.source_system} />
          <LineageMetric label="Status" value={lineage.status} />
          <LineageMetric label="Source id" value={lineage.source_id ?? "N/A"} />
          <LineageMetric label="Source version" value={String(lineage.source_version ?? "N/A")} />
          <LineageMetric label="Source updated" value={lineage.source_updated_at ?? "N/A"} />
          <LineageMetric label="Embedding model" value={lineage.embedding_model ?? "N/A"} />
          <LineageMetric label="Chunks" value={`${lineage.active_chunk_count} active / ${lineage.chunk_count} total`} />
          <LineageMetric label="Stored versions" value={String(lineage.versions.length)} />
        </div>

        <div className="border-t border-line px-5 py-4">
          <p className="text-[12px] font-bold uppercase tracking-[0.08em] text-ink-400">Original source</p>
          {lineage.source_url ? (
            <a className="mt-2 block break-all text-[13px] font-semibold text-brand-600 hover:underline" href={lineage.source_url} target="_blank" rel="noreferrer">
              {lineage.source_url}
            </a>
          ) : (
            <p className="mt-2 text-[13px] text-ink-500">No source URL stored for this document.</p>
          )}
        </div>

        <div className="border-t border-line px-5 py-4">
          <p className="text-[12px] font-bold uppercase tracking-[0.08em] text-ink-400">Versions</p>
          <div className="mt-3 divide-y divide-line rounded-[12px] border border-line">
            {lineage.versions.map((version) => (
              <div key={`${version.version}-${version.file_sha256}`} className="grid grid-cols-[80px_1fr_120px] gap-3 px-3 py-2.5 text-[12.5px]">
                <span className="font-bold text-ink-900">v{version.version}</span>
                <span className="truncate font-mono text-ink-500">{version.file_sha256}</span>
                <span className="text-right font-semibold text-ink-500">{new Intl.NumberFormat().format(version.file_size_bytes)} bytes</span>
              </div>
            ))}
            {!lineage.versions.length && <p className="px-3 py-3 text-[13px] text-ink-500">No stored versions found.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}

function LineageMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[12px] border border-line bg-canvas px-3 py-3">
      <p className="text-[11.5px] font-semibold text-ink-400">{label}</p>
      <p className="mt-1 break-words text-[13px] font-bold text-ink-900">{value}</p>
    </div>
  );
}
