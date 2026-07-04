import { Bookmark, ExternalLink, Clock } from "lucide-react";
import { Card, PageHeader, GhostButton, cx } from "@/components/ui";
import {
  ConfluenceIcon,
  GitHubIcon,
  NotionIcon,
  GoogleDriveIcon,
  PdfIcon,
  SlackIcon,
} from "@/components/brand-icons";

const groups = [
  {
    label: "DevOps & Infrastructure",
    items: [
      { title: "Kubernetes Deployment Guide", source: "Confluence", icon: ConfluenceIcon, added: "2 days ago" },
      { title: "service-template repository", source: "GitHub", icon: GitHubIcon, added: "5 days ago" },
      { title: "Production Readiness Checklist", source: "Confluence", icon: ConfluenceIcon, added: "1 week ago" },
    ],
  },
  {
    label: "Processes & SOPs",
    items: [
      { title: "Incident Response Runbook", source: "PDF", icon: PdfIcon, added: "1 week ago" },
      { title: "Release Management SOP", source: "Notion", icon: NotionIcon, added: "2 weeks ago" },
      { title: "#devops-support pinned answers", source: "Slack", icon: SlackIcon, added: "3 weeks ago" },
    ],
  },
  {
    label: "Planning & Docs",
    items: [
      { title: "Q3 Product Roadmap", source: "Notion", icon: NotionIcon, added: "3 weeks ago" },
      { title: "Architecture Decision Records", source: "Google Drive", icon: GoogleDriveIcon, added: "1 month ago" },
    ],
  },
];

export default function BookmarksPage() {
  return (
    <div>
      <PageHeader
        title="Bookmarks"
        subtitle="Documents and threads you pinned for quick access."
        actions={<GhostButton><Bookmark size={15} /> New collection</GhostButton>}
      />

      <div className="space-y-7">
        {groups.map((g, gi) => (
          <section key={g.label} className={cx("animate-rise", gi === 1 && "animate-rise-1", gi === 2 && "animate-rise-2")}>
            <div className="mb-3 flex items-center gap-3">
              <h2 className="text-[13px] font-bold uppercase tracking-[0.1em] text-ink-400">{g.label}</h2>
              <span className="h-px flex-1 bg-line" />
              <span className="text-[12px] font-semibold text-ink-400">{g.items.length} items</span>
            </div>
            <div className="grid grid-cols-3 gap-4">
              {g.items.map((b) => (
                <Card key={b.title} className="group flex items-start gap-3.5 p-4 transition hover:shadow-[var(--shadow-pop)]">
                  <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[11px] border border-line bg-white">
                    <b.icon size={19} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13.5px] font-bold text-ink-900 transition group-hover:text-brand-600">
                      {b.title}
                    </p>
                    <p className="mt-0.5 text-[12px] text-ink-500">{b.source}</p>
                    <p className="mt-2 inline-flex items-center gap-1.5 text-[11.5px] text-ink-400">
                      <Clock size={12} /> Added {b.added}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col gap-1">
                    <button className="flex h-7 w-7 items-center justify-center rounded-[7px] text-brand-500" aria-label="Bookmarked">
                      <Bookmark size={14} fill="currentColor" />
                    </button>
                    <button className="flex h-7 w-7 items-center justify-center rounded-[7px] text-ink-400 opacity-0 transition hover:text-brand-500 group-hover:opacity-100" aria-label="Open">
                      <ExternalLink size={14} />
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
