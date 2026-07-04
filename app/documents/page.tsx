import { Search, Filter, ArrowUpDown, Eye, MoreHorizontal, Upload } from "lucide-react";
import { Card, PageHeader, PrimaryButton, GhostButton, Badge, cx } from "@/components/ui";
import {
  JiraIcon,
  ConfluenceIcon,
  SlackIcon,
  GitHubIcon,
  GoogleDriveIcon,
  NotionIcon,
  PdfIcon,
  SharePointIcon,
} from "@/components/brand-icons";

const docs = [
  { title: "Kubernetes Deployment Guide", source: "Confluence", icon: ConfluenceIcon, area: "DevOps", owner: "Platform Team", updated: "2 days ago", freshness: "Fresh" },
  { title: "Incident Response Runbook", source: "PDF", icon: PdfIcon, area: "Security", owner: "SecOps", updated: "4 days ago", freshness: "Fresh" },
  { title: "Q3 Product Roadmap", source: "Notion", icon: NotionIcon, area: "Product", owner: "Product Team", updated: "1 week ago", freshness: "Fresh" },
  { title: "Payment Service — API Reference", source: "GitHub", icon: GitHubIcon, area: "Engineering", owner: "Payments Squad", updated: "1 week ago", freshness: "Fresh" },
  { title: "New Joiner Onboarding SOP", source: "SharePoint", icon: SharePointIcon, area: "HR & Policies", owner: "People Ops", updated: "3 weeks ago", freshness: "Aging" },
  { title: "Postmortem — 2026-06-12 API Outage", source: "Confluence", icon: ConfluenceIcon, area: "DevOps", owner: "SRE", updated: "3 weeks ago", freshness: "Fresh" },
  { title: "Design Review Checklist", source: "Google Drive", icon: GoogleDriveIcon, area: "Engineering", owner: "Design Systems", updated: "1 month ago", freshness: "Aging" },
  { title: "#dev-updates — Weekly Digest", source: "Slack", icon: SlackIcon, area: "Engineering", owner: "Eng Leads", updated: "1 month ago", freshness: "Aging" },
  { title: "KIM-2841 — Migrate billing to v2", source: "Jira", icon: JiraIcon, area: "Product", owner: "Billing Squad", updated: "2 months ago", freshness: "Stale" },
  { title: "Legacy VPN Setup Guide", source: "Confluence", icon: ConfluenceIcon, area: "IT", owner: "IT Support", updated: "5 months ago", freshness: "Stale" },
];

const freshTone = { Fresh: "green", Aging: "amber", Stale: "red" } as const;

export default function DocumentsPage() {
  return (
    <div>
      <PageHeader
        title="Documents"
        subtitle="54,102 indexed documents across 10 connected sources."
        actions={
          <PrimaryButton>
            <Upload size={15} /> Upload Documents
          </PrimaryButton>
        }
      />

      <Card className="animate-rise-1">
        <div className="flex items-center gap-3 border-b border-line p-4">
          <label className="flex h-10 flex-1 cursor-text items-center gap-2.5 rounded-[10px] border border-line bg-canvas px-3.5 transition focus-within:border-brand-300 focus-within:bg-white focus-within:ring-4 focus-within:ring-brand-50">
            <Search size={15} className="text-ink-400" />
            <input
              placeholder="Search documents by title, content or owner..."
              className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-ink-400"
            />
          </label>
          <GhostButton><Filter size={14} /> Filters</GhostButton>
          <GhostButton><ArrowUpDown size={14} /> Sort: Last updated</GhostButton>
        </div>

        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Document</th>
              <th className="font-bold">Source</th>
              <th className="font-bold">Knowledge Area</th>
              <th className="font-bold">Owner</th>
              <th className="font-bold">Last Updated</th>
              <th className="font-bold">Freshness</th>
              <th className="pr-5 text-right font-bold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {docs.map((d) => (
              <tr key={d.title} className="group transition hover:bg-brand-50/30">
                <td className="py-3.5 pl-5">
                  <span className="text-[13.5px] font-semibold text-ink-900 transition group-hover:text-brand-600">
                    {d.title}
                  </span>
                </td>
                <td>
                  <span className="inline-flex items-center gap-2 text-[13px] font-medium text-ink-700">
                    <d.icon size={16} /> {d.source}
                  </span>
                </td>
                <td className="text-[13px] text-ink-700">{d.area}</td>
                <td className="text-[13px] text-ink-700">{d.owner}</td>
                <td className="text-[13px] text-ink-500">{d.updated}</td>
                <td>
                  <Badge tone={freshTone[d.freshness as keyof typeof freshTone]}>{d.freshness}</Badge>
                </td>
                <td className="pr-5">
                  <div className="flex items-center justify-end gap-1">
                    <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500" aria-label={`Preview ${d.title}`}>
                      <Eye size={15} />
                    </button>
                    <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500" aria-label="More actions">
                      <MoreHorizontal size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex items-center justify-between border-t border-line px-5 py-3.5 text-[12.5px] text-ink-500">
          <span>Showing 1–10 of 54,102 documents</span>
          <div className="flex gap-1.5">
            {["1", "2", "3", "…", "5,411"].map((p, i) => (
              <button
                key={p}
                className={cx(
                  "flex h-8 min-w-8 items-center justify-center rounded-[8px] px-2 text-[12.5px] font-semibold transition",
                  i === 0 ? "bg-brand-500 text-white" : "text-ink-500 hover:bg-canvas"
                )}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
