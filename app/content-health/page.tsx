import { HeartPulse, Link2Off, History, FileWarning, CopyX, Wand2, ArrowRight } from "lucide-react";
import { Card, CardTitle, PageHeader, PrimaryButton, Badge, ProgressBar } from "@/components/ui";
import { ConfluenceIcon, NotionIcon, GoogleDriveIcon, SharePointIcon } from "@/components/brand-icons";

const issues = [
  { icon: History, label: "Outdated Documents", count: 23, desc: "Not updated in 6+ months but still cited in answers", tone: "amber" as const },
  { icon: Link2Off, label: "Broken Links", count: 12, desc: "Links pointing to moved or deleted pages", tone: "red" as const },
  { icon: CopyX, label: "Duplicate Content", count: 9, desc: "Near-identical pages competing in retrieval", tone: "amber" as const },
  { icon: FileWarning, label: "Low Quality Content", count: 8, desc: "Thin pages that produce weak answers", tone: "gray" as const },
];

const queue = [
  { title: "Legacy VPN Setup Guide", source: "Confluence", icon: ConfluenceIcon, issue: "Outdated — last updated 11 months ago", severity: "High", owner: "IT Support" },
  { title: "Deployment Checklist (old)", source: "Notion", icon: NotionIcon, issue: "Duplicate of Production Readiness Checklist", severity: "High", owner: "Platform Team" },
  { title: "2024 Travel Policy", source: "SharePoint", icon: SharePointIcon, issue: "Superseded — new policy exists", severity: "Medium", owner: "People Ops" },
  { title: "API Style Guide draft", source: "Google Drive", icon: GoogleDriveIcon, issue: "3 broken internal links", severity: "Medium", owner: "API Guild" },
  { title: "Oncall FAQ", source: "Confluence", icon: ConfluenceIcon, issue: "Thin content — 4 questions unanswered", severity: "Low", owner: "SRE" },
];

const sevTone = { High: "red", Medium: "amber", Low: "gray" } as const;

export default function ContentHealthPage() {
  return (
    <div>
      <PageHeader
        title="Content Health"
        subtitle="Keep the knowledge base accurate, current and answer-ready."
        actions={<PrimaryButton><Wand2 size={15} /> Run health scan</PrimaryButton>}
      />

      <div className="grid grid-cols-12 gap-5 animate-rise-1">
        <Card className="col-span-4 p-6">
          <CardTitle icon={HeartPulse} title="Overall Health Score" tint="bg-rose-50 text-rose-400" />
          <div className="mt-6 flex items-end gap-3">
            <p className="text-[52px] font-bold leading-none tracking-[-0.03em] text-ink-900">85</p>
            <div className="pb-1.5">
              <Badge tone="green">Good</Badge>
              <p className="mt-1 text-[12px] text-ink-500">+3 since last scan</p>
            </div>
          </div>
          <div className="mt-5"><ProgressBar value={85} /></div>
          <div className="mt-5 space-y-3 border-t border-line pt-4">
            {[
              { label: "Freshness", v: 81 },
              { label: "Coverage", v: 88 },
              { label: "Citation quality", v: 90 },
              { label: "Deduplication", v: 79 },
            ].map((m) => (
              <div key={m.label}>
                <div className="mb-1 flex justify-between text-[12.5px]">
                  <span className="font-medium text-ink-700">{m.label}</span>
                  <span className="font-semibold text-ink-900">{m.v}</span>
                </div>
                <ProgressBar value={m.v} color="bg-brand-400" />
              </div>
            ))}
          </div>
        </Card>

        <div className="col-span-8 grid grid-cols-2 gap-5">
          {issues.map((i) => (
            <Card key={i.label} className="flex items-start gap-4 p-5">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-canvas text-ink-500">
                <i.icon size={18} />
              </span>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <p className="text-[14px] font-bold text-ink-900">{i.label}</p>
                  <span className="text-[22px] font-bold text-ink-900">{i.count}</span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-ink-500">{i.desc}</p>
                <button className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-brand-500 transition hover:text-brand-600">
                  Review items <ArrowRight size={13} />
                </button>
              </div>
            </Card>
          ))}
        </div>
      </div>

      <Card className="mt-5 animate-rise-2">
        <div className="p-5 pb-0">
          <CardTitle
            icon={FileWarning}
            title="Remediation Queue"
            tint="bg-amber-50 text-amber-500"
            right={<span className="text-[12px] font-semibold text-ink-400">Sorted by answer impact</span>}
          />
        </div>
        <table className="mt-3 w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Document</th>
              <th className="font-bold">Issue</th>
              <th className="font-bold">Severity</th>
              <th className="font-bold">Owner</th>
              <th className="pr-5 text-right font-bold">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {queue.map((q) => (
              <tr key={q.title} className="transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5">
                  <span className="inline-flex items-center gap-2.5">
                    <q.icon size={17} />
                    <span className="text-[13.5px] font-semibold text-ink-900">{q.title}</span>
                  </span>
                </td>
                <td className="text-[13px] text-ink-700">{q.issue}</td>
                <td><Badge tone={sevTone[q.severity as keyof typeof sevTone]}>{q.severity}</Badge></td>
                <td className="text-[13px] text-ink-700">{q.owner}</td>
                <td className="pr-5 text-right">
                  <button className="rounded-[8px] border border-line px-3 py-1.5 text-[12px] font-semibold text-ink-700 transition hover:border-brand-200 hover:text-brand-600">
                    Notify owner
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
