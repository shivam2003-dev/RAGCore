"use client";

import { Bot, Cloud, FileUp, GitBranch, Search, SquareKanban, TerminalSquare, Webhook } from "lucide-react";
import { Badge, Card, PageHeader } from "@/components/ui";
import { useLiveMetrics } from "@/components/use-live-metrics";

const planned = [
  { name: "Google Drive", desc: "No Drive connector is implemented in this build.", icon: FileUp },
  { name: "Webhooks", desc: "No outbound webhook delivery is implemented yet.", icon: Webhook },
];

export function IntegrationsClient() {
  const { confluence, jira, slack, github, metrics } = useLiveMetrics();
  const live = [
    {
      name: "Confluence",
      desc: confluence?.base_url
        ? `Read-only sync from ${confluence.base_url}, space ${confluence.space_key}.`
        : "Read-only Confluence sync is available after backend env configuration.",
      icon: Cloud,
      tone: confluence?.configured ? "green" as const : "amber" as const,
      status: confluence?.configured ? "Configured" : "Needs config",
    },
    {
      name: "Jira",
      desc: jira?.base_url
        ? `Read-only sync from ${jira.base_url}, project ${jira.project_key}, board ${jira.board_id}.`
        : "Read-only Jira sync is available after backend env configuration.",
      icon: SquareKanban,
      tone: jira?.configured ? "green" as const : "amber" as const,
      status: jira?.configured ? "Configured" : "Needs config",
    },
    {
      name: "Slack",
      desc: slack?.allowlisted_channels
        ? `Socket Mode indexing is allowlisted to ${slack.allowlisted_channels} public channel${slack.allowlisted_channels === 1 ? "" : "s"}.`
        : "Read-only Socket Mode indexing is available after credentials and a public-channel allowlist are configured.",
      icon: Bot,
      tone: slack?.configured ? "green" as const : "amber" as const,
      status: slack?.configured ? "Configured" : "Needs config",
    },
    {
      name: "GitHub",
      desc: github?.repositories.length
        ? `${github.repositories.length} read-only repository branch${github.repositories.length === 1 ? "" : "es"} mapped to projects.`
        : "Read-only incremental code indexing is available after a repository allowlist is configured.",
      icon: GitBranch,
      tone: github?.configured ? "green" as const : "amber" as const,
      status: github?.configured ? "Configured" : "Needs config",
    },
    {
      name: "CVUM API",
      desc: "FastAPI endpoints for auth, documents, search, chat, metrics, Confluence, and Jira sync.",
      icon: TerminalSquare,
      tone: "green" as const,
      status: "Available",
    },
    {
      name: "Manual Uploads",
      desc: `${metrics?.documents_total ?? 0} documents currently indexed through local upload/sync paths.`,
      icon: FileUp,
      tone: "green" as const,
      status: "Available",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="Implemented connectors and honest roadmap status."
        actions={
          <label className="flex h-10 w-64 cursor-text items-center gap-2.5 rounded-[10px] border border-line bg-white px-3.5 shadow-[var(--shadow-card)] opacity-60">
            <Search size={15} className="text-ink-400" />
            <input disabled placeholder="Search unavailable" className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-ink-400" />
          </label>
        }
      />

      <section className="animate-rise-1">
        <div className="mb-3 flex items-center gap-3">
          <h2 className="text-[13px] font-bold uppercase tracking-[0.1em] text-ink-400">Implemented</h2>
          <span className="h-px flex-1 bg-line" />
          <Badge tone="green">{live.length} available</Badge>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {live.map((item) => (
            <Card key={item.name} className="flex items-start gap-3.5 p-5 transition hover:shadow-[var(--shadow-pop)]">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] border border-line bg-white text-brand-500 shadow-[var(--shadow-card)]">
                <item.icon size={22} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-[14px] font-bold text-ink-900">{item.name}</p>
                  <Badge tone={item.tone}>{item.status}</Badge>
                </div>
                <p className="mt-1 text-[12.5px] leading-snug text-ink-500">{item.desc}</p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section className="mt-8 animate-rise-2">
        <div className="mb-3 flex items-center gap-3">
          <h2 className="text-[13px] font-bold uppercase tracking-[0.1em] text-ink-400">Not Implemented</h2>
          <span className="h-px flex-1 bg-line" />
          <Badge tone="gray">Disabled</Badge>
        </div>
        <div className="grid grid-cols-3 gap-4">
          {planned.map((item) => (
            <Card key={item.name} className="flex items-start gap-3.5 p-5 opacity-75">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-canvas text-ink-400">
                <item.icon size={20} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-bold text-ink-900">{item.name}</p>
                <p className="mt-0.5 text-[12.5px] leading-snug text-ink-500">{item.desc}</p>
              </div>
              <button disabled className="rounded-[9px] border border-line bg-white px-3.5 py-1.5 text-[12.5px] font-semibold text-ink-400">
                Disabled
              </button>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
