"use client";

import {
  Activity,
  CircleCheck,
  Database,
  FileText,
  HelpCircle,
  HeartHandshake,
  Loader2,
  MessageCircleQuestion,
  Plug,
  Sparkles,
  Target,
} from "lucide-react";
import { Badge, Card, CardLink, CardTitle, Donut, ProgressBar } from "@/components/ui";
import { HomeAsk } from "@/components/home-ask";
import { useLiveMetrics } from "@/components/use-live-metrics";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

function timeAgo(value: string) {
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.floor(hours / 24)} day ago`;
}

export function HomeClient() {
  const { metrics, loading, error } = useLiveMetrics();
  const readyRate = metrics?.documents_total
    ? Math.round((metrics.documents_ready / metrics.documents_total) * 100)
    : null;
  const feedbackRate = metrics?.feedback.helpful_rate != null
    ? Math.round(metrics.feedback.helpful_rate * 100)
    : null;
  const sourceTotal = metrics?.sources.reduce((sum, source) => sum + source.documents, 0) ?? 0;
  const donutData = metrics?.sources.length
    ? metrics.sources.map((source, index) => ({
        value: sourceTotal ? Math.max(1, Math.round((source.documents / sourceTotal) * 100)) : 1,
        color: ["#5b5ceb", "#38bdf8", "#10b981", "#f59e0b", "#8583f1", "#cbd5e1"][index % 6],
      }))
    : [];

  return (
    <div className="space-y-6">
      <section className="animate-rise">
        <h1 className="text-[34px] font-bold tracking-[-0.025em] text-ink-900">
          Kimbal Knowledge Hub{" "}
          <Sparkles size={22} className="inline -translate-y-1 text-brand-400" />
        </h1>
        <p className="mt-1.5 text-[15.5px] text-ink-500">
          Unified knowledge. Smarter answers. Better decisions.
        </p>
      </section>

      <HomeAsk />

      {error && (
        <Card className="border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <section className="grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-3 p-5">
          <CardTitle icon={Plug} title="Indexed Sources" tint="bg-brand-50 text-brand-500" />
          <p className="mt-3 text-[26px] font-bold text-ink-900">
            {loading ? <Loader2 size={22} className="animate-spin text-brand-500" /> : number(metrics?.sources.length ?? 0)}
          </p>
          <p className="text-[12px] text-ink-500">Source types with indexed documents</p>
          <ul className="mt-3 space-y-2">
            {metrics?.sources.slice(0, 5).map((source) => (
              <li key={`${source.name}-${source.source_type}`} className="flex items-center gap-2.5">
                <Database size={16} className="text-brand-500" />
                <span className="flex-1 text-[13px] font-medium text-ink-700">{source.name}</span>
                <span className="rounded-md bg-canvas px-1.5 py-0.5 text-[11.5px] font-semibold text-ink-500">
                  {number(source.documents)}
                </span>
              </li>
            ))}
            {!loading && !metrics?.sources.length && (
              <li className="rounded-[10px] bg-canvas px-3 py-2 text-[12.5px] text-ink-500">
                No documents indexed yet.
              </li>
            )}
          </ul>
          <div className="mt-3.5">
            <CardLink href="/knowledge-sources">View sources</CardLink>
          </div>
        </Card>

        <Card className="col-span-2 flex flex-col p-5">
          <CardTitle icon={FileText} title="Documents" tint="bg-sky-50 text-sky-500" />
          <p className="mt-4 text-[30px] font-bold tracking-[-0.02em] text-ink-900">
            {number(metrics?.documents_total ?? 0)}
          </p>
          <p className="text-[12.5px] text-ink-500">{number(metrics?.chunks_active ?? 0)} active chunks</p>
          <div className="mt-auto pt-4">
            <ProgressBar value={readyRate ?? 0} />
            <p className="mt-2 text-[11.5px] font-semibold text-ink-500">
              {readyRate == null ? "No readiness data" : `${readyRate}% ready`}
            </p>
          </div>
        </Card>

        <Card className="col-span-2 flex flex-col p-5">
          <CardTitle icon={MessageCircleQuestion} title="Questions" tint="bg-brand-50 text-brand-500" />
          <p className="mt-4 text-[30px] font-bold tracking-[-0.02em] text-ink-900">
            {number(metrics?.questions_asked ?? 0)}
          </p>
          <p className="text-[12.5px] text-ink-500">{number(metrics?.assistant_answers ?? 0)} answers persisted</p>
          <div className="mt-auto pt-4 text-[12px] font-semibold text-ink-500">
            {metrics?.avg_latency_ms ? `${metrics.avg_latency_ms} ms avg answer latency` : "No latency samples yet"}
          </div>
        </Card>

        <Card className="col-span-2 flex flex-col p-5">
          <CardTitle icon={Target} title="Feedback" tint="bg-emerald-50 text-emerald-500" />
          <p className="mt-4 text-[30px] font-bold tracking-[-0.02em] text-ink-900">
            {feedbackRate == null ? "N/A" : `${feedbackRate}%`}
          </p>
          <p className="text-[12.5px] text-ink-500">
            {number(metrics?.feedback.total ?? 0)} recorded ratings
          </p>
          <div className="mt-auto pt-4">
            <Badge tone={feedbackRate == null ? "gray" : feedbackRate >= 80 ? "green" : "amber"}>
              {feedbackRate == null ? "No ratings" : "Live"}
            </Badge>
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <CardTitle icon={Activity} title="Recent Activity" tint="bg-brand-50 text-brand-500" />
          <ul className="mt-3.5 space-y-3.5">
            {metrics?.recent_activity.slice(0, 5).map((activity) => (
              <li key={`${activity.action}-${activity.created_at}`} className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-[9px] bg-canvas text-ink-500">
                  <Activity size={14} strokeWidth={2} />
                </span>
                <span className="flex-1 text-[13px] font-medium text-ink-700">
                  {activity.detail || activity.action}
                </span>
                <span className="whitespace-nowrap text-[11.5px] text-ink-400">{timeAgo(activity.created_at)}</span>
              </li>
            ))}
            {!loading && !metrics?.recent_activity.length && (
              <li className="rounded-[10px] bg-canvas px-3 py-2 text-[12.5px] text-ink-500">
                No audit activity yet.
              </li>
            )}
          </ul>
        </Card>
      </section>

      <section className="grid grid-cols-12 gap-5 animate-rise-3">
        <Card className="col-span-5 p-5">
          <CardTitle icon={HelpCircle} title="Top Questions" tint="bg-brand-50 text-brand-500" />
          <ul className="mt-2 divide-y divide-line">
            {metrics?.top_questions.map((item) => (
              <li key={item.question} className="flex items-center justify-between gap-4 py-3">
                <span className="text-left text-[13.5px] font-medium text-ink-700">{item.question}</span>
                <span className="rounded-md bg-canvas px-2 py-0.5 text-[12px] font-semibold text-ink-500">
                  {item.count}
                </span>
              </li>
            ))}
            {!loading && !metrics?.top_questions.length && (
              <li className="py-3 text-[13px] text-ink-500">No questions have been asked yet.</li>
            )}
          </ul>
          <div className="mt-3">
            <CardLink href="/analytics">View analytics</CardLink>
          </div>
        </Card>

        <Card className="col-span-4 p-5">
          <CardTitle icon={Database} title="Source Mix" tint="bg-sky-50 text-sky-500" />
          <div className="mt-5 flex items-center gap-6">
            {donutData.length ? <Donut data={donutData} /> : <div className="h-[128px] w-[128px] rounded-full bg-canvas" />}
            <ul className="flex-1 space-y-2.5">
              {metrics?.sources.slice(0, 6).map((source) => (
                <li key={source.name} className="flex items-center gap-2.5 text-[12.5px]">
                  <span className="h-2.5 w-2.5 rounded-full bg-brand-400" />
                  <span className="flex-1 font-medium text-ink-700">{source.name}</span>
                  <span className="font-semibold text-ink-500">{number(source.documents)}</span>
                </li>
              ))}
              {!loading && !metrics?.sources.length && (
                <li className="text-[12.5px] text-ink-500">No indexed source mix yet.</li>
              )}
            </ul>
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <CardTitle icon={HeartHandshake} title="Knowledge Health" tint="bg-rose-50 text-rose-400" />
          <p className="mt-4 text-[12.5px] text-ink-500">Readiness score</p>
          <div className="mt-1 flex items-center justify-between">
            <p className="text-[30px] font-bold text-ink-900">
              {readyRate == null ? "N/A" : readyRate} <span className="text-[14px] font-medium text-ink-400">/100</span>
            </p>
            <Badge tone={readyRate == null ? "gray" : readyRate >= 90 ? "green" : readyRate >= 70 ? "amber" : "red"}>
              {readyRate == null ? "No docs" : "Live"}
            </Badge>
          </div>
          <div className="mt-2.5">
            <ProgressBar value={readyRate ?? 0} />
          </div>
          <ul className="mt-4 space-y-3">
            {[
              ["Ready documents", metrics?.documents_ready ?? 0],
              ["Processing documents", metrics?.documents_processing ?? 0],
              ["Failed documents", metrics?.documents_failed ?? 0],
            ].map(([label, value]) => (
              <li key={label} className="flex items-center gap-2.5 text-[13px]">
                <CircleCheck size={15} className="text-emerald-500" />
                <span className="flex-1 font-medium text-ink-700">{label}</span>
                <span className="font-semibold text-ink-900">{value}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <CardLink href="/content-health">Review health</CardLink>
          </div>
        </Card>
      </section>
    </div>
  );
}
