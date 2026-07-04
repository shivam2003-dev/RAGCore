import { Plus, RefreshCw, FileText, Clock } from "lucide-react";
import { Card, PageHeader, PrimaryButton, Badge, CardLink } from "@/components/ui";
import {
  JiraIcon,
  ConfluenceIcon,
  SlackIcon,
  TeamsIcon,
  GitHubIcon,
  GitLabIcon,
  SharePointIcon,
  GoogleDriveIcon,
  NotionIcon,
  PdfIcon,
} from "@/components/brand-icons";

const sources = [
  { name: "Jira", desc: "Projects, issues, sprints and comments", docs: "12,430", sync: "2 min ago", status: "Synced", icon: JiraIcon },
  { name: "Confluence", desc: "Spaces, pages and attachments", docs: "8,245", sync: "5 min ago", status: "Synced", icon: ConfluenceIcon },
  { name: "Slack", desc: "Channels, threads and shared files", docs: "18,732", sync: "1 hr ago", status: "Synced", icon: SlackIcon },
  { name: "Microsoft Teams", desc: "Teams, channels and meeting notes", docs: "9,103", sync: "1 hr ago", status: "Synced", icon: TeamsIcon },
  { name: "GitHub", desc: "Repos, READMEs, wikis and PRs", docs: "3,204", sync: "3 hrs ago", status: "Synced", icon: GitHubIcon },
  { name: "GitLab", desc: "Repos, snippets and wikis", docs: "1,187", sync: "3 hrs ago", status: "Syncing", icon: GitLabIcon },
  { name: "SharePoint", desc: "Sites, libraries and documents", docs: "4,410", sync: "6 hrs ago", status: "Synced", icon: SharePointIcon },
  { name: "Google Drive", desc: "Docs, sheets, slides and folders", docs: "6,512", sync: "20 min ago", status: "Synced", icon: GoogleDriveIcon },
  { name: "Notion", desc: "Pages, databases and wikis", docs: "2,876", sync: "1 day ago", status: "Needs attention", icon: NotionIcon },
  { name: "PDFs & Internal Docs", desc: "SOPs, runbooks and incident reports", docs: "1,915", sync: "2 days ago", status: "Synced", icon: PdfIcon },
];

const tone = { Synced: "green", Syncing: "blue", "Needs attention": "amber" } as const;

export default function KnowledgeSourcesPage() {
  return (
    <div>
      <PageHeader
        title="Knowledge Sources"
        subtitle="All connected systems feeding the Kimbal knowledge graph."
        actions={
          <PrimaryButton>
            <Plus size={15} /> Connect Source
          </PrimaryButton>
        }
      />

      <div className="grid grid-cols-3 gap-5 animate-rise-1">
        {sources.map((s) => (
          <Card key={s.name} className="group p-5 transition hover:shadow-[var(--shadow-pop)]">
            <div className="flex items-start justify-between">
              <span className="flex h-11 w-11 items-center justify-center rounded-[13px] border border-line bg-white shadow-[var(--shadow-card)]">
                <s.icon size={22} />
              </span>
              <Badge tone={tone[s.status as keyof typeof tone]}>{s.status}</Badge>
            </div>
            <p className="mt-3.5 text-[15px] font-bold text-ink-900">{s.name}</p>
            <p className="mt-0.5 text-[12.5px] text-ink-500">{s.desc}</p>
            <div className="mt-4 flex items-center gap-4 border-t border-line pt-3.5 text-[12px] text-ink-500">
              <span className="inline-flex items-center gap-1.5">
                <FileText size={13} className="text-ink-400" />
                <strong className="font-semibold text-ink-900">{s.docs}</strong> docs
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Clock size={13} className="text-ink-400" />
                {s.sync}
              </span>
              <button className="ml-auto text-ink-400 transition hover:text-brand-500" aria-label={`Sync ${s.name}`}>
                <RefreshCw size={14} />
              </button>
            </div>
          </Card>
        ))}

        <button className="flex min-h-[176px] flex-col items-center justify-center gap-2.5 rounded-[18px] border-2 border-dashed border-ink-300/60 text-ink-400 transition hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-500">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-white shadow-[var(--shadow-card)]">
            <Plus size={18} />
          </span>
          <span className="text-[13.5px] font-semibold">Add another source</span>
        </button>
      </div>

      <div className="mt-6 animate-rise-2">
        <CardLink href="/data-sources">Manage sync schedules in Data Sources</CardLink>
      </div>
    </div>
  );
}
