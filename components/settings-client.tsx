"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  Bell,
  Bot,
  Check,
  ChevronDown,
  CircleAlert,
  Database,
  Gauge,
  Globe2,
  KeyRound,
  Layers3,
  Loader2,
  Monitor,
  Moon,
  Palette,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Sun,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import { Badge, Card, CardLink, GhostButton, PageHeader, PrimaryButton, cx } from "@/components/ui";
import {
  applySettingsToDocument,
  defaultSettings,
  loadSettings,
  saveSettings,
  type SettingsState,
} from "@/lib/settings-store";
import {
  cvumApi,
  type ChatCapabilities,
  type ConfluenceStatus,
  type EvalOverview,
  type JiraStatus,
  type RuntimeConfig,
  type UserOut,
  type WebSearchStatus,
  type WebSearchTest,
} from "@/lib/cvum-api";

type SectionId = "Workspace" | "Appearance" | "Retrieval" | "Connectors" | "Quality" | "Security";

const sections: Array<{ id: SectionId; icon: LucideIcon }> = [
  { id: "Workspace", icon: Settings2 },
  { id: "Appearance", icon: Palette },
  { id: "Retrieval", icon: Search },
  { id: "Connectors", icon: Database },
  { id: "Quality", icon: Gauge },
  { id: "Security", icon: ShieldCheck },
];

const accents = ["#5b5ceb", "#0ea5e9", "#16a34a", "#ea580c", "#e11d48", "#0f766e"];

type LiveSettings = {
  user: UserOut;
  runtime: RuntimeConfig;
  web: WebSearchStatus;
  confluence: ConfluenceStatus;
  jira: JiraStatus;
  capabilities: ChatCapabilities;
  evals: EvalOverview;
};

export function SettingsClient() {
  const [active, setActive] = useState<SectionId>("Workspace");
  const [settings, setSettings] = useState<SettingsState>(() => loadSettings());
  const [live, setLive] = useState<LiveSettings | null>(null);
  const [webTest, setWebTest] = useState<WebSearchTest | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("Loading runtime configuration");
  const [error, setError] = useState("");

  const refresh = useCallback(async (force = false) => {
    setLoading(true);
    setError("");
    try {
      if (force) cvumApi.refreshLiveData();
      const user = await cvumApi.ensureSession();
      const [runtime, web, confluence, jira, capabilities, evals] = await Promise.all([
        cvumApi.runtimeConfig(),
        cvumApi.webSearchStatus(),
        cvumApi.confluenceStatus(),
        cvumApi.jiraStatus(),
        cvumApi.chatCapabilities(),
        cvumApi.evalsOverview(),
      ]);
      setLive({ user, runtime, web, confluence, jira, capabilities, evals });
      setNotice("Runtime status is current");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load settings");
      setNotice("Runtime status unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  function patch(next: Partial<SettingsState>) {
    setSettings((current) => {
      const updated = { ...current, ...next };
      applySettingsToDocument(updated);
      return updated;
    });
    setNotice("Unsaved preference changes");
  }

  function save() {
    saveSettings(settings);
    setNotice("Browser preferences saved");
  }

  async function run(action: string, operation: () => Promise<unknown>) {
    setBusy(action);
    setError("");
    try {
      await operation();
      await refresh(true);
      setNotice(`${action} completed`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `${action} failed`);
    } finally {
      setBusy("");
    }
  }

  const content: Record<SectionId, ReactNode> = {
    Workspace: (
      <div className="grid gap-4 lg:grid-cols-2">
        <SettingsCard icon={UserRound} title="Operator">
          <LiveRow label="Name" value={live?.user.full_name ?? "Loading"} />
          <LiveRow label="Email" value={live?.user.email ?? "Loading"} />
          <LiveRow label="Role" value={live?.user.role ?? "Loading"} />
          <CardLink href="/access-control">Manage access</CardLink>
        </SettingsCard>
        <SettingsCard icon={Globe2} title="Locale">
          <Field label="Time zone">
            <Select value={settings.timeZone} onChange={(timeZone) => patch({ timeZone })} options={["(GMT+05:30) Asia/Kolkata", "(GMT+00:00) UTC", "(GMT-08:00) America/Los_Angeles"]} />
          </Field>
          <Field label="Date format">
            <Select value={settings.dateFormat} onChange={(dateFormat) => patch({ dateFormat })} options={["DD MMM, YYYY", "YYYY-MM-DD", "MM/DD/YYYY"]} />
          </Field>
          <Field label="Time format">
            <Select value={settings.timeFormat} onChange={(timeFormat) => patch({ timeFormat })} options={["12-hour (AM/PM)", "24-hour"]} />
          </Field>
        </SettingsCard>
        <SettingsCard icon={Bell} title="Notifications">
          <ToggleRow label="Security alerts" checked={settings.securityAlerts} onChange={(securityAlerts) => patch({ securityAlerts })} />
          <ToggleRow label="Answer feedback" checked={settings.answerFeedback} onChange={(answerFeedback) => patch({ answerFeedback })} />
          <ToggleRow label="Query suggestions" checked={settings.querySuggestions} onChange={(querySuggestions) => patch({ querySuggestions })} />
        </SettingsCard>
        <SettingsCard icon={Activity} title="Environment">
          <LiveRow label="Environment" value={live?.runtime.app_env ?? "Loading"} />
          <LiveRow label="API" value={cvumApi.baseUrl} />
          <LiveRow label="Authentication" value={live?.runtime.auth_disabled ? "Local bypass" : "Enforced"} />
        </SettingsCard>
      </div>
    ),
    Appearance: (
      <div className="grid gap-4 lg:grid-cols-2">
        <SettingsCard icon={Palette} title="Theme">
          <div className="grid grid-cols-3 gap-2">
            {([
              { label: "Light" as const, icon: Sun },
              { label: "Dark" as const, icon: Moon },
              { label: "System" as const, icon: Monitor },
            ]).map(({ label, icon: Icon }) => (
              <button key={label} type="button" onClick={() => patch({ theme: label })} className={cx("flex h-20 flex-col items-center justify-center gap-2 rounded-lg border text-[12px] font-semibold transition", settings.theme === label ? "border-brand-300 bg-brand-50 text-brand-600" : "border-line text-ink-500 hover:border-brand-200")}>
                <Icon size={18} />{label}
              </button>
            ))}
          </div>
        </SettingsCard>
        <SettingsCard icon={Layers3} title="Accent">
          <div className="flex flex-wrap gap-3">
            {accents.map((color) => (
              <button key={color} type="button" onClick={() => patch({ accentColor: color })} aria-label={`Use ${color} accent`} className={cx("flex h-9 w-9 items-center justify-center rounded-full ring-offset-2 transition", settings.accentColor === color && "ring-2 ring-brand-400")} style={{ backgroundColor: color }}>
                {settings.accentColor === color && <Check size={15} className="text-white" strokeWidth={3} />}
              </button>
            ))}
          </div>
        </SettingsCard>
      </div>
    ),
    Retrieval: (
      <div className="grid gap-4 lg:grid-cols-2">
        <SettingsCard icon={Search} title="Hybrid retrieval">
          <LiveRow label="Final context" value={`${live?.runtime.retrieval.top_k ?? "-"} chunks`} />
          <LiveRow label="Candidate pool" value={`${live?.runtime.retrieval.candidate_k ?? "-"} per arm`} />
          <LiveRow label="Dense weight" value={String(live?.runtime.retrieval.dense_weight ?? "-")} />
          <LiveRow label="Keyword weight" value={String(live?.runtime.retrieval.sparse_weight ?? "-")} />
        </SettingsCard>
        <SettingsCard icon={Bot} title="Answer modes">
          <LiveRow label="Fast" value="Enabled" />
          <LiveRow label="Council" value={live?.capabilities.council_configured ? "Enabled" : "Unavailable"} />
          <LiveRow label="Council evaluator" value={live?.capabilities.council_chair_model ?? "Not configured"} />
          <LiveRow label="Available models" value={String(live?.capabilities.council_available_models.length ?? 0)} />
        </SettingsCard>
        {Object.entries(live?.runtime.chunking ?? {}).map(([source, profile]) => (
          <SettingsCard key={source} icon={Layers3} title={`${capitalize(source)} chunking`}>
            <LiveRow label="Profile" value={profile.profile} />
            <LiveRow label="Chunk size" value={`${profile.size_tokens} tokens`} />
            <LiveRow label="Overlap" value={`${profile.overlap_tokens} tokens`} />
            {profile.excluded_issue_types?.length ? <LiveRow label="Excluded types" value={profile.excluded_issue_types.join(", ")} /> : null}
            {profile.comments_indexed != null ? <LiveRow label="Comments" value={profile.comments_indexed ? "Indexed" : "Disabled"} /> : null}
            {profile.attachments_extracted != null ? <LiveRow label="Attachments" value={profile.attachments_extracted ? "Office, PDF and image text" : "Metadata only"} /> : null}
          </SettingsCard>
        ))}
      </div>
    ),
    Connectors: (
      <div className="grid gap-4 lg:grid-cols-2">
        <ConnectorCard title="Tavily Web" configured={Boolean(live?.web.configured)} detail={`${live?.web.provider ?? "-"} / top ${live?.web.top_k ?? "-"}`} busy={busy === "Web test"} actionLabel="Test provider" onAction={() => void run("Web test", async () => setWebTest(await cvumApi.testWebSearch()))}>
          {webTest && <LiveRow label="Last test" value={`${webTest.result_count} results in ${webTest.latency_ms} ms`} />}
        </ConnectorCard>
        <ConnectorCard title="Confluence" configured={Boolean(live?.confluence.configured)} detail={`${live?.confluence.space_key ?? "-"} / read only`} busy={busy === "Confluence sync"} actionLabel="Sync now" onAction={() => void run("Confluence sync", () => cvumApi.syncConfluence())} />
        <ConnectorCard title="Jira" configured={Boolean(live?.jira.configured)} detail={`${live?.jira.project_key ?? "-"} / read only`} busy={busy === "Jira sync"} actionLabel="Sync now" onAction={() => void run("Jira sync", () => cvumApi.syncJira())} />
        <SettingsCard icon={Database} title="Source administration">
          <CardLink href="/data-sources">Open data sources</CardLink>
          <CardLink href="/knowledge-sources">Open knowledge sources</CardLink>
          <CardLink href="/integrations">Open integrations</CardLink>
        </SettingsCard>
      </div>
    ),
    Quality: (
      <div className="grid gap-4 lg:grid-cols-2">
        <SettingsCard icon={Gauge} title="Observed quality">
          <LiveRow label="Evaluated" value={String(live?.evals.quality.evaluated ?? 0)} />
          <LiveRow label="Healthy" value={String(live?.evals.quality.healthy ?? 0)} tone="good" />
          <LiveRow label="Needs review" value={String(live?.evals.quality.needs_review ?? 0)} tone="warn" />
          <LiveRow label="Failures" value={String(live?.evals.quality.failures ?? 0)} tone="bad" />
          <CardLink href="/evals">Open evals</CardLink>
        </SettingsCard>
        <SettingsCard icon={CircleAlert} title="Detected issues">
          {Object.entries(live?.evals.quality.issue_counts ?? {}).map(([issue, count]) => <LiveRow key={issue} label={formatIssue(issue)} value={String(count)} tone="bad" />)}
          {!Object.keys(live?.evals.quality.issue_counts ?? {}).length && <p className="text-[13px] text-ink-500">No observed quality incidents.</p>}
        </SettingsCard>
      </div>
    ),
    Security: (
      <div className="grid gap-4 lg:grid-cols-2">
        <SettingsCard icon={ShieldCheck} title="Access controls">
          <LiveRow label="Role" value={live?.user.role ?? "Loading"} />
          <LiveRow label="Session" value={live?.runtime.auth_disabled ? "Local development" : "Token protected"} />
          <CardLink href="/access-control">Manage users</CardLink>
        </SettingsCard>
        <SettingsCard icon={KeyRound} title="Credentials">
          <LiveRow label="Tavily key" value={live?.runtime.web.configured ? "Configured server-side" : "Missing"} />
          <LiveRow label="Atlassian tokens" value={live?.confluence.token_configured && live?.jira.token_configured ? "Configured server-side" : "Check connectors"} />
          <LiveRow label="Provider keys" value="Never exposed to the browser" />
        </SettingsCard>
      </div>
    ),
  };

  return (
    <div>
      <PageHeader title="Settings" subtitle="Effective workspace configuration and operational controls." actions={<div className="flex items-center gap-2"><GhostButton onClick={() => void refresh(true)} disabled={loading}>{loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}Refresh</GhostButton><PrimaryButton onClick={save}>Save preferences</PrimaryButton></div>} />
      {(error || notice) && <div className={cx("mb-5 flex items-center justify-between rounded-lg border px-4 py-3 text-[13px] font-semibold", error ? "border-rose-200 bg-rose-50 text-rose-700" : "border-line bg-white text-ink-600")}><span>{error || notice}</span><Badge tone={error ? "red" : "green"}>{error ? "Action required" : "Live"}</Badge></div>}
      <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav className="overflow-x-auto lg:overflow-visible" aria-label="Settings sections">
          <div className="flex min-w-max gap-1 rounded-lg border border-line bg-white p-1.5 shadow-[var(--shadow-card)] lg:min-w-0 lg:flex-col">
            {sections.map(({ id, icon: Icon }) => <button key={id} type="button" onClick={() => setActive(id)} className={cx("flex items-center gap-2.5 rounded-md px-3 py-2.5 text-left text-[13px] font-semibold transition", active === id ? "bg-brand-50 text-brand-600" : "text-ink-500 hover:bg-canvas hover:text-ink-900")}><Icon size={16} />{id}</button>)}
          </div>
        </nav>
        <section className="min-w-0">
          <div className="mb-4 flex items-center justify-between"><h2 className="text-[18px] font-bold text-ink-900">{active}</h2>{active === "Appearance" && <button type="button" onClick={() => { setSettings(defaultSettings); applySettingsToDocument(defaultSettings); setNotice("Appearance defaults restored"); }} className="text-[12px] font-semibold text-brand-600">Restore defaults</button>}</div>
          {content[active]}
        </section>
      </div>
    </div>
  );
}

function SettingsCard({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: ReactNode }) {
  return <Card className="min-w-0 p-5"><div className="flex items-center gap-2.5"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-500"><Icon size={16} /></span><h3 className="text-[14px] font-bold text-ink-900">{title}</h3></div><div className="mt-4 space-y-3">{children}</div></Card>;
}

function ConnectorCard({ title, configured, detail, busy, actionLabel, onAction, children }: { title: string; configured: boolean; detail: string; busy: boolean; actionLabel: string; onAction: () => void; children?: ReactNode }) {
  return <SettingsCard icon={Database} title={title}><div className="flex items-center justify-between gap-4"><div><Badge tone={configured ? "green" : "red"}>{configured ? "Configured" : "Unavailable"}</Badge><p className="mt-2 text-[12px] text-ink-500">{detail}</p></div><GhostButton onClick={onAction} disabled={!configured || busy}>{busy && <Loader2 size={14} className="animate-spin" />}{actionLabel}</GhostButton></div>{children}</SettingsCard>;
}

function LiveRow({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" | "bad" }) {
  return <div className="flex items-start justify-between gap-4 border-b border-line pb-3 last:border-0 last:pb-0"><span className="text-[12.5px] font-medium text-ink-500">{label}</span><span className={cx("max-w-[65%] break-words text-right text-[12.5px] font-semibold text-ink-900", tone === "good" && "text-emerald-600", tone === "warn" && "text-amber-600", tone === "bad" && "text-rose-600")}>{value}</span></div>;
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return <div className="flex items-center justify-between"><span className="text-[13px] font-medium text-ink-700">{label}</span><button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className={cx("relative h-6 w-11 rounded-full transition", checked ? "bg-brand-500" : "bg-ink-200")}><span className={cx("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition", checked ? "left-5.5" : "left-0.5")} /></button></div>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-[12px] font-semibold text-ink-600">{label}</span>{children}</label>;
}

function Select({ value, options, onChange }: { value: string; options: string[]; onChange: (value: string) => void }) {
  return <span className="relative block"><select value={value} onChange={(event) => onChange(event.target.value)} className="h-10 w-full appearance-none rounded-lg border border-line bg-white px-3 pr-9 text-[13px] text-ink-900 outline-none focus:border-brand-300 focus:ring-4 focus:ring-brand-50">{options.map((option) => <option key={option}>{option}</option>)}</select><ChevronDown size={15} className="pointer-events-none absolute right-3 top-3 text-ink-400" /></span>;
}

function capitalize(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function formatIssue(value: string) { return value.split("_").map(capitalize).join(" "); }
