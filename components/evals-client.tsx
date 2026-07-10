"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ClipboardCheck,
  Gauge,
  Layers3,
  Loader2,
  MessageSquareQuote,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Timer,
} from "lucide-react";
import { Badge, Card, CardTitle, GhostButton, PageHeader, ProgressBar, cx } from "@/components/ui";
import { EvalGateRun, EvalOverview, EvalScore, kimbalApi } from "@/lib/kimbal-api";

const OVERVIEW_CACHE_KEY = "cvum.evals.overview.v2";
const GATE_CACHE_KEY = "cvum.evals.offline-gate.v2";

type CachedValue<T> = { cachedAt: string; value: T };

function readCache<T>(key: string): CachedValue<T> | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as CachedValue<T>) : null;
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

function writeCache<T>(key: string, value: T) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, JSON.stringify({ cachedAt: new Date().toISOString(), value }));
}

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

function verdictTone(verdict: string): "green" | "amber" | "red" | "gray" {
  if (verdict === "healthy") return "green";
  if (verdict === "needs_review") return "amber";
  if (verdict === "failure") return "red";
  return "gray";
}

function label(value: string) {
  return value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatBreakdown(values: Record<string, number> | undefined) {
  if (!values) return "N/A";
  const entries = Object.entries(values);
  if (!entries.length) return "N/A";
  return entries.map(([key, value]) => `${key}: ${number(value)}`).join(" · ");
}

export function EvalsClient() {
  const initialOverview = readCache<EvalOverview>(OVERVIEW_CACHE_KEY);
  const initialGate = readCache<EvalGateRun>(GATE_CACHE_KEY);
  const [overview, setOverview] = useState<EvalOverview | null>(() => initialOverview?.value ?? null);
  const [offlineGate, setOfflineGate] = useState<EvalGateRun | null>(() => initialGate?.value ?? null);
  const [cachedAt, setCachedAt] = useState<string | null>(() => initialOverview?.cachedAt ?? null);
  const [loading, setLoading] = useState(() => !initialOverview);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async (force = false) => {
    setRefreshing(true);
    setError("");
    try {
      if (force) kimbalApi.refreshLiveData();
      await kimbalApi.ensureSession();
      const overviewRequest = kimbalApi.evalsOverview().then((liveOverview) => {
        setOverview(liveOverview);
        setCachedAt(new Date().toISOString());
        writeCache(OVERVIEW_CACHE_KEY, liveOverview);
        setLoading(false);
      });
      const gateRequest = kimbalApi.evalsOfflineGate().then((gate) => {
        setOfflineGate(gate);
        writeCache(GATE_CACHE_KEY, gate);
      });
      const results = await Promise.allSettled([overviewRequest, gateRequest]);
      const failures = results.filter((result) => result.status === "rejected") as PromiseRejectedResult[];
      if (failures.length === results.length) {
        throw failures[0].reason;
      }
      if (results[0].status === "rejected") {
        setError("Showing the saved live benchmark because its background refresh failed.");
      } else if (results[1].status === "rejected") {
        setError("Live overview updated; the offline gate refresh is still unavailable.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load evals");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const savedOverview = readCache<EvalOverview>(OVERVIEW_CACHE_KEY);
      const savedGate = readCache<EvalGateRun>(GATE_CACHE_KEY);
      if (savedOverview) {
        setOverview(savedOverview.value);
        setCachedAt(savedOverview.cachedAt);
        setLoading(false);
      }
      if (savedGate) setOfflineGate(savedGate.value);
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

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
          <GhostButton onClick={() => void refresh(true)} disabled={refreshing}>
            {(loading || refreshing) ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            {refreshing ? "Refreshing" : "Refresh"}
          </GhostButton>
        }
      />

      {error && (
        <Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      {cachedAt && (
        <p className="mb-4 text-right text-[11.5px] font-semibold text-ink-400">
          Showing the latest saved benchmark from {formatDate(cachedAt)}{refreshing ? " while live checks refresh." : "."}
        </p>
      )}

      <div className="grid grid-cols-12 gap-5 animate-rise-1">
        <Card className="col-span-12 p-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle icon={Gauge} title={overview?.benchmark.label ?? "CVUM Benchmark"} tint="bg-brand-50 text-brand-500" />
              <p className="mt-3 max-w-3xl text-[13px] leading-6 text-ink-500">
                {overview?.benchmark.detail ?? "Loading benchmark from stored answer evaluations."}
              </p>
            </div>
            <div className="shrink-0 rounded-[16px] border border-line bg-canvas px-6 py-5 text-center">
              <p className="text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">Benchmark score</p>
              <p className="mt-1 text-[42px] font-black tracking-[-0.03em] text-ink-950">
                {overview?.benchmark.display ?? "N/A"}
              </p>
              <Badge tone={statusTone(overview?.benchmark.status ?? "no_data")}>{overview?.benchmark.status ?? "Loading"}</Badge>
            </div>
          </div>
          <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
            {(overview?.benchmark.components ?? []).map((component) => (
              <div key={component.id} className="rounded-[12px] border border-line bg-white px-3 py-3">
                <div className="flex items-center justify-between gap-3 text-[12px]">
                  <span className="font-bold text-ink-700">{component.label}</span>
                  <span className="font-bold text-ink-900">{component.display}</span>
                </div>
                <ProgressBar value={(component.value ?? 0) * 100} color={progressColor(overview?.benchmark.status ?? "no_data")} />
                <p className="mt-1 text-[11px] font-semibold text-ink-400">Weight {Math.round(component.weight * 100)}%</p>
              </div>
            ))}
            {!overview?.benchmark.components.length && (
              <div className="rounded-[12px] border border-line bg-white px-3 py-3 text-[13px] text-ink-500 md:col-span-3">
                No benchmark components available yet.
              </div>
            )}
          </div>
        </Card>

        <Card className="col-span-12 p-5 lg:col-span-4">
          <CardTitle icon={Gauge} title="Eval Window" tint="bg-sky-50 text-sky-600" />
          <div className="mt-5 grid grid-cols-2 gap-3">
            <MetricTile label="Answers total" value={overview ? number(overview.answers_total) : "N/A"} />
            <MetricTile label="Sample" value={overview ? number(overview.sample_size) : "N/A"} />
            <MetricTile label="P95 latency" value={latency(overview?.latency.p95_ms ?? null)} />
            <MetricTile label="Helpful rate" value={percent(overview?.feedback.helpful_rate ?? null)} />
          </div>
          <p className="mt-4 rounded-[12px] border border-line bg-canvas px-3 py-2.5 text-[12.5px] leading-5 text-ink-500">
            Live rows use persisted answer observations. The offline gate is a deterministic retrieval dry run, not a model comparison.
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

      <Card className="mt-5 p-5 animate-rise-2">
        <CardTitle
          icon={AlertTriangle}
          title="Observed Quality Incidents"
          tint={(overview?.quality.failures ?? 0) > 0 ? "bg-rose-50 text-rose-600" : "bg-emerald-50 text-emerald-600"}
          right={<Badge tone={(overview?.quality.failures ?? 0) > 0 ? "red" : "green"}>{overview?.quality.failures ?? 0} failures</Badge>}
        />
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricTile label="Observed" value={number(overview?.quality.evaluated ?? 0)} />
          <MetricTile label="Healthy" value={number(overview?.quality.healthy ?? 0)} />
          <MetricTile label="Needs review" value={number(overview?.quality.needs_review ?? 0)} />
          <MetricTile label="Failures" value={number(overview?.quality.failures ?? 0)} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(overview?.quality.issue_counts ?? {}).map(([issue, count]) => (
            <Badge key={issue} tone="red">{label(issue)}: {count}</Badge>
          ))}
          {!Object.keys(overview?.quality.issue_counts ?? {}).length && (
            <p className="text-[13px] font-medium text-emerald-700">No persisted quality incidents in the observed answer window.</p>
          )}
        </div>
      </Card>

      <Card className="mt-5 p-5 animate-rise-2">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <CardTitle
              icon={ClipboardCheck}
              title="Offline Release Gate"
              tint={offlineGate == null ? "bg-sky-50 text-sky-600" : offlineGate.passed ? "bg-emerald-50 text-emerald-600" : "bg-rose-50 text-rose-600"}
              right={<Badge tone={offlineGate == null ? "gray" : offlineGate.passed ? "green" : "red"}>{offlineGate == null ? "Refreshing" : offlineGate.passed ? "Passing" : "Failing"}</Badge>}
            />
            <p className="mt-3 max-w-3xl text-[13px] leading-6 text-ink-500">
              {offlineGate
                ? `${offlineGate.cases} golden cases from ${offlineGate.dataset_path}. Failing examples include expected sources, returned sources, answer text, and judge rationale.`
                : "Loading offline golden-set release gate."}
            </p>
          </div>
          <div className="shrink-0 rounded-[14px] border border-line bg-canvas px-5 py-4 text-center">
            <p className="text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">Gate score</p>
            <p className="mt-1 text-[34px] font-black tracking-[-0.03em] text-ink-950">{offlineGate?.display ?? "N/A"}</p>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {(offlineGate?.metrics ?? []).slice(0, 8).map((metric) => (
            <div key={metric.id} className="rounded-[12px] border border-line bg-white px-3 py-3">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[12.5px] font-bold text-ink-800">{metric.label}</p>
                <Badge tone={metric.passed ? "green" : "red"}>{metric.display}</Badge>
              </div>
              <p className="mt-2 text-[11.5px] leading-5 text-ink-400">{metric.detail}</p>
            </div>
          ))}
          {!offlineGate?.metrics.length && (
            <p className="rounded-[12px] border border-line bg-white px-3 py-3 text-[13px] text-ink-500">
              No offline gate metrics available.
            </p>
          )}
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {(offlineGate?.failing_cases ?? []).slice(0, 4).map((item) => (
            <div key={item.id} className="rounded-[14px] border border-rose-100 bg-rose-50/40 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="red">{item.category}</Badge>
                <span className="text-[11.5px] font-bold uppercase tracking-[0.08em] text-rose-500">{item.id}</span>
              </div>
              <p className="mt-2 text-[13px] font-bold text-ink-900">{item.question}</p>
              <p className="mt-2 text-[12.5px] leading-5 text-rose-700">{item.judge_rationale}</p>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11.5px] font-semibold text-ink-500">
                <span className="rounded-[10px] bg-white px-2.5 py-2">Expected: {item.expected_sources.join(", ")}</span>
                <span className="rounded-[10px] bg-white px-2.5 py-2">Returned: {item.returned_sources.join(", ") || "none"}</span>
              </div>
            </div>
          ))}
          {offlineGate?.passed && offlineGate.failing_cases.length > 0 && (
            <p className="rounded-[14px] border border-amber-100 bg-amber-50 px-4 py-4 text-[13px] font-semibold text-amber-700">
              Aggregate release thresholds pass, but {offlineGate.failing_cases.length} individual cases still need review.
            </p>
          )}
          {offlineGate?.passed && offlineGate.failing_cases.length === 0 && (
            <p className="rounded-[14px] border border-emerald-100 bg-emerald-50 px-4 py-4 text-[13px] font-semibold text-emerald-700">
              All golden cases are currently above the configured release thresholds.
            </p>
          )}
        </div>
      </Card>

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

        <Card className="col-span-12 overflow-hidden lg:col-span-7">
          <div className="p-5 pb-0">
            <CardTitle icon={Brain} title="Model Breakdown" tint="bg-brand-50 text-brand-500" />
          </div>
          <div className="overflow-x-auto"><table className="mt-3 min-w-[620px] w-full text-left">
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
          </table></div>
        </Card>
      </div>

      <Card className="mt-5 overflow-hidden animate-rise-3">
        <div className="p-5 pb-0"><CardTitle icon={Layers3} title="Mode Breakdown" tint="bg-sky-50 text-sky-600" /></div>
        <div className="overflow-x-auto">
          <table className="mt-3 min-w-[720px] w-full text-left">
            <thead><tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400"><th className="py-3 pl-5">Source</th><th>Answer mode</th><th className="text-right">Answers</th><th className="text-right">Latency</th><th className="text-right">Grounding</th><th className="pr-5 text-right">Failure rate</th></tr></thead>
            <tbody className="divide-y divide-line">
              {overview?.modes.map((mode) => <tr key={`${mode.source_mode}-${mode.answer_mode}`}><td className="py-3.5 pl-5 text-[13px] font-semibold text-ink-800">{label(mode.source_mode)}</td><td className="text-[13px] font-semibold text-ink-600">{label(mode.answer_mode)}</td><td className="text-right text-[13px] font-semibold">{mode.answers}</td><td className="text-right text-[13px] text-ink-600">{latency(mode.avg_latency_ms)}</td><td className="text-right text-[13px] text-ink-600">{percent(mode.groundedness_score)}</td><td className="pr-5 text-right"><Badge tone={(mode.failure_rate ?? 0) > 0.2 ? "red" : (mode.failure_rate ?? 0) > 0 ? "amber" : "green"}>{percent(mode.failure_rate)}</Badge></td></tr>)}
              {!overview?.modes.length && <tr><td colSpan={6} className="px-5 py-6 text-[13px] text-ink-500">No mode observations yet. New answers record source and answer modes.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

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
                  <Badge tone={verdictTone(answer.verdict)}>{label(answer.verdict)}</Badge>
                  <Badge tone="gray">{label(answer.source_mode)} / {label(answer.answer_mode)}</Badge>
                </div>
                <p className="mt-2 text-[13.5px] font-bold text-ink-900">{answer.question || "Question unavailable in sample"}</p>
                <p className="mt-1.5 text-[13px] leading-6 text-ink-500">{answer.answer_preview}</p>
                <div className="mt-3 flex flex-wrap gap-2 text-[12px] font-semibold">
                  <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-emerald-600">Grounded {percent(answer.groundedness_score)}</span>
                  <span className="rounded-full bg-sky-50 px-2.5 py-1 text-sky-600">Relevance {percent(answer.relevance_score)}</span>
                  <span className="rounded-full bg-canvas px-2.5 py-1 text-ink-500">Latency {latency(answer.latency_ms)}</span>
                  {answer.unsupported_claim_rate != null && <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-700">Unsupported {percent(answer.unsupported_claim_rate)}</span>}
                </div>
                {answer.issues.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{answer.issues.map((issue) => <Badge key={issue} tone="red">{label(issue)}</Badge>)}</div>}
              </div>
            ))}
            {!loading && !overview?.recent_answers.length && (
              <p className="px-5 py-6 text-[13px] text-ink-500">No assistant answers have been evaluated yet.</p>
            )}
          </div>
        </Card>

        <div className="col-span-12 space-y-5 lg:col-span-4">
          <Card className="p-5">
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

          <Card className="p-5">
            <CardTitle
              icon={ClipboardCheck}
              title="Golden Dataset"
              tint="bg-emerald-50 text-emerald-600"
              right={<Badge tone={overview?.golden_dataset.benchmark_ready ? "green" : "gray"}>{overview?.golden_dataset.cases ?? 0} cases</Badge>}
            />
            <div className="mt-4 space-y-3 text-[12.5px] leading-5 text-ink-600">
              <p className="rounded-[12px] border border-line bg-canvas px-3 py-3">
                {overview?.golden_dataset.dataset_path ?? "evals/golden/rag.jsonl"}
              </p>
              <p className="rounded-[12px] border border-line bg-canvas px-3 py-3">
                Categories: {formatBreakdown(overview?.golden_dataset.categories)}
              </p>
              <p className="rounded-[12px] border border-line bg-canvas px-3 py-3">
                Source targets: {formatBreakdown(overview?.golden_dataset.source_types)}
              </p>
            </div>
          </Card>
        </div>
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
