"use client";

import { ChartColumn, Download, Loader2, MessageCircleQuestion, Target, Timer, Users } from "lucide-react";
import { Card, CardTitle, GhostButton, PageHeader, ProgressBar } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

export function AnalyticsClient() {
  const { metrics, loading, error } = useLiveMetrics();
  const helpfulRate = metrics?.feedback.helpful_rate != null
    ? Math.round(metrics.feedback.helpful_rate * 100)
    : null;
  const stats = [
    { title: "Questions Asked", value: number(metrics?.questions_asked ?? 0), icon: MessageCircleQuestion },
    { title: "Active Users", value: number(metrics?.active_users ?? 0), icon: Users },
    { title: "Avg. Response Time", value: metrics?.avg_latency_ms ? `${metrics.avg_latency_ms} ms` : "N/A", icon: Timer },
    { title: "Helpful Rate", value: helpfulRate == null ? "N/A" : `${helpfulRate}%`, icon: Target },
  ];

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Live usage data from the CVUM backend."
        actions={<GhostButton disabled><Download size={15} /> Export unavailable</GhostButton>}
      />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <div className="grid grid-cols-4 gap-5 animate-rise-1">
        {stats.map((stat) => (
          <Card key={stat.title} className="flex min-h-[154px] flex-col p-5">
            <CardTitle icon={stat.icon} title={stat.title} />
            <p className="mt-4 text-[28px] font-bold tracking-[-0.02em] text-ink-900">
              {loading ? <Loader2 size={22} className="animate-spin text-brand-500" /> : stat.value}
            </p>
            <p className="mt-auto pt-3 text-[12.5px] text-ink-500">Current database total</p>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-7 p-5">
          <CardTitle
            icon={ChartColumn}
            title="Historical Trends"
            right={<span className="text-[12px] font-semibold text-ink-400">No synthetic history</span>}
          />
          <div className="mt-6 rounded-[14px] border border-dashed border-line bg-canvas px-5 py-10 text-center">
            <p className="text-[14px] font-bold text-ink-900">Time-series analytics are not collected yet</p>
            <p className="mt-1 text-[12.5px] text-ink-500">
              Add a daily metrics snapshot table before showing week-over-week charts.
            </p>
          </div>
        </Card>

        <Card className="col-span-5 p-5">
          <CardTitle icon={Target} title="Answer Quality" tint="bg-emerald-50 text-emerald-500" />
          <div className="mt-5 space-y-4">
            <div>
              <div className="mb-1.5 flex justify-between text-[13px]">
                <span className="font-semibold text-ink-900">Helpful</span>
                <span className="font-semibold text-ink-500">{number(metrics?.feedback.helpful ?? 0)}</span>
              </div>
              <ProgressBar value={helpfulRate ?? 0} color="bg-emerald-400" />
            </div>
            <div>
              <div className="mb-1.5 flex justify-between text-[13px]">
                <span className="font-semibold text-ink-900">Not helpful</span>
                <span className="font-semibold text-ink-500">{number(metrics?.feedback.not_helpful ?? 0)}</span>
              </div>
              <ProgressBar value={helpfulRate == null ? 0 : 100 - helpfulRate} color="bg-rose-400" />
            </div>
          </div>
        </Card>
      </div>

      <Card className="mt-5 animate-rise-3">
        <div className="p-5 pb-0">
          <CardTitle icon={MessageCircleQuestion} title="Top Questions" />
        </div>
        <table className="mt-3 w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Question</th>
              <th className="w-32 pr-5 text-right font-bold">Times asked</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {metrics?.top_questions.map((question) => (
              <tr key={question.question} className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5 text-[13.5px] font-medium text-ink-700">{question.question}</td>
                <td className="pr-5 text-right text-[13px] font-semibold text-ink-900">{question.count}</td>
              </tr>
            ))}
            {!loading && !metrics?.top_questions.length && (
              <tr>
                <td className="px-5 py-6 text-[13px] text-ink-500" colSpan={2}>
                  No questions have been asked yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
