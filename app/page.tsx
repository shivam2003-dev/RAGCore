import {
  Sparkles,
  Send,
  Plug,
  FileText,
  MessageCircleQuestion,
  Target,
  Activity,
  HelpCircle,
  ChartPie,
  HeartHandshake,
  RefreshCw,
  FolderGit2,
  Hash,
  FilePlus2,
  BookOpen,
  CircleCheck,
} from "lucide-react";
import {
  Card,
  CardTitle,
  CardLink,
  Delta,
  Sparkline,
  Donut,
  ProgressBar,
  Badge,
} from "@/components/ui";
import {
  JiraIcon,
  ConfluenceIcon,
  SlackIcon,
  TeamsIcon,
  GoogleDriveIcon,
} from "@/components/brand-icons";

const sources = [
  { name: "Jira", count: "12,430", icon: JiraIcon },
  { name: "Confluence", count: "8,245", icon: ConfluenceIcon },
  { name: "Slack", count: "18,732", icon: SlackIcon },
  { name: "Microsoft Teams", count: "9,103", icon: TeamsIcon },
  { name: "Google Drive", count: "6,512", icon: GoogleDriveIcon },
];

const activity = [
  { icon: RefreshCw, text: "Document synced from Confluence", time: "2 min ago" },
  { icon: FolderGit2, text: "New Jira project indexed", time: "15 min ago" },
  { icon: Hash, text: "Slack channel #dev-updates synced", time: "1 hr ago" },
  { icon: FilePlus2, text: "108 new documents indexed", time: "2 hrs ago" },
  { icon: BookOpen, text: "Knowledge base updated", time: "3 hrs ago" },
];

const popular = [
  { q: "How do I deploy a new service on Kubernetes?", n: 23 },
  { q: "What is our code review process?", n: 18 },
  { q: "How to access production logs?", n: 15 },
  { q: "What are the incident response steps?", n: 12 },
  { q: "How to onboard a new team member?", n: 10 },
];

const knowledgeAreas = [
  { label: "DevOps & Infrastructure", pct: 28, color: "#5b5ceb" },
  { label: "Engineering Practices", pct: 24, color: "#38bdf8" },
  { label: "Product & Roadmaps", pct: 18, color: "#8583f1" },
  { label: "HR & Policies", pct: 15, color: "#f59e0b" },
  { label: "Security", pct: 10, color: "#10b981" },
  { label: "Others", pct: 5, color: "#cbd5e1" },
];

const health = [
  { label: "Broken Links", n: 12, tone: "text-emerald-500" },
  { label: "Outdated Documents", n: 23, tone: "text-amber-500" },
  { label: "Low Quality Content", n: 8, tone: "text-emerald-500" },
];

export default function Home() {
  return (
    <div className="space-y-6">
      {/* hero */}
      <section className="relative overflow-hidden animate-rise">
        <div className="pointer-events-none absolute -right-24 -top-40 h-[420px] w-[520px] rounded-full bg-gradient-to-br from-brand-100/80 via-sky-100/60 to-transparent blur-3xl" />
        <h1 className="text-[34px] font-bold tracking-[-0.025em] text-ink-900">
          Kimbal Knowledge Hub{" "}
          <Sparkles size={22} className="inline -translate-y-1 text-brand-400" />
        </h1>
        <p className="mt-1.5 text-[15.5px] text-ink-500">
          Unified knowledge. Smarter answers. Better decisions.
        </p>
      </section>

      {/* ask box */}
      <Card className="relative overflow-hidden p-6 animate-rise-1">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-50/40 via-transparent to-sky-50/40" />
        <div className="relative">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-brand-50 text-brand-500">
              <Sparkles size={17} />
            </span>
            <div>
              <p className="text-[15px] font-semibold text-ink-900">
                Ask Kimbal <span className="font-normal text-ink-500">(Powered by RAG)</span>
              </p>
              <p className="text-[12.5px] text-ink-500">Ask anything across your company knowledge</p>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-2 rounded-[14px] border border-line bg-white py-1.5 pl-5 pr-1.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50">
            <input
              placeholder="Ask a question... (e.g., How to deploy a service on Kubernetes?)"
              className="h-10 min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-400"
            />
            <button
              aria-label="Ask"
              className="flex h-10 w-10 items-center justify-center rounded-[11px] bg-brand-500 text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.6)] transition hover:bg-brand-600"
            >
              <Send size={16} />
            </button>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            {[
              "How to onboard a new engineer?",
              "Where is our CI/CD documentation?",
              "What is our incident response process?",
            ].map((s) => (
              <button
                key={s}
                className="rounded-full border border-line bg-white px-3.5 py-1.5 text-[12.5px] font-medium text-ink-700 transition hover:border-brand-200 hover:text-brand-600"
              >
                {s}
              </button>
            ))}
            <CardLink href="/ask">View all suggestions</CardLink>
          </div>
        </div>
      </Card>

      {/* stat row */}
      <section className="grid grid-cols-12 gap-5 animate-rise-2">
        <Card className="col-span-3 p-5">
          <CardTitle icon={Plug} title="Connected Sources" tint="bg-brand-50 text-brand-500" />
          <p className="mt-3 text-[26px] font-bold text-ink-900">8</p>
          <p className="text-[12px] text-ink-500">All systems connected</p>
          <ul className="mt-3 space-y-2">
            {sources.map((s) => (
              <li key={s.name} className="flex items-center gap-2.5">
                <s.icon size={16} />
                <span className="flex-1 text-[13px] font-medium text-ink-700">{s.name}</span>
                <span className="rounded-md bg-canvas px-1.5 py-0.5 text-[11.5px] font-semibold text-ink-500">
                  {s.count}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3.5">
            <CardLink href="/knowledge-sources">View all sources</CardLink>
          </div>
        </Card>

        <Card className="col-span-2 flex flex-col p-5">
          <CardTitle icon={FileText} title="Total Documents" tint="bg-sky-50 text-sky-500" />
          <p className="mt-4 text-[30px] font-bold tracking-[-0.02em] text-ink-900">54,102</p>
          <p className="text-[12.5px] text-ink-500">Across all sources</p>
          <div className="mt-2"><Delta value="12.5% vs last month" /></div>
          <div className="mt-auto pt-3">
            <Sparkline id="docs" points={[24, 30, 26, 38, 32, 44, 40, 52, 46, 58, 54, 66]} />
          </div>
        </Card>

        <Card className="col-span-2 flex flex-col p-5">
          <CardTitle icon={MessageCircleQuestion} title="Questions Answered" tint="bg-brand-50 text-brand-500" />
          <p className="mt-4 text-[30px] font-bold tracking-[-0.02em] text-ink-900">1,429</p>
          <p className="text-[12.5px] text-ink-500">This month</p>
          <div className="mt-2"><Delta value="18.3% vs last month" /></div>
          <div className="mt-auto pt-3">
            <Sparkline id="qa" points={[10, 18, 14, 24, 20, 30, 26, 36, 30, 42, 38, 48]} stroke="#38bdf8" />
          </div>
        </Card>

        <Card className="col-span-2 flex flex-col p-5">
          <CardTitle icon={Target} title="Answer Accuracy" tint="bg-emerald-50 text-emerald-500" />
          <p className="mt-4 text-[30px] font-bold tracking-[-0.02em] text-ink-900">92%</p>
          <p className="text-[12.5px] text-ink-500">This month</p>
          <div className="mt-2"><Delta value="4.7% vs last month" /></div>
          <div className="mt-auto pt-3">
            <Sparkline id="acc" points={[70, 78, 74, 82, 78, 86, 80, 88, 84, 90, 88, 92]} stroke="#10b981" />
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <CardTitle icon={Activity} title="Recent Activity" tint="bg-brand-50 text-brand-500" />
          <ul className="mt-3.5 space-y-3.5">
            {activity.map((a) => (
              <li key={a.text} className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-[9px] bg-canvas text-ink-500">
                  <a.icon size={14} strokeWidth={2} />
                </span>
                <span className="flex-1 text-[13px] font-medium text-ink-700">{a.text}</span>
                <span className="whitespace-nowrap text-[11.5px] text-ink-400">{a.time}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <CardLink href="/analytics">View all activity</CardLink>
          </div>
        </Card>
      </section>

      {/* bottom row */}
      <section className="grid grid-cols-12 gap-5 animate-rise-3">
        <Card className="col-span-5 p-5">
          <CardTitle icon={HelpCircle} title="Popular Questions" tint="bg-brand-50 text-brand-500" />
          <ul className="mt-2 divide-y divide-line">
            {popular.map((p) => (
              <li key={p.q} className="flex items-center justify-between gap-4 py-3">
                <button className="text-left text-[13.5px] font-medium text-ink-700 transition hover:text-brand-600">
                  {p.q}
                </button>
                <span className="rounded-md bg-canvas px-2 py-0.5 text-[12px] font-semibold text-ink-500">{p.n}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3">
            <CardLink href="/analytics">View all questions</CardLink>
          </div>
        </Card>

        <Card className="col-span-4 p-5">
          <CardTitle icon={ChartPie} title="Top Knowledge Areas" tint="bg-sky-50 text-sky-500" />
          <div className="mt-5 flex items-center gap-6">
            <Donut data={knowledgeAreas.map((k) => ({ value: k.pct, color: k.color }))} />
            <ul className="flex-1 space-y-2.5">
              {knowledgeAreas.map((k) => (
                <li key={k.label} className="flex items-center gap-2.5 text-[12.5px]">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.color }} />
                  <span className="flex-1 font-medium text-ink-700">{k.label}</span>
                  <span className="font-semibold text-ink-500">{k.pct}%</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="mt-5">
            <CardLink href="/analytics">View full analytics</CardLink>
          </div>
        </Card>

        <Card className="col-span-3 p-5">
          <CardTitle icon={HeartHandshake} title="Knowledge Health" tint="bg-rose-50 text-rose-400" />
          <p className="mt-4 text-[12.5px] text-ink-500">Overall Health Score</p>
          <div className="mt-1 flex items-center justify-between">
            <p className="text-[30px] font-bold text-ink-900">
              85 <span className="text-[14px] font-medium text-ink-400">/100</span>
            </p>
            <Badge tone="green">Good</Badge>
          </div>
          <div className="mt-2.5">
            <ProgressBar value={85} />
          </div>
          <ul className="mt-4 space-y-3">
            {health.map((h) => (
              <li key={h.label} className="flex items-center gap-2.5 text-[13px]">
                <CircleCheck size={15} className={h.tone} />
                <span className="flex-1 font-medium text-ink-700">{h.label}</span>
                <span className="font-semibold text-ink-900">{h.n}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4">
            <CardLink href="/content-health">Improve knowledge health</CardLink>
          </div>
        </Card>
      </section>
    </div>
  );
}
