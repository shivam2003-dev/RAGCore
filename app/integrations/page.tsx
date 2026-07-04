import { Search, Workflow, Webhook, TerminalSquare, Bot, Mail, Calendar, Sparkles } from "lucide-react";
import { Card, PageHeader, Badge, Toggle, cx } from "@/components/ui";
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
} from "@/components/brand-icons";

const connected = [
  { name: "Slack", desc: "Ask Kimbal from any channel with /kimbal", icon: SlackIcon, on: true },
  { name: "Microsoft Teams", desc: "Kimbal bot for Teams chats and meetings", icon: TeamsIcon, on: true },
  { name: "Jira", desc: "Surface related knowledge inside issues", icon: JiraIcon, on: true },
  { name: "Confluence", desc: "Inline answer panel on every page", icon: ConfluenceIcon, on: true },
  { name: "GitHub", desc: "Answer questions in PR review threads", icon: GitHubIcon, on: true },
  { name: "Google Drive", desc: "Instant answers from Docs and Sheets", icon: GoogleDriveIcon, on: true },
  { name: "Notion", desc: "Sync wikis and databases into Kimbal", icon: NotionIcon, on: false },
  { name: "SharePoint", desc: "Index sites and document libraries", icon: SharePointIcon, on: true },
  { name: "GitLab", desc: "Index repos, wikis and snippets", icon: GitLabIcon, on: true },
];

const available = [
  { name: "Kimbal API", desc: "REST API for custom RAG applications", icon: TerminalSquare },
  { name: "Webhooks", desc: "Push sync and answer events anywhere", icon: Webhook },
  { name: "Kimbal Copilot", desc: "Browser extension for in-context answers", icon: Bot },
  { name: "Email Digest", desc: "Weekly knowledge gaps and health summary", icon: Mail },
  { name: "Calendar", desc: "Meeting-aware knowledge suggestions", icon: Calendar },
  { name: "Zapier", desc: "Connect Kimbal to 6,000+ apps", icon: Workflow },
];

export default function IntegrationsPage() {
  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="Bring Kimbal answers into the tools your teams already use."
        actions={
          <label className="flex h-10 w-64 cursor-text items-center gap-2.5 rounded-[10px] border border-line bg-white px-3.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50">
            <Search size={15} className="text-ink-400" />
            <input placeholder="Search integrations..." className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-ink-400" />
          </label>
        }
      />

      <section className="animate-rise-1">
        <div className="mb-3 flex items-center gap-3">
          <h2 className="text-[13px] font-bold uppercase tracking-[0.1em] text-ink-400">Connected</h2>
          <span className="h-px flex-1 bg-line" />
          <Badge tone="green">8 active</Badge>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {connected.map((i) => (
            <Card key={i.name} className={cx("flex items-start gap-3.5 p-4.5 p-5 transition hover:shadow-[var(--shadow-pop)]", !i.on && "opacity-70")}>
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] border border-line bg-white shadow-[var(--shadow-card)]">
                <i.icon size={22} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-bold text-ink-900">{i.name}</p>
                <p className="mt-0.5 text-[12.5px] leading-snug text-ink-500">{i.desc}</p>
              </div>
              <Toggle on={i.on} label={`${i.name} integration`} />
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-8 animate-rise-2">
        <div className="mb-3 flex items-center gap-3">
          <h2 className="text-[13px] font-bold uppercase tracking-[0.1em] text-ink-400">Available</h2>
          <span className="h-px flex-1 bg-line" />
        </div>
        <div className="grid grid-cols-3 gap-4">
          {available.map((i) => (
            <Card key={i.name} className="group flex items-start gap-3.5 p-5 transition hover:shadow-[var(--shadow-pop)]">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-brand-50 text-brand-500">
                <i.icon size={20} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-bold text-ink-900">{i.name}</p>
                <p className="mt-0.5 text-[12.5px] leading-snug text-ink-500">{i.desc}</p>
              </div>
              <button className="rounded-[9px] border border-brand-200 bg-white px-3.5 py-1.5 text-[12.5px] font-semibold text-brand-600 transition hover:bg-brand-50">
                Connect
              </button>
            </Card>
          ))}
        </div>
      </section>

      <Card className="mt-8 flex items-center gap-5 overflow-hidden bg-gradient-to-r from-brand-50/80 via-white to-sky-50/60 p-6 animate-rise-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[14px] bg-white text-brand-500 shadow-[var(--shadow-pop)]">
          <Sparkles size={22} />
        </span>
        <div className="flex-1">
          <p className="text-[15px] font-bold text-ink-900">Build your own integration</p>
          <p className="mt-0.5 text-[13px] text-ink-500">
            Use the Kimbal API and webhooks to embed retrieval-augmented answers in any internal tool.
          </p>
        </div>
        <button className="rounded-[10px] bg-brand-500 px-4.5 px-5 py-2.5 text-[13px] font-semibold text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.5)] transition hover:bg-brand-600">
          View API docs
        </button>
      </Card>
    </div>
  );
}
