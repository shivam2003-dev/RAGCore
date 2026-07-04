"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  Gauge,
  Loader2,
  MessageSquareQuote,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Timer,
} from "lucide-react";
import { Badge, Card, CardTitle, GhostButton, PageHeader, ProgressBar, cx } from "@/components/ui";
import { EvalOverview, EvalScore, kimbalApi } from "@/lib/kimbal-api";

function number(value: number) {
  return new Intl.NumberFormat().format(value);
}

function percent(value: number | null) {
  return value == null ? "N/A" : `${Math.round(value * 100)}%`;
}

function latency(value: number | null) {
  return value == null ? "N/A" : `${number(value)} ms`;
}

function statusTone(status: string): "green" | "amber" | "red" | "gray" {
  if (status === "good") return "green";
  if (status === "watch") return "amber";
  if (status === "needs_attention") return "red";
  return "gray";
}

function progressColor(status: string) {
  if (status === "good") return "bg-emerald-400";
  if (status === "watch") return "bg-amber-400";
  if (status === "needs_attention") return "bg-rose-400";
  return "bg-ink-300";
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function EvalsClient() {
  const [overview, setOverview] = useState<EvalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refresh(force = false) {
    setLoading(true);
    setError("");
    try {
      if (force) kimbalApi.refreshLiveData();
      await kimbalApi.ensureSession();
      setOverview(await kimbalApi.evalsOverview());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load evals");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const scores = overview?.scores ?? [];
  const primaryScores = ["groundedness", "answer_relevance", "citation_coverage", "retrieval_confidence"];
  const scoreById = new Map(scores.map((score) => [score.id, score]));
  const sampleLabel = overview ? `${number(overview.sample_size)} recent answers` : "Loading sample";

  return (
    <div>
      <PageHeader
        title="Evals"
        subtitle="Live answer quality and performance checks from persisted RAG responses."
        actions={
          <GhostButton onClick={() => void refresh(true)} disabled={loading}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Refresh
          </GhostButton>
        }
      />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      <div className="grid grid-cols-12 gap-5 animate-rise-1">
        <Card className="col-span-12 p-5 lg:col-span-4">
          <CardTitle icon={Gauge} title="Eval Window" tint="bg-sky-50 text-sky-600" />
          <div className="mt-5 grid grid-cols-2 gap-3">
            <MetricTile label="Answers total" value={overview ? number(overview.answers_total) : "N/A"} />
            <MetricTile label="Sample" value={overview ? number(overview.sample_size) : "N/A"} />
            <MetricTile label="P95 latency" value={latency(overview?.latency.p95_ms ?? null)} />
            <MetricTile label="Helpful rate" value={percent(overview?.feedback.helpful_rate ?? null)} />
          </div>
          <p className="mt-4 rounded-[12px] border border-line bg-canvas px-3 py-2.5 text-[12.5px] leading-5 text-ink-500">
            These are live heuristic evals over stored conversations. Add a golden dataset before using them as release gates.
          </p>
        </Card>

        <Card className="col-span-12 p-5 lg:col-span-8">
          <CardTitle icon={ShieldCheck} title="RAG Quality" tint="bg-emerald-50 text-emerald-500" right={<Badge tone="blue">{sampleLabel}</Badge>} />
          <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
            {primaryScores.map((id) => {
              const score = scoreById.get(id);
              return score ? <ScoreCard key={score.id} score={score} /> : <ScoreSkeleton key={id} />;
            })}
          </div>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-12 p-5 lg:col-span-5">
          <CardTitle icon={Timer} title="Latency" tint="bg-amber-50 text-amber-500" />
          <div className="mt-5 grid grid-cols-3 gap-3">
            <MetricTile label="Average" value={latency(overview?.latency.avg_ms ?? null)} />
            <MetricTile label="P50" value={latency(overview?.latency.p50_ms ?? null)} />
            <MetricTile label="P95" value={latency(overview?.latency.p95_ms ?? null)} />
          </div>
          <div className="mt-5 space-y-3">
            {scores.filter((score) => !primaryScores.includes(score.id)).map((score) => (
              <CompactScore key={score.id} score={score} />
            ))}
            {!loading && !scores.length && (
              <p className="rounded-[12px] bg-canvas px-3 py-3 text-[13px] text-ink-500">
                Ask at least one question to populate answer evals.
              </p>
            )}
          </div>
        </Card>

        <Card className="col-span-12 lg:col-span-7">
          <div className="p-5 pb-0">
            <CardTitle icon={Brain} title="Model Breakdown" tint="bg-brand-50 text-brand-500" />
          </div>
          <table className="mt-3 w-full text-left">
            <thead>
              <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
                <th className="py-3 pl-5 font-bold">Model</th>
                <th className="w-24 text-right font-bold">Answers</th>
                <th className="w-32 text-right font-bold">Latency</th>
                <th className="w-32 pr-5 text-right font-bold">Grounding</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {overview?.models.map((model) => (
                <tr key={model.model} className="transition hover:bg-brand-50/30">
                  <td className="py-3.5 pl-5 text-[13.5px] font-semibold text-ink-800">{model.model}</td>
                  <td className="text-right text-[13px] font-semibold text-ink-900">{number(model.answers)}</td>
                  <td className="text-right text-[13px] font-semibold text-ink-600">{latency(model.avg_latency_ms)}</td>
                  <td className="pr-5 text-right text-[13px] font-semibold text-ink-600">{percent(model.groundedness_score)}</td>
                </tr>
              ))}
              {!loading && !overview?.models.length && (
                <tr>
                  <td className="px-5 py-6 text-[13px] text-ink-500" colSpan={4}>
                    No model usage data yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-3">
        <Card className="col-span-12 lg:col-span-8">
          <div className="p-5 pb-0">
            <CardTitle icon={MessageSquareQuote} title="Recent Evaluated Answers" />
          </div>
          <div className="mt-3 divide-y divide-line">
            {overview?.recent_answers.map((answer) => (
              <div key={answer.message_id} className="px-5 py-4">
                <div className="flex flex-wrap items-center gap-2 text-[11.5px] font-semibold text-ink-400">
                  <span>{formatDate(answer.created_at)}</span>
                  <span>-</span>
                  <span>{answer.model ?? "unknown model"}</span>
                  <Badge tone={answer.citations ? "green" : "gray"}>{answer.citations} citations</Badge>
                </div>
                <p className="mt-2 text-[13.5px] font-bold text-ink-900">{answer.question || "Question unavailable in sample"}</p>
                <p className="mt-1.5 text-[13px] leading-6 text-ink-500">{answer.answer_preview}</p>
                <div className="mt-3 flex flex-wrap gap-2 text-[12px] font-semibold">
                  <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-600">Grounded {percent(answer.groundedness_score)}</span>
                  <span className="rounded-full bg-sky-50 px-2.5 py-1 text-sky-600">Relevance {percent(answer.relevance_score)}</span>
                  <span className="rounded-full bg-canvas px-2.5 py-1 text-ink-500">Latency {latency(answer.latency_ms)}</span>
                </div>
              </div>
            ))}
            {!loading && !overview?.recent_answers.length && (
              <p className="px-5 py-6 text-[13px] text-ink-500">No assistant answers have been evaluated yet.</p>
            )}
          </div>
        </Card>

        <Card className="col-span-12 p-5 lg:col-span-4">
          <CardTitle icon={Sparkles} title="Methodology" tint="bg-sky-50 text-sky-600" />
          <div className="mt-4 space-y-3">
            {(overview?.methodology ?? [
              "Loading current methodology from the backend.",
            ]).map((item) => (
              <div key={item} className="rounded-[12px] border border-line bg-canvas px-3 py-3">
                <p className="text-[12.5px] leading-5 text-ink-600">{item}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[12px] border border-line bg-canvas px-3 py-3">
      <p className="text-[11.5px] font-semibold text-ink-400">{label}</p>
      <p className="mt-1 text-[20px] font-bold tracking-[-0.02em] text-ink-900">{value}</p>
    </div>
  );
}

function ScoreCard({ score }: { score: EvalScore }) {
  return (
    <div className="rounded-[14px] border border-line bg-canvas p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[13px] font-bold text-ink-900">{score.label}</p>
          <p className="mt-1 text-[12px] leading-5 text-ink-500">{score.detail}</p>
        </div>
        <Badge tone={statusTone(score.status)}>{score.display}</Badge>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <span className={cx("flex h-8 w-8 items-center justify-center rounded-[10px]", score.status === "needs_attention" ? "bg-rose-50 text-rose-500" : "bg-white text-ink-500")}>
          {score.status === "good" ? (
            <CheckCircle2 size={16} />
          ) : score.status === "needs_attention" ? (
            <AlertTriangle size={16} />
          ) : (
            <ShieldCheck size={16} />
          )}
        </span>
        <ProgressBar value={(score.value ?? 0) * 100} color={progressColor(score.status)} />
      </div>
    </div>
  );
}

function CompactScore({ score }: { score: EvalScore }) {
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-[12.5px]">
        <span className="font-semibold text-ink-700">{score.label}</span>
        <span className="font-bold text-ink-900">{score.display}</span>
      </div>
      <ProgressBar value={(score.value ?? 0) * 100} color={progressColor(score.status)} />
      <p className="mt-1 text-[11.5px] leading-5 text-ink-400">{score.detail}</p>
    </div>
  );
}

function ScoreSkeleton() {
  return (
    <div className="rounded-[14px] border border-line bg-canvas p-4">
      <div className="h-4 w-32 rounded-full bg-line" />
      <div className="mt-3 h-3 w-full rounded-full bg-line" />
      <div className="mt-4 h-2 w-full rounded-full bg-line" />
    </div>
  );
}
