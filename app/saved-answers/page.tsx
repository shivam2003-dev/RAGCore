import { Sparkles, Bookmark, Share2, Trash2, Search, FolderOpen } from "lucide-react";
import { Card, PageHeader, GhostButton, Badge } from "@/components/ui";

const saved = [
  {
    q: "How do I deploy a new microservice on Kubernetes in production?",
    a: "Build and push the Docker image to harbor.kimbal.io, create manifests from the service-template repo, run kubectl diff, then deploy through the ArgoCD pipeline via a PR to infrastructure-configs…",
    area: "DevOps",
    sources: 8,
    saved: "Today, 10:26 AM",
  },
  {
    q: "What is our incident response process?",
    a: "Declare severity in #incidents, page the on-call via PagerDuty, assign an incident commander, open a live incident doc, and hold the postmortem within 48 hours of resolution…",
    area: "Security",
    sources: 5,
    saved: "Yesterday",
  },
  {
    q: "How to request access to production logs?",
    a: "Production log access is granted through the access-request workflow in the IT portal. Choose 'Observability — Read Only', get manager approval, and access syncs to Grafana within 15 minutes…",
    area: "Engineering",
    sources: 4,
    saved: "2 days ago",
  },
  {
    q: "What are the code review SLAs for each team?",
    a: "Reviews must start within 4 business hours. Payments and Security-tagged PRs require two approvers, one from the owning squad. Stale PRs auto-escalate to the EM after 24 hours…",
    area: "Engineering",
    sources: 6,
    saved: "Last week",
  },
  {
    q: "How do quarterly OKRs get finalized?",
    a: "Draft OKRs are proposed by each pillar lead in week 10, calibrated in the leads review during week 11, and locked in Notion by the first Monday of the new quarter…",
    area: "Product",
    sources: 3,
    saved: "2 weeks ago",
  },
];

export default function SavedAnswersPage() {
  return (
    <div>
      <PageHeader
        title="Saved Answers"
        subtitle="Answers you saved from Ask Kimbal, ready to revisit and share."
        actions={<GhostButton><FolderOpen size={15} /> Manage collections</GhostButton>}
      />

      <label className="mb-5 flex h-11 max-w-xl cursor-text items-center gap-2.5 rounded-[12px] border border-line bg-white px-4 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50 animate-rise-1">
        <Search size={15} className="text-ink-400" />
        <input
          placeholder="Search saved answers..."
          className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-ink-400"
        />
      </label>

      <div className="space-y-4 animate-rise-2">
        {saved.map((s) => (
          <Card key={s.q} className="group p-5 transition hover:shadow-[var(--shadow-pop)]">
            <div className="flex items-start gap-4">
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-[11px] bg-brand-50 text-brand-500">
                <Sparkles size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <p className="text-[14.5px] font-bold text-ink-900 transition group-hover:text-brand-600">{s.q}</p>
                  <Badge>{s.area}</Badge>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-ink-500">{s.a}</p>
                <div className="mt-3 flex items-center gap-4 text-[12px] text-ink-400">
                  <span>{s.sources} sources cited</span>
                  <span>•</span>
                  <span>Saved {s.saved}</span>
                </div>
              </div>
              <div className="flex shrink-0 gap-1">
                <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-brand-500" aria-label="Saved">
                  <Bookmark size={15} fill="currentColor" />
                </button>
                <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-canvas hover:text-brand-500" aria-label="Share">
                  <Share2 size={15} />
                </button>
                <button className="flex h-8 w-8 items-center justify-center rounded-[8px] text-ink-400 transition hover:bg-rose-50 hover:text-rose-500" aria-label="Delete">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
