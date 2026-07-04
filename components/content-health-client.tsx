"use client";

import { FileWarning, HeartPulse, Loader2, RefreshCw } from "lucide-react";
import { Badge, Card, CardLink, CardTitle, GhostButton, PageHeader, ProgressBar } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

export function ContentHealthClient() {
  const { metrics, loading, error, refresh } = useLiveMetrics();
  const total = metrics?.documents_total ?? 0;
  const score = total ? Math.round(((metrics?.documents_ready ?? 0) / total) * 100) : null;
  const checks = [
    { label: "Ready documents", value: metrics?.documents_ready ?? 0, pct: total ? ((metrics?.documents_ready ?? 0) / total) * 100 : 0 },
    { label: "Processing documents", value: metrics?.documents_processing ?? 0, pct: total ? ((metrics?.documents_processing ?? 0) / total) * 100 : 0 },
    { label: "Failed documents", value: metrics?.documents_failed ?? 0, pct: total ? ((metrics?.documents_failed ?? 0) / total) * 100 : 0 },
  ];

  return (
    <div>
      <PageHeader
        title="Content Health"
        subtitle="Live document readiness from the retrieval index."
        actions={<GhostButton onClick={() => void refresh()}><RefreshCw size={15} /> Refresh</GhostButton>}
      />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <div className="grid grid-cols-12 gap-5 animate-rise-1">
        <Card className="col-span-4 p-6">
          <CardTitle icon={HeartPulse} title="Readiness Score" tint="bg-rose-50 text-rose-400" />
          <div className="mt-6 flex items-end gap-3">
            <p className="text-[52px] font-bold leading-none tracking-[-0.03em] text-ink-900">
              {loading ? <Loader2 size={34} className="animate-spin text-brand-500" /> : score ?? "N/A"}
            </p>
            <div className="pb-1.5">
              <Badge tone={score == null ? "gray" : score >= 90 ? "green" : score >= 70 ? "amber" : "red"}>
                {score == null ? "No docs" : "Live"}
              </Badge>
              <p className="mt-1 text-[12px] text-ink-500">{number(total)} documents indexed</p>
            </div>
          </div>
          <div className="mt-5"><ProgressBar value={score ?? 0} /></div>
          <div className="mt-5 space-y-3 border-t border-line pt-4">
            {checks.map((check) => (
              <div key={check.label}>
                <div className="mb-1 flex justify-between text-[12.5px]">
                  <span className="font-medium text-ink-700">{check.label}</span>
                  <span className="font-semibold text-ink-900">{number(check.value)}</span>
                </div>
                <ProgressBar value={check.pct} color={check.label.startsWith("Failed") ? "bg-rose-400" : "bg-brand-400"} />
              </div>
            ))}
          </div>
        </Card>

        <div className="col-span-8 grid grid-cols-2 gap-5">
          {[
            { label: "Knowledge bases", value: metrics?.knowledge_bases ?? 0, desc: "Org-scoped KB records" },
            { label: "Active chunks", value: metrics?.chunks_active ?? 0, desc: "Retrievable active vector/FTS chunks" },
            { label: "Failed documents", value: metrics?.documents_failed ?? 0, desc: "Documents that need reindex or source cleanup" },
            { label: "Processing documents", value: metrics?.documents_processing ?? 0, desc: "Documents still moving through ingestion" },
          ].map((issue) => (
            <Card key={issue.label} className="flex items-start gap-4 p-5">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-canvas text-ink-500">
                <FileWarning size={18} />
              </span>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <p className="text-[14px] font-bold text-ink-900">{issue.label}</p>
                  <span className="text-[22px] font-bold text-ink-900">{number(issue.value)}</span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-ink-500">{issue.desc}</p>
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Card className="mt-5 p-5 animate-rise-2">
        <CardTitle
          icon={FileWarning}
          title="Remediation"
          tint="bg-amber-50 text-amber-500"
          right={<span className="text-[12px] font-semibold text-ink-400">Derived from live document status</span>}
        />
        <div className="mt-4 rounded-[14px] border border-dashed border-line bg-canvas px-5 py-8">
          <p className="text-[14px] font-bold text-ink-900">
            {metrics?.documents_failed ? `${metrics.documents_failed} documents failed ingestion` : "No failed documents"}
          </p>
          <p className="mt-1 text-[12.5px] text-ink-500">
            Use Documents to inspect failed rows and reindex after correcting the source.
          </p>
          <div className="mt-4">
            <CardLink href="/documents">Open documents</CardLink>
          </div>
        </div>
      </Card>
    </div>
  );
}
