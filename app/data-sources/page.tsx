import { Plus, RefreshCw, Pause, MoreHorizontal, Database, CheckCircle2, AlertTriangle, Loader } from "lucide-react";
import { Card, CardTitle, PageHeader, PrimaryButton, Badge, cx } from "@/components/ui";
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

const rows = [
  { name: "Jira", icon: JiraIcon, scope: "14 projects", docs: "12,430", schedule: "Every 15 min", last: "2 min ago", status: "Healthy" },
  { name: "Confluence", icon: ConfluenceIcon, scope: "22 spaces", docs: "8,245", schedule: "Every 15 min", last: "5 min ago", status: "Healthy" },
  { name: "Slack", icon: SlackIcon, scope: "48 channels", docs: "18,732", schedule: "Hourly", last: "1 hr ago", status: "Healthy" },
  { name: "Microsoft Teams", icon: TeamsIcon, scope: "12 teams", docs: "9,103", schedule: "Hourly", last: "1 hr ago", status: "Healthy" },
  { name: "GitHub", icon: GitHubIcon, scope: "86 repos", docs: "3,204", schedule: "Every 6 hrs", last: "3 hrs ago", status: "Healthy" },
  { name: "GitLab", icon: GitLabIcon, scope: "24 repos", docs: "1,187", schedule: "Every 6 hrs", last: "Running now", status: "Syncing" },
  { name: "SharePoint", icon: SharePointIcon, scope: "9 sites", docs: "4,410", schedule: "Daily", last: "6 hrs ago", status: "Healthy" },
  { name: "Google Drive", icon: GoogleDriveIcon, scope: "6 shared drives", docs: "6,512", schedule: "Hourly", last: "20 min ago", status: "Healthy" },
  { name: "Notion", icon: NotionIcon, scope: "3 workspaces", docs: "2,876", schedule: "Daily", last: "1 day ago", status: "Auth expiring" },
  { name: "PDF Uploads", icon: PdfIcon, scope: "Manual + S3 bucket", docs: "1,915", schedule: "On upload", last: "2 days ago", status: "Healthy" },
];

const statusMeta = {
  Healthy: { tone: "green" as const, icon: CheckCircle2 },
  Syncing: { tone: "blue" as const, icon: Loader },
  "Auth expiring": { tone: "amber" as const, icon: AlertTriangle },
};

export default function DataSourcesPage() {
  return (
    <div>
      <PageHeader
        title="Data Sources"
        subtitle="Connection health, sync schedules and indexing scope for every source."
        actions={<PrimaryButton><Plus size={15} /> Add Data Source</PrimaryButton>}
      />

      <div className="grid grid-cols-4 gap-5 animate-rise-1">
        {[
          { label: "Connected sources", value: "10" },
          { label: "Documents indexed", value: "54,102" },
          { label: "Syncs today", value: "312" },
          { label: "Failed syncs (7d)", value: "2" },
        ].map((s) => (
          <Card key={s.label} className="p-5">
            <p className="text-[12.5px] font-semibold text-ink-500">{s.label}</p>
            <p className="mt-2 text-[26px] font-bold tracking-[-0.02em] text-ink-900">{s.value}</p>
          </Card>
        ))}
      </div>

      <Card className="mt-5 animate-rise-2">
        <div className="p-5 pb-0">
          <CardTitle icon={Database} title="All Sources" right={<span className="text-[12px] font-semibold text-ink-400">Auto-sync enabled</span>} />
        </div>
        <table className="mt-3 w-full text-left">
          <thead>
            <tr className="border-b border-line text-[11.5px] font-bold uppercase tracking-[0.08em] text-ink-400">
              <th className="py-3 pl-5 font-bold">Source</th>
              <th className="font-bold">Scope</th>
              <th className="font-bold">Documents</th>
              <th className="font-bold">Sync schedule</th>
              <th className="font-bold">Last sync</th>
              <th className="font-bold">Status</th>
              <th className="pr-5 text-right font-bold">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r) => {
              const meta = statusMeta[r.status as keyof typeof statusMeta];
              return (
                <tr key={r.name} className="transition hover:bg-brand-50/30">
                  <td className="py-3.5 pl-5">
                    <span className="inline-flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-line bg-white">
                        <r.icon size={18} />
                      </span>
                      <span className="text-[13.5px] font-bold text-ink-900">{r.name}</span>
                    </span>
                  </td>
                  <td className="text-[13px] text-ink-700">{r.scope}</td>
                  <td className="text-[13px] font-semibold text-ink-900">{r.docs}</td>
                  <td className="text-[13px] text-ink-700">{r.schedule}</td>
                  <td className={cx("text-[13px]", r.last === "Running now" ? "font-semibold text-sky-600" : "text-ink-500")}>{r.last}</td>
                  <td>
                    <Badge tone={meta.tone}>
                      <meta.icon size={11} className={cx("mr-1", r.status === "Syncing" && "animate-spin")} />
                      {r.status}
                    </Badge>
                  </td>
                  <td className="pr-5">
                    <div className="flex items-center justify-end gap-1">
                      <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500" aria-label={`Sync ${r.name} now`}>
                        <RefreshCw size={14} />
                      </button>
                      <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500" aria-label={`Pause ${r.name}`}>
                        <Pause size={14} />
                      </button>
                      <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-white hover:text-brand-500" aria-label="More">
                        <MoreHorizontal size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
