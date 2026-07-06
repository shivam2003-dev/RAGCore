"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Cloud, Clock, Database, FileText, Loader2, Plus, RefreshCw, ShieldCheck, SquareKanban } from "lucide-react";
import { Badge, Card, CardLink, GhostButton, PageHeader, PrimaryButton } from "@/components/ui";
import { kimbalApi, type ConfluenceStatus, type JiraStatus, type KnowledgeBase } from "@/lib/kimbal-api";

type SourceRow = {
  kb: KnowledgeBase;
  docsTotal: number;
};

const LEGACY_SEED_KB_NAME = "CVUM Local Runbook";

export function KnowledgeSourcesClient() {
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [confluence, setConfluence] = useState<ConfluenceStatus | null>(null);
  const [jira, setJira] = useState<JiraStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncingConfluence, setSyncingConfluence] = useState(false);
  const [syncingJira, setSyncingJira] = useState(false);
  const [status, setStatus] = useState("Loading live sources");

  async function refresh() {
    setLoading(true);
    try {
      await kimbalApi.ensureSession();
      const [kbs, confluenceStatus, jiraStatus] = await Promise.all([
        kimbalApi.listKnowledgeBases(),
        kimbalApi.confluenceStatus().catch(() => null),
        kimbalApi.jiraStatus().catch(() => null),
      ]);
      const rows = await Promise.all(
        kbs.map(async (kb) => {
          const docs = await kimbalApi.listDocuments(kb.id, 1);
          return { kb, docsTotal: docs.total };
        })
      );
      const visibleRows = rows.filter(({ kb }) => kb.name !== LEGACY_SEED_KB_NAME);
      setSources(visibleRows);
      setConfluence(confluenceStatus);
      setJira(jiraStatus);
      setStatus(`${visibleRows.length} knowledge bases loaded`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Failed to load sources");
    } finally {
      setLoading(false);
    }
  }

  async function syncConfluence() {
    setSyncingConfluence(true);
    setStatus("Syncing Confluence DevOps1");
    try {
      await kimbalApi.ensureSession();
      const result = await kimbalApi.syncConfluence();
      setStatus(
        `Confluence sync queued: ${result.created} created, ${result.updated} updated, ${result.skipped} unchanged`
      );
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Confluence sync failed");
    } finally {
      setSyncingConfluence(false);
    }
  }

  async function syncJira() {
    setSyncingJira(true);
    setStatus("Syncing Jira DEVO");
    try {
      await kimbalApi.ensureSession();
      const result = await kimbalApi.syncJira();
      setStatus(
        `Jira sync queued: ${result.created} created, ${result.updated} updated, ${result.skipped} unchanged`
      );
      await refresh();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Jira sync failed");
    } finally {
      setSyncingJira(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const confluenceKb = sources.find(({ kb }) => kb.name === (confluence?.default_kb_name ?? "Confluence DevOps1"));
  const jiraKb = sources.find(({ kb }) => kb.name === (jira?.default_kb_name ?? "Jira DEVO"));
  const documentsHref = (kb?: KnowledgeBase) => (kb ? `/documents?kb=${encodeURIComponent(kb.id)}` : "/documents");

  return (
    <div>
      <PageHeader
        title="Knowledge Sources"
        subtitle="Live knowledge bases feeding the CVUM retrieval API."
        actions={
          <div className="flex items-center gap-2.5">
            <span className="rounded-full border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-ink-500">
              {status}
            </span>
            <GhostButton
              onClick={() => void syncConfluence()}
              disabled={syncingConfluence || confluence?.configured === false}
            >
              {syncingConfluence ? <Loader2 size={15} className="animate-spin" /> : <Cloud size={15} />}
              Sync Confluence
            </GhostButton>
            <GhostButton
              onClick={() => void syncJira()}
              disabled={syncingJira || jira?.configured === false}
            >
              {syncingJira ? <Loader2 size={15} className="animate-spin" /> : <SquareKanban size={15} />}
              Sync Jira
            </GhostButton>
            <Link
              href="/documents"
              className="inline-flex items-center gap-2 rounded-[10px] bg-brand-500 px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.5)] transition hover:bg-brand-600"
            >
              <Plus size={15} /> Upload documents
            </Link>
          </div>
        }
      />

      <Card className="mb-5 flex items-center justify-between gap-4 p-5 animate-rise-1">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] border border-line bg-white text-sky-600 shadow-[var(--shadow-card)]">
            <Cloud size={21} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[15px] font-bold text-ink-900">Confluence DevOps1</p>
              <Badge tone={confluence?.configured ? "green" : "amber"}>
                {confluence?.configured ? "Configured" : "Needs config"}
              </Badge>
              <Badge tone="blue">Read only</Badge>
            </div>
            <p className="mt-1 text-[12.5px] text-ink-500">
              {confluence?.base_url
                ? `${confluence.base_url} · space ${confluence.space_key}`
                : "Set CONFLUENCE_BASE_URL, CONFLUENCE_API_TOKEN, and for Cloud API tokens CONFLUENCE_EMAIL."}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <CardLink href={documentsHref(confluenceKb?.kb)}>View docs</CardLink>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-canvas px-3 py-1.5 text-[12px] font-semibold text-ink-600">
            <ShieldCheck size={13} className="text-emerald-500" />
            GET-only API calls
          </span>
          <PrimaryButton
            onClick={() => void syncConfluence()}
            disabled={syncingConfluence || confluence?.configured === false}
          >
            {syncingConfluence ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Sync
          </PrimaryButton>
        </div>
      </Card>

      <Card className="mb-5 flex items-center justify-between gap-4 p-5 animate-rise-1">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] border border-line bg-white text-brand-600 shadow-[var(--shadow-card)]">
            <SquareKanban size={21} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[15px] font-bold text-ink-900">Jira {jira?.project_key || "DEVO"}</p>
              <Badge tone={jira?.configured ? "green" : "amber"}>
                {jira?.configured ? "Configured" : "Needs config"}
              </Badge>
              <Badge tone="blue">Read only</Badge>
            </div>
            <p className="mt-1 text-[12.5px] text-ink-500">
              {jira?.base_url
                ? `${jira.base_url} · board ${jira.board_id}`
                : "Set JIRA_BASE_URL and JIRA_BOARD_ID; credentials can reuse the Atlassian token."}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <CardLink href={documentsHref(jiraKb?.kb)}>View docs</CardLink>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-canvas px-3 py-1.5 text-[12px] font-semibold text-ink-600">
            <ShieldCheck size={13} className="text-emerald-500" />
            GET-only API calls
          </span>
          <PrimaryButton
            onClick={() => void syncJira()}
            disabled={syncingJira || jira?.configured === false}
          >
            {syncingJira ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Sync
          </PrimaryButton>
        </div>
      </Card>

      <div className="grid grid-cols-3 gap-5 animate-rise-1">
        {sources.map(({ kb, docsTotal }) => (
          <Card key={kb.id} className="group p-5 transition hover:shadow-[var(--shadow-pop)]">
            <div className="flex items-start justify-between">
              <span className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-line bg-white text-brand-500 shadow-[var(--shadow-card)]">
                <Database size={22} />
              </span>
              <Badge tone="green">Synced</Badge>
            </div>
            <p className="mt-3.5 text-[15px] font-bold text-ink-900">{kb.name}</p>
            <p className="mt-0.5 text-[12.5px] text-ink-500">{kb.description || "Hybrid RAG knowledge base"}</p>
            <div className="mt-4 flex items-center gap-4 border-t border-line pt-3.5 text-[12px] text-ink-500">
              <Link
                href={documentsHref(kb)}
                className="inline-flex items-center gap-1.5 rounded-md transition hover:text-brand-600"
                aria-label={`View ${docsTotal} documents in ${kb.name}`}
              >
                <FileText size={13} className="text-ink-400" />
                <strong className="font-semibold text-ink-900">{docsTotal}</strong> docs
              </Link>
              <span className="inline-flex items-center gap-1.5">
                <Clock size={13} className="text-ink-400" />
                {new Date(kb.created_at).toLocaleDateString()}
              </span>
              <button
                type="button"
                onClick={() => void refresh()}
                className="ml-auto text-ink-400 transition hover:text-brand-500"
                aria-label={`Sync ${kb.name}`}
              >
                <RefreshCw size={14} />
              </button>
            </div>
          </Card>
        ))}

        <Link
          href="/documents"
          className="flex min-h-[176px] flex-col items-center justify-center gap-2.5 rounded-[18px] border-2 border-dashed border-ink-300/60 text-ink-400 transition hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-500"
        >
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-[var(--shadow-card)]">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
          </span>
          <span className="text-[13.5px] font-semibold">Upload documents</span>
        </Link>
      </div>

      <div className="mt-6 animate-rise-2">
        <CardLink href="/documents">Review indexed documents</CardLink>
      </div>
    </div>
  );
}
