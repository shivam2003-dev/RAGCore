"use client";

import { CalendarDays, Compass, Lightbulb, MessageCircleQuestion, Search } from "lucide-react";
import { Badge, Card, CardTitle, Donut, PageHeader } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

export function UsageInsightsClient() {
  const { metrics, loading, error } = useLiveMetrics();
  const sourceTotal = metrics?.sources.reduce((sum, source) => sum + source.documents, 0) ?? 0;
  const sourceMix = metrics?.sources.map((source, index) => ({
    label: source.name,
    pct: sourceTotal ? Math.round((source.documents / sourceTotal) * 100) : 0,
    color: ["#5b5ceb", "#38bdf8", "#10b981", "#f59e0b", "#8583f1", "#cbd5e1"][index % 6],
  })) ?? [];

  return (
    <div>
      <PageHeader title="Usage & Insights" subtitle="Live usage signals; unavailable analytics are labeled clearly." />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <div className="grid grid-cols-12 gap-5 animate-rise-1">
        <Card className="col-span-5 p-5">
          <CardTitle icon={CalendarDays} title="Peak Usage Hours" />
          <div className="mt-5 rounded-[14px] border border-dashed border-line bg-canvas px-5 py-10 text-center">
            <p className="text-[14px] font-bold text-ink-900">Hourly usage is not collected yet</p>
            <p className="mt-1 text-[12.5px] text-ink-500">
              Add timestamp snapshot aggregation before showing a heatmap.
            </p>
          </div>
        </Card>

        <Card className="col-span-4 p-5">
          <CardTitle icon={Compass} title="Indexed Source Mix" tint="bg-sky-50 text-sky-500" />
          <div className="mt-5 flex items-center gap-5">
            {sourceMix.length ? <Donut data={sourceMix.map((item) => ({ value: Math.max(1, item.pct), color: item.color }))} size={120} thickness={26} /> : <div className="h-[120px] w-[120px] rounded-full bg-canvas" />}
            <ul className="flex-1 space-y-2.5">
              {sourceMix.map((item) => (
                <li key={item.label} className="flex items-center gap-2 text-[12.5px]">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: item.color }} />
                  <span className="flex-1 font-medium text-ink-700">{item.label}</span>
                  <span className="font-semibold text-ink-500">{item.pct}%</span>
                </li>
              ))}
              {!loading && !sourceMix.length && (
                <li className="text-[12.5px] text-ink-500">No indexed sources yet.</li>
              )}
            </ul>
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <CardTitle icon={MessageCircleQuestion} title="Usage Totals" tint="bg-amber-50 text-amber-500" />
          <div className="mt-4 space-y-3">
            <div className="rounded-[12px] bg-canvas px-4 py-3">
              <p className="text-[12px] text-ink-500">Questions asked</p>
              <p className="mt-1 text-[24px] font-bold text-ink-900">{number(metrics?.questions_asked ?? 0)}</p>
            </div>
            <div className="rounded-[12px] bg-canvas px-4 py-3">
              <p className="text-[12px] text-ink-500">Conversations</p>
              <p className="mt-1 text-[24px] font-bold text-ink-900">{number(metrics?.conversations ?? 0)}</p>
            </div>
          </div>
        </Card>
      </div>

      <Card className="mt-5 p-5 animate-rise-2">
        <CardTitle
          icon={Lightbulb}
          title="Question Signals"
          tint="bg-amber-50 text-amber-500"
          right={<Badge tone={metrics?.top_questions.length ? "green" : "gray"}>{metrics?.top_questions.length ?? 0} live themes</Badge>}
        />
        <p className="mt-1.5 pl-[42px] text-[12.5px] text-ink-500">
          These are grouped by exact question text from stored conversations.
        </p>
        <ul className="mt-4 divide-y divide-line">
          {metrics?.top_questions.map((item) => (
            <li key={item.question} className="flex items-center gap-4 py-3.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-canvas text-ink-400">
                <Search size={14} />
              </span>
              <div className="flex-1">
                <p className="text-[13.5px] font-semibold text-ink-900">{item.question}</p>
                <p className="text-[12px] text-ink-500">
                  Last asked {new Date(item.last_asked_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
                </p>
              </div>
              <span className="text-[12.5px] text-ink-500">
                Asked <strong className="font-bold text-ink-900">{item.count}</strong> times
              </span>
            </li>
          ))}
          {!loading && !metrics?.top_questions.length && (
            <li className="py-6 text-[13px] text-ink-500">No questions have been stored yet.</li>
          )}
        </ul>
      </Card>
    </div>
  );
}
