"use client";

import { useEffect, useState } from "react";
import { Database, ExternalLink, FileWarning, HeartPulse, History, Loader2, RefreshCw } from "lucide-react";
import { Badge, Card, CardLink, CardTitle, GhostButton, PageHeader, ProgressBar } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";
import { kimbalApi, type FreshnessResponse, type Project } from "@/lib/kimbal-api";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

function age(seconds: number | null) {
  if (seconds == null) return "No successful sync";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function ContentHealthClient() {
  const { metrics, loading: metricsLoading, error: metricsError, refresh } = useLiveMetrics();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [freshness, setFreshness] = useState<FreshnessResponse | null>(null);
  const [loadingFreshness, setLoadingFreshness] = useState(true);
  const [freshnessError, setFreshnessError] = useState("");

  async function loadFreshness(targetProjectId: string) {
    if (!targetProjectId) return;
    setLoadingFreshness(true);
    setFreshnessError("");
    try {
      setFreshness(await kimbalApi.freshness(targetProjectId));
    } catch (cause) {
      setFreshnessError(cause instanceof Error ? cause.message : "Could not load freshness data");
    } finally {
      setLoadingFreshness(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadProjects() {
      try {
        const [rows, user] = await Promise.all([kimbalApi.listProjects(), kimbalApi.ensureSession()]);
        if (cancelled) return;
        const selected = rows.find((item) => item.id === user.default_project_id)?.id ?? rows[0]?.id ?? "";
        setProjects(rows);
        setProjectId(selected);
        await loadFreshness(selected);
      } catch (cause) {
        if (!cancelled) setFreshnessError(cause instanceof Error ? cause.message : "Could not load projects");
      }
    }
    void loadProjects();
    return () => { cancelled = true; };
  }, []);

  const loading = metricsLoading || loadingFreshness;
  const error = metricsError || freshnessError;
  const total = metrics?.documents_total ?? 0;
  const score = freshness?.score ?? null;
  const checks = [
    { label: "Stale sources", value: freshness?.stale_sources ?? 0 },
    { label: "Failing sources", value: freshness?.failing_sources ?? 0 },
    { label: "Outdated Slack resolutions", value: freshness?.outdated_slack_resolutions ?? 0 },
    { label: "Repository branch lag", value: freshness?.repository_branch_lag ?? 0 },
    { label: "Replaced documents", value: freshness?.replaced_documents ?? 0 },
  ];

  async function refreshAll() {
    await Promise.all([refresh({ force: true }), loadFreshness(projectId)]);
  }

  return (
    <div>
      <PageHeader
        title="Knowledge Freshness Center"
        subtitle="Live sync health, source age, branch-index lag, replacement lineage, and remediation."
        actions={<GhostButton onClick={() => void refreshAll()} disabled={loading}><RefreshCw size={15} /> Refresh</GhostButton>}
      />

      <Card className="mb-5 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="text-[12px] font-semibold text-ink-600">Project Lens<select aria-label="Freshness project" value={projectId} onChange={(event) => { setProjectId(event.target.value); void loadFreshness(event.target.value); }} className="mt-1 h-10 w-full min-w-[220px] rounded-[10px] border border-line bg-white px-3 text-[13px] outline-none focus:border-brand-300 sm:w-auto">{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
          <p className="text-[12px] leading-5 text-ink-500 sm:ml-auto">Health is calculated only from sources authorized in the selected project.</p>
        </div>
      </Card>

      {error && <div role="alert"><Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">{error}</Card></div>}

      <div className="grid grid-cols-1 gap-5 animate-rise-1 xl:grid-cols-12">
        <Card className="p-6 xl:col-span-4">
          <CardTitle icon={HeartPulse} title="Freshness Score" tint="bg-rose-50 text-rose-400" />
          <div className="mt-6 flex items-end gap-3">
            <p className="text-[52px] font-bold leading-none tracking-[-0.03em] text-ink-900">{loading ? <Loader2 size={34} className="animate-spin text-brand-500" /> : score ?? "N/A"}</p>
            <div className="pb-1.5"><Badge tone={score == null ? "gray" : score >= 90 ? "green" : score >= 70 ? "amber" : "red"}>{score == null ? "No data" : "Live"}</Badge><p className="mt-1 text-[12px] text-ink-500">{number(total)} documents indexed</p></div>
          </div>
          <div className="mt-5"><ProgressBar value={score ?? 0} /></div>
          <div className="mt-5 border-t border-line pt-4 text-[11.5px] leading-5 text-ink-500">Generated {freshness ? new Date(freshness.generated_at).toLocaleString() : "when project data loads"}.</div>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 xl:col-span-8 xl:grid-cols-3">
          {checks.map((issue) => <Card key={issue.label} className="flex items-start gap-3 p-4"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] bg-canvas text-ink-500"><FileWarning size={17} /></span><div className="min-w-0 flex-1"><p className="text-[12.5px] font-semibold text-ink-700">{issue.label}</p><p className="mt-1 text-[24px] font-bold text-ink-900">{number(issue.value)}</p></div></Card>)}
          <Card className="flex items-start gap-3 p-4"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] bg-canvas text-ink-500"><Database size={17} /></span><div><p className="text-[12.5px] font-semibold text-ink-700">Ready documents</p><p className="mt-1 text-[24px] font-bold text-ink-900">{number(metrics?.documents_ready ?? 0)}</p></div></Card>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card className="p-5">
          <CardTitle icon={History} title="Connector sync health" />
          <div className="mt-4 space-y-3">
            {freshness?.connectors.map((connector) => <div key={connector.kind} className="flex items-center gap-3 rounded-[11px] border border-line p-3"><span className="min-w-0 flex-1"><span className="block text-[13px] font-semibold capitalize text-ink-900">{connector.kind}</span><span className="block truncate text-[11px] text-ink-500">Last success: {age(connector.lag_seconds)}</span></span><Badge tone={connector.status === "connected" ? "green" : connector.status === "degraded" ? "red" : "gray"}>{connector.status}</Badge></div>)}
            {!loading && !freshness?.connectors.length && <p className="rounded-[11px] bg-canvas p-4 text-[12px] text-ink-500">No connector sync state is recorded yet.</p>}
          </div>
        </Card>

        <Card className="p-5">
          <CardTitle icon={FileWarning} title="Suggested remediation" tint="bg-amber-50 text-amber-500" />
          <ul className="mt-4 space-y-3">{freshness?.suggestions.map((item) => <li key={item} className="rounded-[11px] bg-canvas px-4 py-3 text-[12.5px] leading-5 text-ink-700">{item}</li>)}</ul>
          <div className="mt-4"><CardLink href="/documents">Open documents</CardLink></div>
        </Card>
      </div>

      <Card className="mt-5 p-5 animate-rise-2">
        <CardTitle icon={FileWarning} title={`Freshness findings (${number(freshness?.total_findings ?? 0)})`} />
        {(freshness?.total_findings ?? 0) > (freshness?.issues.length ?? 0) && (
          <p className="mt-2 text-[11.5px] text-ink-500">
            Showing the 200 highest-priority findings; totals and remediation use the full authorized inventory.
          </p>
        )}
        <div className="mt-4 space-y-3">
          {freshness?.issues.map((issue) => <div key={`${issue.kind}-${issue.source_id}`} className="rounded-[12px] border border-line p-4"><div className="flex flex-wrap items-center gap-2"><Badge tone={issue.severity === "critical" ? "red" : "amber"}>{issue.kind.replaceAll("_", " ")}</Badge><Badge tone="gray">{issue.source_type}</Badge>{issue.age_days != null && <span className="ml-auto text-[11px] text-ink-400">{issue.age_days} days old</span>}</div><div className="mt-2 flex items-start gap-2"><div className="min-w-0 flex-1"><p className="truncate text-[13px] font-semibold text-ink-900">{issue.title}</p><p className="mt-1 text-[11.5px] leading-5 text-ink-500">{issue.suggested_remediation}</p></div>{issue.source_url && <a href={issue.source_url} target="_blank" rel="noreferrer" aria-label={`Open ${issue.title}`} className="text-ink-400 hover:text-brand-600"><ExternalLink size={15} /></a>}</div></div>)}
          {!loading && !freshness?.issues.length && <div className="rounded-[14px] border border-dashed border-line bg-canvas px-5 py-8 text-center"><p className="text-[14px] font-bold text-ink-900">No freshness findings</p><p className="mt-1 text-[12.5px] text-ink-500">The selected project has no stale, failing, or lagging authorized sources.</p></div>}
        </div>
      </Card>
    </div>
  );
}
