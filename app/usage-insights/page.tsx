import { Clock, Search, Compass, Lightbulb, Flame, CalendarDays } from "lucide-react";
import { Card, CardTitle, PageHeader, Badge, Donut, cx } from "@/components/ui";

const peak = [
  [1, 2, 3, 2, 1, 0, 0],
  [2, 4, 5, 4, 3, 1, 0],
  [3, 5, 6, 6, 4, 1, 1],
  [4, 6, 6, 5, 4, 2, 1],
  [3, 5, 5, 4, 3, 1, 0],
  [2, 3, 4, 3, 2, 1, 0],
];
const hours = ["9am", "11am", "1pm", "3pm", "5pm", "7pm"];
const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const heat = ["bg-brand-50", "bg-brand-100", "bg-brand-200", "bg-brand-300", "bg-brand-400", "bg-brand-500", "bg-brand-600"];

const intents = [
  { label: "How-to & procedures", pct: 38, color: "#5b5ceb" },
  { label: "Finding documents", pct: 26, color: "#38bdf8" },
  { label: "Policy questions", pct: 16, color: "#8583f1" },
  { label: "Troubleshooting", pct: 13, color: "#f59e0b" },
  { label: "People & ownership", pct: 7, color: "#cbd5e1" },
];

const gaps = [
  { q: "How to set up local dev for the mobile app?", asks: 14, note: "No confident source found" },
  { q: "What is the on-call compensation policy?", asks: 11, note: "Answers rated unhelpful" },
  { q: "Where are the staging environment credentials?", asks: 9, note: "No confident source found" },
  { q: "How do I request a new SaaS tool?", asks: 7, note: "Conflicting sources" },
];

const champions = [
  { name: "Ananya Rao", team: "Engineering", asks: 142 },
  { name: "Rahul Mehta", team: "Support", asks: 118 },
  { name: "Priya Nair", team: "Product", asks: 97 },
  { name: "Arjun Patel", team: "SRE", asks: 89 },
];

export default function UsageInsightsPage() {
  return (
    <div>
      <PageHeader title="Usage & Insights" subtitle="Where knowledge gets used — and where it's missing." />

      <div className="grid grid-cols-12 gap-5 animate-rise-1">
        <Card className="col-span-5 p-5">
          <CardTitle icon={CalendarDays} title="Peak Usage Hours" />
          <div className="mt-5 flex gap-2.5">
            <div className="flex flex-col justify-between py-0.5 text-[10.5px] font-medium text-ink-400">
              {hours.map((h) => <span key={h}>{h}</span>)}
            </div>
            <div className="flex-1">
              <div className="grid grid-cols-7 gap-1.5">
                {peak.flatMap((row, ri) =>
                  row.map((v, ci) => (
                    <div key={`${ri}-${ci}`} className={cx("aspect-square rounded-[5px]", heat[v])} title={`${days[ci]} ${hours[ri]}`} />
                  ))
                )}
              </div>
              <div className="mt-1.5 grid grid-cols-7 gap-1.5 text-center text-[10.5px] font-medium text-ink-400">
                {days.map((d) => <span key={d}>{d}</span>)}
              </div>
            </div>
          </div>
          <p className="mt-4 flex items-center gap-2 text-[12.5px] text-ink-500">
            <Clock size={13} className="text-brand-400" />
            Busiest window: <strong className="font-semibold text-ink-900">Wed–Thu, 11am–3pm IST</strong>
          </p>
        </Card>

        <Card className="col-span-4 p-5">
          <CardTitle icon={Compass} title="Query Intent Mix" tint="bg-sky-50 text-sky-500" />
          <div className="mt-5 flex items-center gap-5">
            <Donut data={intents.map((i) => ({ value: i.pct, color: i.color }))} size={120} thickness={26} />
            <ul className="flex-1 space-y-2.5">
              {intents.map((i) => (
                <li key={i.label} className="flex items-center gap-2 text-[12.5px]">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: i.color }} />
                  <span className="flex-1 font-medium text-ink-700">{i.label}</span>
                  <span className="font-semibold text-ink-500">{i.pct}%</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <CardTitle icon={Flame} title="Knowledge Champions" tint="bg-amber-50 text-amber-500" />
          <ul className="mt-4 space-y-3.5">
            {champions.map((c, i) => (
              <li key={c.name} className="flex items-center gap-3">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-brand-200 text-[11.5px] font-bold text-brand-700">
                  {c.name.split(" ").map((p) => p[0]).join("")}
                </span>
                <span className="flex-1">
                  <span className="block text-[13px] font-semibold text-ink-900">{c.name}</span>
                  <span className="block text-[11.5px] text-ink-500">{c.team}</span>
                </span>
                <span className="text-[12.5px] font-bold text-ink-700">{c.asks}</span>
                {i === 0 && <Badge tone="amber">Top</Badge>}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card className="mt-5 p-5 animate-rise-2">
        <CardTitle
          icon={Lightbulb}
          title="Knowledge Gaps"
          tint="bg-amber-50 text-amber-500"
          right={<Badge tone="amber">4 unanswered themes</Badge>}
        />
        <p className="mt-1.5 pl-[42px] text-[12.5px] text-ink-500">
          Questions people keep asking that Kimbal can&apos;t answer well yet. Fill these to lift accuracy fastest.
        </p>
        <ul className="mt-4 divide-y divide-line">
          {gaps.map((g) => (
            <li key={g.q} className="flex items-center gap-4 py-3.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-[9px] bg-canvas text-ink-400">
                <Search size={14} />
              </span>
              <div className="flex-1">
                <p className="text-[13.5px] font-semibold text-ink-900">{g.q}</p>
                <p className="text-[12px] text-ink-500">{g.note}</p>
              </div>
              <span className="text-[12.5px] text-ink-500">
                Asked <strong className="font-bold text-ink-900">{g.asks}×</strong> this month
              </span>
              <button className="rounded-[9px] border border-brand-200 bg-brand-50 px-3.5 py-2 text-[12.5px] font-semibold text-brand-600 transition hover:bg-brand-100">
                Assign owner
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
