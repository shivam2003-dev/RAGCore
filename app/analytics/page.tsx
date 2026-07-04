import { MessageCircleQuestion, Users, Timer, Target, TrendingUp, ChartColumn, Download } from "lucide-react";
import { Card, CardTitle, PageHeader, GhostButton, Delta, Sparkline, Bars, ProgressBar } from "@/components/ui";

const stats = [
  { title: "Questions Asked", value: "4,287", delta: "18.3%", up: true, icon: MessageCircleQuestion, points: [12, 18, 15, 24, 20, 30, 26, 34, 30, 40, 36, 46], stroke: "#5b5ceb" },
  { title: "Active Users", value: "612", delta: "9.1%", up: true, icon: Users, points: [30, 34, 32, 38, 36, 42, 40, 44, 42, 48, 46, 52], stroke: "#38bdf8" },
  { title: "Avg. Response Time", value: "1.8s", delta: "0.4s faster", up: true, icon: Timer, points: [40, 38, 39, 36, 37, 34, 35, 32, 31, 30, 29, 27], stroke: "#10b981" },
  { title: "Answer Accuracy", value: "92%", delta: "4.7%", up: true, icon: Target, points: [78, 80, 79, 83, 82, 85, 84, 88, 87, 90, 89, 92], stroke: "#8583f1" },
];

const topQuestions = [
  { q: "How do I deploy a new service on Kubernetes?", asks: 96, accuracy: 96 },
  { q: "What is our code review process?", asks: 81, accuracy: 94 },
  { q: "How to access production logs?", asks: 72, accuracy: 91 },
  { q: "What are the incident response steps?", asks: 64, accuracy: 95 },
  { q: "How to onboard a new team member?", asks: 57, accuracy: 88 },
  { q: "Where is the Q3 roadmap?", asks: 49, accuracy: 90 },
];

const teams = [
  { name: "Engineering", pct: 42 },
  { name: "Product", pct: 21 },
  { name: "Support", pct: 15 },
  { name: "People Ops", pct: 12 },
  { name: "Finance", pct: 10 },
];

export default function AnalyticsPage() {
  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="How your organization asks, answers and learns — last 30 days."
        actions={<GhostButton><Download size={15} /> Export report</GhostButton>}
      />

      <div className="grid grid-cols-4 gap-5 animate-rise-1">
        {stats.map((s, i) => (
          <Card key={s.title} className="flex flex-col p-5">
            <CardTitle icon={s.icon} title={s.title} />
            <p className="mt-4 text-[28px] font-bold tracking-[-0.02em] text-ink-900">{s.value}</p>
            <div className="mt-1"><Delta value={`${s.delta} vs last month`} up={s.up} /></div>
            <div className="mt-auto pt-3">
              <Sparkline id={`an-${i}`} points={s.points} stroke={s.stroke} />
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-7 p-5">
          <CardTitle
            icon={ChartColumn}
            title="Questions per Week"
            right={<span className="text-[12px] font-semibold text-ink-400">Last 12 weeks</span>}
          />
          <div className="mt-6 px-1">
            <Bars values={[220, 260, 240, 310, 290, 340, 320, 380, 350, 420, 470, 430]} height={180} />
            <div className="mt-2 flex justify-between text-[11px] font-medium text-ink-400">
              <span>W14</span><span>W16</span><span>W18</span><span>W20</span><span>W22</span><span>W24</span>
            </div>
          </div>
        </Card>

        <Card className="col-span-5 p-5">
          <CardTitle icon={TrendingUp} title="Usage by Team" tint="bg-sky-50 text-sky-500" />
          <ul className="mt-5 space-y-4">
            {teams.map((t) => (
              <li key={t.name}>
                <div className="mb-1.5 flex justify-between text-[13px]">
                  <span className="font-semibold text-ink-900">{t.name}</span>
                  <span className="font-semibold text-ink-500">{t.pct}%</span>
                </div>
                <ProgressBar value={t.pct * 2} color="bg-brand-400" />
              </li>
            ))}
          </ul>
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
              <th className="w-32 font-bold">Times asked</th>
              <th className="w-56 pr-5 font-bold">Answer accuracy</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {topQuestions.map((q) => (
              <tr key={q.q} className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5 text-[13.5px] font-medium text-ink-700">{q.q}</td>
                <td className="text-[13px] font-semibold text-ink-900">{q.asks}</td>
                <td className="pr-5">
                  <div className="flex items-center gap-3">
                    <div className="flex-1"><ProgressBar value={q.accuracy} color="bg-emerald-400" /></div>
                    <span className="w-9 text-right text-[12.5px] font-semibold text-ink-700">{q.accuracy}%</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
