"use client";

import { useState } from "react";
import { CheckCircle2, Cloud, Database, History, Loader2, Plus, RefreshCw, SquareKanban } from "lucide-react";
import { Badge, Card, CardTitle, GhostButton, PageHeader, PrimaryButton, cx } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";
import { cvumApi } from "@/lib/cvum-api";
import { sourceFamily } from "@/components/source-metrics";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatDate(value: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function pendingDocuments(
  source:
    | {
        documents: number;
        ready_documents: number;
        failed_documents: number;
        pending_documents?: number;
      }
    | undefined
) {
  if (!source) return 0;
  if (typeof source.pending_documents === "number") return source.pending_documents;
  return Math.max(0, source.documents - source.ready_documents - source.failed_documents);
}

function connectorLabel(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function SourceIcon({ family }: { family: string }) {
  const iconClass = "flex h-9 w-9 items-center justify-center rounded-[10px] border border-line bg-white";
  if (family === "jira") {
    return (
      <span className={`${iconClass} text-brand-600`}>
        <SquareKanban size={18} />
      </span>
    );
  }
  if (family === "confluence") {
    return (
      <span className={`${iconClass} text-sky-600`}>
        <Cloud size={18} />
      </span>
    );
  }
  return (
    <span className={`${iconClass} text-brand-500`}>
      <Database size={18} />
    </span>
  );
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function DataSourcesClient() {
  const { metrics, confluence, jira, loading, error, refresh } = useLiveMetrics();
  const [syncing, setSyncing] = useState(false);
  const [syncingJira, setSyncingJira] = useState(false);
  const [status, setStatus] = useState("");

  async function refreshAfterSync(label: string, queued: number, changed: number) {
    await refresh({ force: true });
    if (changed <= 0) return;
    for (let attempt = 0; attempt < 6; attempt += 1) {
      await sleep(1500);
      setStatus(`${number(queued)} ${label} queued · refreshing live counts`);
      await refresh({ force: true });
    }
  }

  async function syncConfluence() {
    setSyncing(true);
    setStatus("Syncing Confluence");
    try {
      const result = await cvumApi.syncConfluence();
      setStatus(`${number(result.total_pages)} Confluence pages queued`);
      await refreshAfterSync("Confluence pages", result.total_pages, result.created + result.updated);
    } catch (cause) {
      setStatus(cause instanceof Error ? cause.message : "Confluence sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function syncJira() {
    setSyncingJira(true);
    setStatus("Syncing Jira");
    try {
      const result = await cvumApi.syncJira();
      setStatus(`${number(result.total_issues)} Jira issues queued`);
      await refreshAfterSync("Jira issues", result.total_issues, result.created + result.updated);
    } catch (cause) {
      setStatus(cause instanceof Error ? cause.message : "Jira sync failed");
    } finally {
      setSyncingJira(false);
    }
  }

  const visibleSources = metrics?.sources ?? [];
  const totalPending = Math.max(
    0,
    (metrics?.documents_total ?? 0) - (metrics?.documents_ready ?? 0) - (metrics?.documents_failed ?? 0)
  );

  return (
    <div>
      <PageHeader
        title="Data Sources"
        subtitle="Live source inventory from indexed documents and configured connectors."
        actions={
          <div className="flex items-center gap-2.5">
            <span className="rounded-full border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-ink-500">
              {status || (loading ? "Loading" : "Live")}
            </span>
            <GhostButton disabled>
              <Plus size={15} /> Add source
            </GhostButton>
            <PrimaryButton
              disabled={syncing || confluence?.configured === false}
              onClick={() => void syncConfluence()}
            >
              {syncing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
              Sync Confluence
            </PrimaryButton>
            <PrimaryButton
              disabled={syncingJira || jira?.configured === false}
              onClick={() => void syncJira()}
            >
              {syncingJira ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
              Sync Jira
            </PrimaryButton>
          </div>
        }
      />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <div className="grid grid-cols-4 gap-5 animate-rise-1">
        {[
          { label: "Documents synced", value: metrics?.documents_total ?? 0 },
          { label: "Ready documents", value: metrics?.documents_ready ?? 0 },
          { label: "Pending ingestion", value: totalPending },
          { label: "Failed documents", value: metrics?.documents_failed ?? 0 },
        ].map((stat) => (
          <Card key={stat.label} className="p-5">
            <p className="text-[12.5px] font-semibold text-ink-500">{stat.label}</p>
            <p className="mt-2 text-[26px] font-bold tracking-[-0.02em] text-ink-900">
              {loading ? <Loader2 size={20} className="animate-spin text-brand-500" /> : number(stat.value)}
            </p>
          </Card>
        ))}
      </div>

      <Card className="mt-5 animate-rise-2">
        <div className="p-5 pb-0">
          <CardTitle
            icon={Database}
            title="All Sources"
            right={<span className="text-[12px] font-semibold text-ink-400">No synthetic connectors shown</span>}
          />
        </div>
        <table className="mt-3 w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Source</th>
              <th className="font-bold">Documents</th>
              <th className="font-bold">Ready</th>
              <th className="font-bold">Pending</th>
              <th className="font-bold">Failed</th>
              <th className="font-bold">Chunks</th>
              <th className="font-bold">Last local update</th>
              <th className="font-bold">Last sync</th>
              <th className="pr-5 font-bold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {visibleSources.map((source) => (
              <tr key={`${source.name}-${source.source_type}-${source.source_scope ?? "global"}`} className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5">
                  <span className="inline-flex items-center gap-3">
                    <SourceIcon family={sourceFamily(source)} />
                    <span className="text-[13.5px] font-bold text-ink-900">{source.name}</span>
                  </span>
                </td>
                <td className="text-[13px] font-semibold text-ink-900">{number(source.documents)}</td>
                <td className="text-[13px] text-ink-700">{number(source.ready_documents)}</td>
                <td className="text-[13px] text-ink-700">{number(pendingDocuments(source))}</td>
                <td className="text-[13px] text-ink-700">{number(source.failed_documents)}</td>
                <td className="text-[13px] text-ink-700">{number(source.chunks_active ?? 0)}</td>
                <td className="text-[13px] text-ink-500">{formatDate(source.last_updated_at)}</td>
                <td className="max-w-[220px] pr-3 text-[12.5px] leading-5 text-ink-500">
                  {source.last_run_detail ? (
                    <>
                      <span className="font-semibold text-ink-700">{formatDate(source.last_run_at)}</span>
                      <br />
                      {source.last_run_detail}
                    </>
                  ) : (
                    "No recorded sync"
                  )}
                </td>
                <td className="pr-5">
                  <Badge tone={source.health === "failing" || source.health === "syncing" ? "amber" : "green"}>
                    <CheckCircle2 size={11} className={cx("mr-1", source.failed_documents > 0 && "text-amber-600")} />
                    {source.health === "failing" ? "Needs review" : source.health === "syncing" ? "Indexing" : "Healthy"}
                  </Badge>
                </td>
              </tr>
            ))}

            {!loading && !visibleSources.length && (
              <tr>
                <td className="px-5 py-6 text-[13px] text-ink-500" colSpan={9}>
                  No sources are configured or indexed yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Card className="mt-5 animate-rise-3">
        <div className="p-5 pb-0">
          <CardTitle icon={History} title="Recent Connector Runs" />
        </div>
        <table className="mt-3 w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Connector</th>
              <th className="font-bold">Total</th>
              <th className="font-bold">Created</th>
              <th className="font-bold">Updated</th>
              <th className="font-bold">Skipped</th>
              <th className="font-bold">Failed</th>
              <th className="font-bold">Run time</th>
              <th className="pr-5 font-bold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {(metrics?.connector_runs ?? []).map((run) => (
              <tr key={`${run.connector}-${run.created_at}`} className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5 text-[13.5px] font-bold text-ink-900">{connectorLabel(run.connector)}</td>
                <td className="text-[13px] text-ink-700">{number(run.total)}</td>
                <td className="text-[13px] text-ink-700">{number(run.created)}</td>
                <td className="text-[13px] text-ink-700">{number(run.updated)}</td>
                <td className="text-[13px] text-ink-700">{number(run.skipped)}</td>
                <td className="text-[13px] text-ink-700">{number(run.failed)}</td>
                <td className="text-[13px] text-ink-500">{formatDate(run.created_at)}</td>
                <td className="pr-5">
                  <Badge tone={run.failed ? "red" : "green"}>{run.status}</Badge>
                </td>
              </tr>
            ))}
            {!loading && !(metrics?.connector_runs ?? []).length && (
              <tr>
                <td className="px-5 py-6 text-[13px] text-ink-500" colSpan={8}>
                  No connector sync runs are recorded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
