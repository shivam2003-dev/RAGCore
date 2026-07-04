import { ThumbsUp, ThumbsDown, MessagesSquare, Star, Filter } from "lucide-react";
import { Card, CardTitle, PageHeader, GhostButton, Badge, Delta, ProgressBar, cx } from "@/components/ui";

const stats = [
  { label: "Helpful ratings", value: "1,208", delta: "12.4%", up: true },
  { label: "Not helpful", value: "116", delta: "3.1% fewer", up: true },
  { label: "Feedback rate", value: "31%", delta: "5.2%", up: true },
  { label: "Avg. satisfaction", value: "4.5/5", delta: "0.2", up: true },
];

const distribution = [
  { stars: 5, pct: 58 },
  { stars: 4, pct: 27 },
  { stars: 3, pct: 9 },
  { stars: 2, pct: 4 },
  { stars: 1, pct: 2 },
];

const items = [
  { user: "Ananya Rao", team: "Engineering", verdict: "Helpful", q: "How do I deploy a new service on Kubernetes?", comment: "Step-by-step answer with the exact repo links. Saved me an hour.", time: "12 min ago" },
  { user: "Rahul Mehta", team: "Support", verdict: "Not helpful", q: "What is the refund escalation path for enterprise plans?", comment: "Answer cited the 2024 policy. The escalation matrix changed in May.", time: "1 hr ago" },
  { user: "Priya Nair", team: "Product", verdict: "Helpful", q: "Where is the Q3 roadmap?", comment: "Direct link with the right access level. Perfect.", time: "3 hrs ago" },
  { user: "Dev Sharma", team: "SRE", verdict: "Not helpful", q: "How to rotate the staging DB credentials?", comment: "Steps referenced a vault path that no longer exists.", time: "5 hrs ago" },
  { user: "Meera Iyer", team: "People Ops", verdict: "Helpful", q: "How to onboard a new team member?", comment: "Checklist was complete and current.", time: "Yesterday" },
];

export default function FeedbackPage() {
  return (
    <div>
      <PageHeader
        title="Feedback"
        subtitle="What users say about Kimbal's answers — and what to fix next."
        actions={<GhostButton><Filter size={15} /> Filter: All teams</GhostButton>}
      />

      <div className="grid grid-cols-4 gap-5 animate-rise-1">
        {stats.map((s) => (
          <Card key={s.label} className="p-5">
            <p className="text-[12.5px] font-semibold text-ink-500">{s.label}</p>
            <p className="mt-2 text-[26px] font-bold tracking-[-0.02em] text-ink-900">{s.value}</p>
            <div className="mt-1"><Delta value={`${s.delta} vs last month`} up={s.up} /></div>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-4 p-5">
          <CardTitle icon={Star} title="Rating Distribution" tint="bg-amber-50 text-amber-500" />
          <ul className="mt-5 space-y-3">
            {distribution.map((d) => (
              <li key={d.stars} className="flex items-center gap-3">
                <span className="flex w-10 items-center gap-1 text-[12.5px] font-semibold text-ink-700">
                  {d.stars} <Star size={11} className="fill-amber-400 text-amber-400" />
                </span>
                <div className="flex-1"><ProgressBar value={d.pct} color="bg-amber-400" /></div>
                <span className="w-9 text-right text-[12.5px] font-semibold text-ink-500">{d.pct}%</span>
              </li>
            ))}
          </ul>
          <p className="mt-5 rounded-[12px] bg-canvas px-4 py-3 text-[12.5px] leading-relaxed text-ink-500">
            Most negative feedback traces to <strong className="font-semibold text-ink-900">outdated policy documents</strong>. Fixing the 23 stale docs in Content Health should lift satisfaction fastest.
          </p>
        </Card>

        <Card className="col-span-8">
          <div className="p-5 pb-0">
            <CardTitle icon={MessagesSquare} title="Recent Feedback" />
          </div>
          <ul className="mt-2 divide-y divide-line">
            {items.map((f) => (
              <li key={f.q + f.user} className="flex gap-4 px-5 py-4">
                <span
                  className={cx(
                    "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                    f.verdict === "Helpful" ? "bg-emerald-50 text-emerald-500" : "bg-rose-50 text-rose-500"
                  )}
                >
                  {f.verdict === "Helpful" ? <ThumbsUp size={14} /> : <ThumbsDown size={14} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2.5">
                    <p className="text-[13px] font-bold text-ink-900">{f.user}</p>
                    <span className="text-[11.5px] text-ink-400">{f.team}</span>
                    <Badge tone={f.verdict === "Helpful" ? "green" : "red"}>{f.verdict}</Badge>
                    <span className="ml-auto text-[11.5px] text-ink-400">{f.time}</span>
                  </div>
                  <p className="mt-1 text-[12.5px] font-medium text-brand-600">“{f.q}”</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-ink-700">{f.comment}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
