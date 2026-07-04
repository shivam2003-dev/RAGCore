"use client";

import { useState } from "react";
import { CheckCircle2, Cloud, Database, Loader2, Plus, RefreshCw, SquareKanban } from "lucide-react";
import { Badge, Card, CardTitle, GhostButton, PageHeader, PrimaryButton, cx } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";
import { kimbalApi } from "@/lib/kimbal-api";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

function formatDate(value: string | null) {
  if (!value) return "Never";
  return new Date(value).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export function DataSourcesClient() {
  const { metrics, confluence, jira, loading, error, refresh } = useLiveMetrics();
  const [syncing, setSyncing] = useState(false);
  const [syncingJira, setSyncingJira] = useState(false);
  const [status, setStatus] = useState("");

  async function syncConfluence() {
    setSyncing(true);
    setStatus("Syncing Confluence");
    try {
      const result = await kimbalApi.syncConfluence(undefined, 100);
      setStatus(`${result.total_pages} Confluence pages queued`);
      await refresh();
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
      const result = await kimbalApi.syncJira(undefined, 100);
      setStatus(`${result.total_issues} Jira issues queued`);
      await refresh();
    } catch (cause) {
      setStatus(cause instanceof Error ? cause.message : "Jira sync failed");
    } finally {
      setSyncingJira(false);
    }
  }

  const confluenceSource = metrics?.sources.find((source) => source.name.toLowerCase() === "confluence");
  const jiraSource = metrics?.sources.find((source) => source.name.toLowerCase() === "jira");
  const visibleSources = metrics?.sources.filter((source) => !["confluence", "jira"].includes(source.name.toLowerCase())) ?? [];

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
          { label: "Indexed source types", value: metrics?.sources.length ?? 0 },
          { label: "Documents indexed", value: metrics?.documents_total ?? 0 },
          { label: "Ready documents", value: metrics?.documents_ready ?? 0 },
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
              <th className="font-bold">Failed</th>
              <th className="font-bold">Last local update</th>
              <th className="pr-5 font-bold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {confluence && (
              <tr className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5">
                  <span className="inline-flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-line bg-white text-sky-600">
                      <Cloud size={18} />
                    </span>
                    <span className="text-[13.5px] font-bold text-ink-900">Confluence {confluence.space_key}</span>
                  </span>
                </td>
                <td className="text-[13px] font-semibold text-ink-900">{number(confluenceSource?.documents ?? 0)}</td>
                <td className="text-[13px] text-ink-700">{number(confluenceSource?.ready_documents ?? 0)}</td>
                <td className="text-[13px] text-ink-700">{number(confluenceSource?.failed_documents ?? 0)}</td>
                <td className="text-[13px] text-ink-500">{formatDate(confluenceSource?.last_updated_at ?? null)}</td>
                <td className="pr-5">
                  <Badge tone={confluence.configured ? "green" : "amber"}>
                    {confluence.configured ? "Configured" : "Needs config"}
                  </Badge>
                </td>
              </tr>
            )}

            {jira && (
              <tr className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5">
                  <span className="inline-flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-line bg-white text-brand-600">
                      <SquareKanban size={18} />
                    </span>
                    <span className="text-[13.5px] font-bold text-ink-900">
                      Jira {jira.project_key || "project"} board {jira.board_id}
                    </span>
                  </span>
                </td>
                <td className="text-[13px] font-semibold text-ink-900">{number(jiraSource?.documents ?? 0)}</td>
                <td className="text-[13px] text-ink-700">{number(jiraSource?.ready_documents ?? 0)}</td>
                <td className="text-[13px] text-ink-700">{number(jiraSource?.failed_documents ?? 0)}</td>
                <td className="text-[13px] text-ink-500">{formatDate(jiraSource?.last_updated_at ?? null)}</td>
                <td className="pr-5">
                  <Badge tone={jira.configured ? "green" : "amber"}>
                    {jira.configured ? "Configured" : "Needs config"}
                  </Badge>
                </td>
              </tr>
            )}

            {visibleSources.map((source) => (
              <tr key={`${source.name}-${source.source_type}`} className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5">
                  <span className="inline-flex items-center gap-3">
                    <span className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-line bg-white text-brand-500">
                      <Database size={18} />
                    </span>
                    <span className="text-[13.5px] font-bold text-ink-900">{source.name}</span>
                  </span>
                </td>
                <td className="text-[13px] font-semibold text-ink-900">{number(source.documents)}</td>
                <td className="text-[13px] text-ink-700">{number(source.ready_documents)}</td>
                <td className="text-[13px] text-ink-700">{number(source.failed_documents)}</td>
                <td className="text-[13px] text-ink-500">{formatDate(source.last_updated_at)}</td>
                <td className="pr-5">
                  <Badge tone={source.failed_documents ? "amber" : "green"}>
                    <CheckCircle2 size={11} className={cx("mr-1", source.failed_documents > 0 && "text-amber-600")} />
                    {source.failed_documents ? "Needs review" : "Healthy"}
                  </Badge>
                </td>
              </tr>
            ))}

            {!loading && !confluence && !jira && !visibleSources.length && (
              <tr>
                <td className="px-5 py-6 text-[13px] text-ink-500" colSpan={6}>
                  No sources are configured or indexed yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
