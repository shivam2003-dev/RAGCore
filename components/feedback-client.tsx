"use client";

import { Filter, MessagesSquare, Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { Badge, Card, CardTitle, GhostButton, PageHeader, ProgressBar } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

export function FeedbackClient() {
  const { metrics, loading, error } = useLiveMetrics();
  const total = metrics?.feedback.total ?? 0;
  const helpfulRate = metrics?.feedback.helpful_rate != null
    ? Math.round(metrics.feedback.helpful_rate * 100)
    : null;
  const notHelpfulRate = helpfulRate == null ? null : 100 - helpfulRate;

  return (
    <div>
      <PageHeader
        title="Feedback"
        subtitle="Live answer ratings captured by the backend."
        actions={<GhostButton disabled><Filter size={15} /> Filters unavailable</GhostButton>}
      />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <div className="grid grid-cols-4 gap-5 animate-rise-1">
        {[
          { label: "Helpful ratings", value: number(metrics?.feedback.helpful ?? 0) },
          { label: "Not helpful", value: number(metrics?.feedback.not_helpful ?? 0) },
          { label: "Feedback total", value: number(total) },
          { label: "Helpful rate", value: helpfulRate == null ? "N/A" : `${helpfulRate}%` },
        ].map((stat) => (
          <Card key={stat.label} className="p-5">
            <p className="text-[12.5px] font-semibold text-ink-500">{stat.label}</p>
            <p className="mt-2 text-[26px] font-bold tracking-[-0.02em] text-ink-900">
              {loading ? "..." : stat.value}
            </p>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-4 p-5">
          <CardTitle icon={Star} title="Rating Distribution" tint="bg-amber-50 text-amber-500" />
          <ul className="mt-5 space-y-4">
            <li>
              <div className="mb-1.5 flex justify-between text-[13px]">
                <span className="inline-flex items-center gap-2 font-semibold text-ink-900">
                  <ThumbsUp size={14} className="text-emerald-500" />
                  Helpful
                </span>
                <span className="font-semibold text-ink-500">{helpfulRate == null ? "N/A" : `${helpfulRate}%`}</span>
              </div>
              <ProgressBar value={helpfulRate ?? 0} color="bg-emerald-400" />
            </li>
            <li>
              <div className="mb-1.5 flex justify-between text-[13px]">
                <span className="inline-flex items-center gap-2 font-semibold text-ink-900">
                  <ThumbsDown size={14} className="text-rose-500" />
                  Not helpful
                </span>
                <span className="font-semibold text-ink-500">{notHelpfulRate == null ? "N/A" : `${notHelpfulRate}%`}</span>
              </div>
              <ProgressBar value={notHelpfulRate ?? 0} color="bg-rose-400" />
            </li>
          </ul>
          <p className="mt-5 rounded-[12px] bg-canvas px-4 py-3 text-[12.5px] leading-relaxed text-ink-500">
            Detailed comment analytics need a feedback review endpoint. This card intentionally shows only ratings currently stored and exposed by the API.
          </p>
        </Card>

        <Card className="col-span-8">
          <div className="p-5 pb-0">
            <CardTitle icon={MessagesSquare} title="Recent Feedback" />
          </div>
          <div className="p-5">
            <div className="rounded-[14px] border border-dashed border-line bg-canvas px-5 py-10 text-center">
              <Badge tone={total ? "green" : "gray"}>{total ? "Ratings available" : "No ratings yet"}</Badge>
              <p className="mt-3 text-[14px] font-bold text-ink-900">
                Feedback details are not exposed as a read endpoint yet
              </p>
              <p className="mt-1 text-[12.5px] text-ink-500">
                The Ask buttons persist ratings now; add a reviewed feedback-list API before showing user/comment rows.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
