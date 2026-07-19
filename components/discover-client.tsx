"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  BriefcaseBusiness,
  Building2,
  Code2,
  ExternalLink,
  FileText,
  Loader2,
  Newspaper,
  RefreshCw,
  Search,
  ServerCog,
  ShieldAlert,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import { Badge, Card, GhostButton, cx } from "@/components/ui";
import { DiscoverArticle, DiscoverFeed, cvumApi } from "@/lib/cvum-api";

const departmentIcons: Record<string, LucideIcon> = {
  "for-you": Sparkles,
  devops: ServerCog,
  sre: AlertTriangle,
  development: Code2,
  security: ShieldAlert,
  hr: Users,
  finance: BriefcaseBusiness,
  product: Building2,
};

function compactDate(value: string | null) {
  if (!value) return "Live";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function hostLabel(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "source";
  }
}

function countLabel(value: number) {
  return new Intl.NumberFormat().format(value);
}

export function DiscoverClient({ surface = "page" }: { surface?: "page" | "ask" }) {
  const [department, setDepartment] = useState("for-you");
  const [feed, setFeed] = useState<DiscoverFeed | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const departments = feed?.departments ?? [];
  const selectedDepartment = departments.find((item) => item.id === feed?.department);
  const secondaryArticles = useMemo(() => {
    const ids = new Set([feed?.lead?.id].filter(Boolean));
    return (feed?.articles ?? []).filter((item) => !ids.has(item.id)).slice(0, 6);
  }, [feed]);

  async function load(nextDepartment = department, force = false) {
    setError(null);
    if (force) {
      cvumApi.refreshLiveData();
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    try {
      await cvumApi.ensureSession();
      const nextFeed = await cvumApi.discoverFeed(nextDepartment);
      setFeed(nextFeed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Discover feed");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load(department);
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department]);

  if (surface === "ask") {
    const compactItems = [
      ...(feed?.alerts ?? []),
      ...(feed?.research ?? []),
      ...(feed?.articles ?? []),
    ].filter((item, index, rows) => rows.findIndex((row) => row.id === item.id) === index);

    return (
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="flex items-center gap-2 text-[15px] font-bold text-ink-900">
              <Newspaper size={16} className="text-brand-500" />
              Discover
            </p>
            <p className="mt-1 text-[12.5px] text-ink-500">Live department radar.</p>
          </div>
          <button
            type="button"
            onClick={() => void load(department, true)}
            disabled={loading || refreshing}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-white text-ink-500 transition hover:text-brand-600 disabled:opacity-50"
            aria-label="Refresh Discover"
          >
            {refreshing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          </button>
        </div>

        <div className="mt-3 flex gap-1.5 overflow-x-auto pb-1">
          {(departments.length ? departments : fallbackDepartments()).slice(0, 6).map((item) => {
            const Icon = departmentIcons[item.id] ?? Newspaper;
            const active = department === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setDepartment(item.id)}
                className={cx(
                  "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[9px] px-2.5 text-[12px] font-semibold transition",
                  active ? "bg-ink-900 text-white" : "bg-canvas text-ink-500 hover:text-ink-900"
                )}
              >
                <Icon size={13} />
                {item.label}
              </button>
            );
          })}
        </div>

        {error && <p className="mt-3 rounded-[10px] bg-rose-50 px-3 py-2 text-[12px] text-rose-700">{error}</p>}
        {feed?.warnings[0] && (
          <p className="mt-3 rounded-[10px] bg-amber-50 px-3 py-2 text-[12px] text-amber-700">
            {feed.warnings[0]}
          </p>
        )}

        {loading && !feed ? (
          <div className="mt-4 flex h-24 items-center justify-center rounded-[12px] bg-canvas">
            <Loader2 size={18} className="animate-spin text-brand-500" />
          </div>
        ) : feed?.lead ? (
          <a href={feed.lead.url} target="_blank" rel="noreferrer" className="mt-4 block rounded-[12px] bg-canvas p-3 transition hover:bg-brand-50">
            <p className="text-[11.5px] font-semibold text-ink-400">
              {feed.lead.source || hostLabel(feed.lead.url)} - {compactDate(feed.lead.published_at)}
            </p>
            <p className="mt-1 line-clamp-3 text-[13.5px] font-semibold leading-5 text-ink-900">{feed.lead.title}</p>
            <p className="mt-2 line-clamp-2 text-[12px] leading-5 text-ink-500">{feed.lead.summary}</p>
          </a>
        ) : (
          <p className="mt-4 rounded-[12px] bg-canvas px-3 py-3 text-[12.5px] text-ink-500">
            No live articles loaded yet.
          </p>
        )}

        <div className="mt-3 divide-y divide-line">
          {compactItems.slice(0, 4).map((item) => (
            <a key={item.id} href={item.url} target="_blank" rel="noreferrer" className="block py-2.5">
              <p className="line-clamp-2 text-[12.5px] font-semibold leading-5 text-ink-700 hover:text-brand-500">
                {item.title}
              </p>
              <p className="mt-0.5 text-[11px] text-ink-400">{item.section} - {item.source || hostLabel(item.url)}</p>
            </a>
          ))}
        </div>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-[1320px] space-y-6">
      <section className="flex flex-wrap items-start justify-between gap-4 animate-rise">
        <div>
          <h1 className="text-[30px] font-bold tracking-[-0.02em] text-ink-900">Discover</h1>
          <p className="mt-1 text-[14px] text-ink-500">
            Live department radar from web sources plus indexed Jira and Confluence pulse.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Badge tone={feed?.configured ? "green" : "amber"}>{feed?.provider ?? "loading"}</Badge>
          <GhostButton onClick={() => void load(department, true)} disabled={loading || refreshing}>
            {refreshing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Refresh
          </GhostButton>
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-3 animate-rise-1">
        <div className="flex flex-wrap items-center gap-1.5">
          {(departments.length ? departments : fallbackDepartments()).map((item) => {
            const Icon = departmentIcons[item.id] ?? Newspaper;
            const active = department === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setDepartment(item.id)}
                className={cx(
                  "inline-flex h-9 items-center gap-2 rounded-[10px] px-3 text-[13px] font-semibold transition",
                  active ? "bg-ink-900 text-white shadow-[var(--shadow-card)]" : "text-ink-500 hover:bg-white hover:text-ink-900"
                )}
              >
                <Icon size={15} />
                {item.label}
              </button>
            );
          })}
        </div>
        <div className="flex min-w-[260px] items-center gap-2 rounded-[12px] border border-line bg-white px-3 py-2 text-[13px] text-ink-400">
          <Search size={15} />
          <span className="truncate">{selectedDepartment?.query ?? "Department intelligence feed"}</span>
        </div>
      </section>

      {error && (
        <Card className="border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">
          {error}
        </Card>
      )}

      {feed?.warnings.map((warning) => (
        <Card key={warning} className="border-amber-100 bg-amber-50 p-4 text-[13px] font-semibold text-amber-700">
          {warning}
        </Card>
      ))}

      <section className="grid grid-cols-12 gap-5 animate-rise-2">
        <div className="col-span-12 space-y-5 lg:col-span-8">
          {loading && !feed ? (
            <Card className="flex min-h-[360px] items-center justify-center p-8">
              <Loader2 size={26} className="animate-spin text-brand-500" />
            </Card>
          ) : feed?.lead ? (
            <LeadArticle article={feed.lead} />
          ) : (
            <Card className="p-8">
              <p className="text-[15px] font-semibold text-ink-900">No external updates loaded yet.</p>
              <p className="mt-1 text-[13px] text-ink-500">
                Configure Discover in backend env or use the internal board pulse on the right.
              </p>
            </Card>
          )}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {secondaryArticles.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        </div>

        <aside className="col-span-12 space-y-5 lg:col-span-4">
          {feed && <BoardPulse feed={feed} />}
          <ArticleRail title="Alerts" icon={ShieldAlert} items={feed?.alerts ?? []} empty="No live alerts found for this department." />
          <ArticleRail title="Research & Reads" icon={BookOpen} items={feed?.research ?? []} empty="No research items found yet." />
        </aside>
      </section>
    </div>
  );
}

function LeadArticle({ article }: { article: DiscoverArticle }) {
  return (
    <article className="overflow-hidden rounded-[18px] border border-line bg-white shadow-[var(--shadow-card)]">
      <a href={article.url} target="_blank" rel="noreferrer" className="group grid grid-cols-12 gap-0">
        <div className="col-span-12 p-6 md:p-7 xl:col-span-7">
          <div className="flex flex-wrap items-center gap-2 text-[12px] font-semibold text-ink-400">
            <span>{article.source || hostLabel(article.url)}</span>
            <span>-</span>
            <span>{compactDate(article.published_at)}</span>
          </div>
          <h2 className="mt-4 text-[25px] font-semibold leading-[1.12] tracking-[-0.02em] text-ink-900 md:text-[31px]">
            {article.title}
          </h2>
          <p className="mt-4 max-w-[680px] text-[15px] leading-7 text-ink-500">{article.summary}</p>
          <span className="mt-6 inline-flex items-center gap-2 text-[13px] font-semibold text-brand-500">
            Open source <ExternalLink size={14} className="transition-transform group-hover:translate-x-0.5" />
          </span>
        </div>
        <div className="col-span-12 min-h-[180px] bg-[linear-gradient(135deg,#f0f0fe,#eef7ff_45%,#f7f8fc)] p-5 xl:col-span-5 xl:min-h-[300px] xl:p-6">
          <div className="flex h-full flex-col justify-between rounded-[16px] border border-white/70 bg-white/60 p-5">
            <Newspaper size={30} className="text-brand-500" />
            <div>
              <p className="text-[12px] font-bold uppercase tracking-[0.12em] text-ink-400">{article.section}</p>
              <p className="mt-2 text-[22px] font-semibold tracking-[-0.02em] text-ink-900">{hostLabel(article.url)}</p>
            </div>
          </div>
        </div>
      </a>
    </article>
  );
}

function ArticleCard({ article }: { article: DiscoverArticle }) {
  return (
    <article className="rounded-[16px] border border-line bg-white p-4 shadow-[var(--shadow-card)]">
      <a href={article.url} target="_blank" rel="noreferrer" className="group block">
        <div className="mb-3 flex items-center justify-between gap-3 text-[12px] font-semibold text-ink-400">
          <span className="truncate">{article.source || hostLabel(article.url)}</span>
          <span className="shrink-0">{compactDate(article.published_at)}</span>
        </div>
        <h3 className="line-clamp-3 text-[18px] font-semibold leading-snug tracking-[-0.01em] text-ink-900">
          {article.title}
        </h3>
        <p className="mt-2 line-clamp-3 text-[13px] leading-6 text-ink-500">{article.summary}</p>
        <span className="mt-4 inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-brand-500">
          Read <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
        </span>
      </a>
    </article>
  );
}

function BoardPulse({ feed }: { feed: DiscoverFeed }) {
  const items = [
    ["Jira", feed.board_pulse.jira_documents],
    ["Confluence", feed.board_pulse.confluence_documents],
    ["Uploads", feed.board_pulse.upload_documents],
    ["Web", feed.board_pulse.web_documents],
  ];
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-brand-50 text-brand-500">
            <FileText size={16} />
          </span>
          <h2 className="text-[15px] font-semibold text-ink-900">Board Pulse</h2>
        </div>
        <Badge tone="blue">Live</Badge>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        {items.map(([label, value]) => (
          <div key={label} className="rounded-[12px] border border-line bg-canvas px-3 py-2">
            <p className="text-[11.5px] font-semibold text-ink-400">{label}</p>
            <p className="text-[22px] font-bold text-ink-900">{countLabel(Number(value))}</p>
          </div>
        ))}
      </div>
      <div className="mt-4 divide-y divide-line">
        {feed.board_pulse.latest_items.slice(0, 5).map((item) => {
          const body = (
            <>
              <span className="line-clamp-2 flex-1 text-[13px] font-semibold text-ink-700">{item.title}</span>
              <span className="whitespace-nowrap text-[11.5px] text-ink-400">{compactDate(item.updated_at)}</span>
            </>
          );
          return item.url ? (
            <a
              key={`${item.title}-${item.updated_at}`}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="flex gap-3 py-3 hover:text-brand-500"
            >
              {body}
            </a>
          ) : (
            <div key={`${item.title}-${item.updated_at}`} className="flex gap-3 py-3">
              {body}
            </div>
          );
        })}
        {!feed.board_pulse.latest_items.length && (
          <p className="py-3 text-[13px] text-ink-500">No indexed Jira or Confluence documents yet.</p>
        )}
      </div>
    </Card>
  );
}

function ArticleRail({
  title,
  icon: Icon,
  items,
  empty,
}: {
  title: string;
  icon: LucideIcon;
  items: DiscoverArticle[];
  empty: string;
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-sky-50 text-sky-600">
          <Icon size={16} />
        </span>
        <h2 className="text-[15px] font-semibold text-ink-900">{title}</h2>
      </div>
      <div className="mt-3 divide-y divide-line">
        {items.slice(0, 5).map((item) => (
          <a key={item.id} href={item.url} target="_blank" rel="noreferrer" className="block py-3">
            <p className="line-clamp-2 text-[13px] font-semibold leading-5 text-ink-800 hover:text-brand-500">{item.title}</p>
            <p className="mt-1 text-[11.5px] text-ink-400">
              {item.source || hostLabel(item.url)} - {compactDate(item.published_at)}
            </p>
          </a>
        ))}
        {!items.length && <p className="py-3 text-[13px] text-ink-500">{empty}</p>}
      </div>
    </Card>
  );
}

function fallbackDepartments() {
  return [
    { id: "for-you", label: "For You", description: "", query: "" },
    { id: "devops", label: "DevOps", description: "", query: "" },
    { id: "sre", label: "SRE", description: "", query: "" },
    { id: "development", label: "Development", description: "", query: "" },
    { id: "security", label: "Security", description: "", query: "" },
  ];
}
