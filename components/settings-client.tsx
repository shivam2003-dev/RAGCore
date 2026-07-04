"use client";

import { useCallback, useMemo, useState } from "react";
import {
  BadgeCheck,
  Bell,
  Building2,
  Check,
  ChevronDown,
  Copy,
  Database,
  Globe,
  KeyRound,
  Layers,
  ListChecks,
  Lock,
  Mail,
  Monitor,
  Moon,
  Palette,
  ScrollText,
  Search,
  Settings,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  User,
  Wand2,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { Card, CardLink, CardTitle, PageHeader, PrimaryButton, cx } from "@/components/ui";
import {
  applySettingsToDocument,
  defaultSettings,
  loadSettings,
  saveSettings,
  type SettingsState,
} from "@/lib/settings-store";
import { kimbalApi } from "@/lib/kimbal-api";

type SectionId =
  | "General"
  | "Profile"
  | "Authentication"
  | "Access & Permissions"
  | "Knowledge Sources"
  | "Data & Indexing"
  | "LLM & RAG"
  | "Integrations"
  | "Notifications"
  | "Security"
  | "Audit Logs"
  | "Advanced";

const sections: Array<{ label: SectionId; icon: LucideIcon }> = [
  { label: "General", icon: Settings },
  { label: "Profile", icon: User },
  { label: "Authentication", icon: Lock },
  { label: "Access & Permissions", icon: ShieldCheck },
  { label: "Knowledge Sources", icon: Database },
  { label: "Data & Indexing", icon: ListChecks },
  { label: "LLM & RAG", icon: Sun },
  { label: "Integrations", icon: Workflow },
  { label: "Notifications", icon: Bell },
  { label: "Security", icon: Shield },
  { label: "Audit Logs", icon: ScrollText },
  { label: "Advanced", icon: SlidersHorizontal },
];

const accents = ["#5b5ceb", "#38bdf8", "#22c55e", "#f97316", "#f43f5e", "#14b8a6"];

export function SettingsClient() {
  const [active, setActive] = useState<SectionId>("General");
  const [settings, setSettings] = useState<SettingsState>(() => loadSettings());
  const [status, setStatus] = useState("Loaded");

  function patch(next: Partial<SettingsState>) {
    setSettings((current) => {
      const updated = { ...current, ...next };
      applySettingsToDocument(updated);
      return updated;
    });
    setStatus("Unsaved changes");
  }

  function save(label = "Settings") {
    saveSettings(settings);
    setStatus(`${label} saved`);
  }

  const copyOrgId = useCallback(async () => {
    await navigator.clipboard.writeText(settings.organizationId);
    setStatus("Organization ID copied");
  }, [settings.organizationId]);

  const content = useMemo(() => {
    switch (active) {
      case "General":
        return (
          <>
            <SettingCard icon={Building2} title="Organization Details" desc="Manage organization identity.">
              <Field label="Organization Name">
                <TextInput value={settings.organizationName} onChange={(value) => patch({ organizationName: value })} />
              </Field>
              <Field label="Organization ID">
                <div className="flex h-10 items-center rounded-[10px] border border-line bg-white px-3.5 text-[13.5px] text-ink-900">
                  <input
                    value={settings.organizationId}
                    onChange={(event) => patch({ organizationId: event.target.value })}
                    className="min-w-0 flex-1 bg-transparent outline-none"
                  />
                  <button type="button" onClick={() => void copyOrgId()} aria-label="Copy organization ID">
                    <Copy size={14} className="text-ink-400" />
                  </button>
                </div>
              </Field>
              <Field label="Time Zone">
                <Select value={settings.timeZone} onChange={(timeZone) => patch({ timeZone })} options={["(GMT+05:30) Asia/Kolkata", "(GMT+00:00) UTC", "(GMT-08:00) America/Los_Angeles"]} />
              </Field>
            </SettingCard>

            <SettingCard icon={Globe} title="Language & Region" desc="Set localization defaults." tint="bg-sky-50 text-sky-500">
              <Field label="Language">
                <Select value={settings.language} onChange={(language) => patch({ language })} options={["English", "Hindi", "Spanish"]} />
              </Field>
              <Field label="Date Format">
                <Select value={settings.dateFormat} onChange={(dateFormat) => patch({ dateFormat })} options={["DD MMM, YYYY", "YYYY-MM-DD", "MM/DD/YYYY"]} />
              </Field>
              <Field label="Time Format">
                <Select value={settings.timeFormat} onChange={(timeFormat) => patch({ timeFormat })} options={["12-hour (AM/PM)", "24-hour"]} />
              </Field>
            </SettingCard>

            <SettingCard icon={Palette} title="Theme" desc="Choose visual preferences.">
              <div className="grid grid-cols-3 gap-2.5">
                {[
                  { label: "Light" as const, icon: Sun },
                  { label: "Dark" as const, icon: Moon },
                  { label: "System" as const, icon: Monitor },
                ].map((item) => (
                  <button
                    type="button"
                    key={item.label}
                    onClick={() => patch({ theme: item.label })}
                    className={cx(
                      "relative flex flex-col items-center gap-2 rounded-[12px] border py-4 text-[12.5px] font-semibold transition",
                      settings.theme === item.label
                        ? "border-brand-300 bg-brand-50/60 text-brand-600 ring-2 ring-brand-100"
                        : "border-line text-ink-500 hover:border-brand-200"
                    )}
                  >
                    {settings.theme === item.label && <CheckMark />}
                    <item.icon size={18} />
                    {item.label}
                  </button>
                ))}
              </div>
              <Field label="Accent Color">
                <div className="flex gap-2.5">
                  {accents.map((color) => (
                    <button
                      type="button"
                      key={color}
                      aria-label={`Accent ${color}`}
                      onClick={() => patch({ accentColor: color })}
                      className={cx(
                        "flex h-7 w-7 items-center justify-center rounded-full transition hover:scale-110",
                        settings.accentColor === color && "ring-2 ring-brand-300 ring-offset-2"
                      )}
                      style={{ background: color }}
                    >
                      {settings.accentColor === color && <Check size={12} strokeWidth={3} className="text-white" />}
                    </button>
                  ))}
                </div>
              </Field>
            </SettingCard>
          </>
        );
      case "Profile":
        return (
          <>
            <SettingCard icon={User} title="Personal Profile" desc="Authenticated user identity.">
              <StaticRow title="Profile source" desc="Loaded from the backend session and access-control records." />
              <StaticRow title="Role changes" desc="Managed from Access Control, where updates call the admin role API." />
            </SettingCard>
            <SettingCard icon={BadgeCheck} title="Workspace Identity" desc="Local display metadata." tint="bg-sky-50 text-sky-500">
              <StaticRow title="Sidebar identity" desc="Uses the signed-in local operator identity for this development session." />
              <CardLink href="/access-control">Open Access Control</CardLink>
            </SettingCard>
          </>
        );
      case "Authentication":
        return (
          <>
            <SettingCard icon={Lock} title="Session Policy" desc="Backend-enforced authentication behavior.">
              <StaticRow title="Access token TTL" desc="15 minutes, configured by JWT_ACCESS_TTL_SECONDS on the API." />
              <StaticRow title="Refresh tokens" desc="Rotating one-time refresh tokens are enforced server-side." />
              <StaticRow title="MFA" desc="No MFA provider is implemented in this build." />
            </SettingCard>
            <SettingCard icon={KeyRound} title="SSO" desc="Enterprise identity integration." tint="bg-sky-50 text-sky-500">
              <StaticRow title="SSO provider" desc="Not configured; password auth and API keys are the implemented auth paths." />
              <StaticRow title="User provisioning" desc="Users are created through the backend registration flow." />
            </SettingCard>
          </>
        );
      case "Access & Permissions":
        return (
          <>
            <SettingCard icon={ShieldCheck} title="RBAC" desc="Role controls backed by the admin API.">
              <StaticRow title="Roles" desc="Admin, editor, and viewer roles are enforced by backend dependencies." />
              <StaticRow title="Role updates" desc="Use Access Control to update users through PATCH /admin/users/{id}/role." />
              <CardLink href="/access-control">Manage users</CardLink>
            </SettingCard>
            <SettingCard icon={User} title="Invites" desc="Member invite workflow." tint="bg-sky-50 text-sky-500">
              <StaticRow title="Invitations" desc="No invite endpoint exists yet, so invite controls are disabled in Access Control." />
              <StaticRow title="Allowed domains" desc="Domain allow-listing is not implemented in this build." />
            </SettingCard>
          </>
        );
      case "Knowledge Sources":
        return (
          <>
            <SettingCard icon={Database} title="Source Sync" desc="External source ingestion.">
              <StaticRow title="Confluence DevOps1" desc="Read-only sync is available from Knowledge Sources and Data Sources." />
              <StaticRow title="Jira DEVO" desc="Read-only board sync is available from Knowledge Sources and Data Sources." />
              <CardLink href="/knowledge-sources">Open Knowledge Sources</CardLink>
            </SettingCard>
            <SettingCard icon={Workflow} title="Connector Defaults" desc="Default behavior for new sources." tint="bg-sky-50 text-sky-500">
              <StaticRow title="Scope" desc="Connector scopes are fixed by the backend service implementation." />
              <StaticRow title="Write safety" desc="Connectors use GET-only Atlassian API calls." />
            </SettingCard>
          </>
        );
      case "Data & Indexing":
        return (
          <>
            <SettingCard icon={Search} title="Search Settings" desc="Backend retrieval configuration." tint="bg-sky-50 text-sky-500">
              <StaticRow title="Hybrid retrieval" desc="Dense vector search and Postgres full-text search are fused in the API." />
              <StaticRow title="Weights" desc="Dense 0.7 and sparse 0.3 weights come from backend configuration." />
              <StaticRow title="Top K" desc="The Ask flow requests ranked hits from the live backend search endpoint." />
            </SettingCard>
            <SettingCard icon={Layers} title="Content Processing" desc="Indexing behavior.">
              <StaticRow title="Chunking" desc="Chunk size and overlap are configured on the API process." />
              <StaticRow title="PII redaction" desc="Structured logs are scrubbed by backend middleware." />
            </SettingCard>
          </>
        );
      case "LLM & RAG":
        return (
          <>
            <SettingCard icon={Wand2} title="RAG Settings" desc="Retrieval and answer generation.">
              <StaticRow title="Retrieval mode" desc="Hybrid retrieval is the implemented production path." />
              <StaticRow title="Reranker" desc="No reranker provider is active in this build." />
              <StaticRow title="Generation model" desc="Configured server-side through LLM_PROVIDER and LLM_MODEL." />
            </SettingCard>
            <SettingCard icon={Shield} title="Grounding" desc="Answer guardrails." tint="bg-sky-50 text-sky-500">
              <StaticRow title="Citations" desc="Citation markers are emitted by the Ask flow and linked to retrieved chunks." />
              <StaticRow title="Prompt injection shield" desc="Source text is wrapped as untrusted evidence in the backend prompt." />
            </SettingCard>
          </>
        );
      case "Integrations":
        return (
          <>
            <SettingCard icon={Workflow} title="Implemented Connectors" desc="Production-backed integrations in this build.">
              <StaticRow title="Confluence" desc="Read-only DevOps1 space sync through the backend API." />
              <StaticRow title="Jira" desc="Read-only DEVO board sync through the backend API." />
              <StaticRow title="Kimbal API" desc="OpenAPI available at the backend /docs endpoint." />
            </SettingCard>
            <SettingCard icon={Mail} title="Digest" desc="Scheduled summaries.">
              <StaticRow title="Email Digest" desc="Not implemented yet; no background email worker exists." />
            </SettingCard>
          </>
        );
      case "Notifications":
        return (
          <>
            <SettingCard icon={Bell} title="Notification Preferences" desc="Notification channel status.">
              <StaticRow title="Email Digest" desc="Not implemented; no scheduled email worker is configured." />
              <StaticRow title="Security Alerts" desc="Audit events are stored in the database and surfaced in the top bar." />
              <StaticRow title="Query Suggestions" desc="The Ask page uses local starter prompts only." />
            </SettingCard>
            <SettingCard icon={User} title="Feedback" desc="User answer ratings.">
              <StaticRow title="Answer feedback" desc="Helpful and not helpful actions post to the backend feedback API." />
            </SettingCard>
          </>
        );
      case "Security":
        return (
          <>
            <SettingCard icon={Shield} title="Security Controls" desc="Runtime protection settings.">
              <StaticRow title="PII redaction" desc="Enabled in backend structured logging." />
              <StaticRow title="Rate limiting" desc="Redis-backed API limits are enforced by middleware." />
              <StaticRow title="Upload validation" desc="Magic-byte checks reject unsupported files before ingestion." />
            </SettingCard>
            <SettingCard icon={Lock} title="Secrets" desc="Credential handling.">
              <StaticRow title="Key storage" desc="Provider and Atlassian tokens stay in backend environment variables." />
            </SettingCard>
          </>
        );
      case "Audit Logs":
        return (
          <>
            <SettingCard icon={ScrollText} title="Audit Logging" desc="Sensitive action history.">
              <StaticRow title="Audit storage" desc="Sensitive actions are persisted in the audit_log table." />
              <StaticRow title="Top-bar activity" desc="Recent audit entries are read through /metrics/overview." />
              <StaticRow title="Export" desc="No audit export endpoint is implemented yet." />
            </SettingCard>
          </>
        );
      case "Advanced":
        return (
          <>
            <SettingCard icon={SlidersHorizontal} title="Advanced Runtime" desc="Local runtime diagnostics.">
              <StaticRow title="API base URL" desc={kimbalApi.baseUrl} />
              <StaticRow title="Response cache" desc="Cache TTL is configured on the API process." />
              <StaticRow title="Analytics" desc="The UI only shows metrics that exist in the backend database." />
            </SettingCard>
          </>
        );
    }
  }, [active, copyOrgId, settings]);

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Manage preferences, RAG controls, security and runtime configuration."
        actions={
          <div className="flex items-center gap-3">
            <span className="rounded-full border border-line bg-white px-3 py-1.5 text-[12.5px] font-semibold text-ink-500">
              {status}
            </span>
            <PrimaryButton onClick={() => save(active)}>Save Changes</PrimaryButton>
          </div>
        }
      />

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-3 animate-rise-1">
          <Card className="p-2.5">
            <ul className="space-y-0.5">
              {sections.map((section) => {
                const Icon = section.icon;
                const current = active === section.label;
                return (
                  <li key={section.label}>
                    <button
                      type="button"
                      onClick={() => setActive(section.label)}
                      className={cx(
                        "flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left text-[13.5px] font-medium transition",
                        current
                          ? "bg-brand-50 font-semibold text-brand-600"
                          : "text-ink-500 hover:bg-canvas hover:text-ink-900"
                      )}
                    >
                      <Icon size={16} className={current ? "text-brand-500" : "text-ink-400"} />
                      {section.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </Card>

          <Card className="mt-5 bg-gradient-to-br from-brand-50/70 to-white p-5">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-brand-500 shadow-[var(--shadow-card)]">
              <BadgeCheck size={17} />
            </span>
            <p className="mt-3 text-[14px] font-bold text-ink-900">Need help?</p>
            <p className="mt-1 text-[12.5px] text-ink-500">Open API docs or contact support.</p>
            <div className="mt-3">
              <CardLink href="http://localhost:8000/docs">View Documentation</CardLink>
            </div>
          </Card>
        </div>

        <div className="col-span-9 animate-rise-2">
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-[17px] font-bold text-ink-900">{active}</h2>
              <button
                type="button"
                onClick={() => {
                  setSettings(defaultSettings);
                  applySettingsToDocument(defaultSettings);
                  setStatus("Defaults restored");
                }}
                className="rounded-[9px] border border-line px-3 py-1.5 text-[12px] font-semibold text-ink-500 transition hover:border-brand-200 hover:text-brand-600"
              >
                Restore defaults
              </button>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-5">{content}</div>
            <Card className="mt-5 flex items-center gap-4 bg-gradient-to-br from-brand-50/60 to-white p-5">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-white text-brand-500 shadow-[var(--shadow-pop)]">
                <ShieldCheck size={22} />
              </span>
              <div>
                <p className="text-[14px] font-bold text-ink-900">Settings saved locally</p>
                <p className="mt-1 text-[12.5px] text-ink-500">
                  UI preferences persist in this browser; backend provider keys remain server-side.
                </p>
              </div>
            </Card>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[12.5px] font-semibold text-ink-700">{label}</span>
      {children}
    </label>
  );
}

function TextInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="flex h-10 w-full rounded-[10px] border border-line bg-white px-3.5 text-[13.5px] text-ink-900 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
    />
  );
}

function Select({ value, options, onChange }: { value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <span className="relative block">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full appearance-none rounded-[10px] border border-line bg-white px-3.5 pr-9 text-[13.5px] text-ink-900 outline-none transition hover:border-brand-200 focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
      >
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
      <ChevronDown size={15} className="pointer-events-none absolute right-3 top-3 text-ink-400" />
    </span>
  );
}

function SettingCard({
  icon,
  title,
  desc,
  children,
  tint,
}: {
  icon: LucideIcon;
  title: string;
  desc: string;
  children: React.ReactNode;
  tint?: string;
}) {
  return (
    <Card className="flex flex-col p-5">
      <CardTitle icon={icon} title={title} tint={tint} />
      <p className="mt-1.5 pl-[42px] text-[12px] text-ink-500">{desc}</p>
      <div className="mt-4 flex flex-1 flex-col gap-4">{children}</div>
    </Card>
  );
}

function StaticRow({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex items-center justify-between gap-6 rounded-[12px] bg-canvas px-4 py-3">
      <div>
        <p className="text-[13.5px] font-semibold text-ink-900">{title}</p>
        <p className="text-[12px] text-ink-500">{desc}</p>
      </div>
      <span className="rounded-full border border-line bg-white px-2.5 py-1 text-[11.5px] font-semibold text-ink-500">
        Read only
      </span>
    </div>
  );
}

function CheckMark() {
  return (
    <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-brand-500 text-white">
      <Check size={10} strokeWidth={3} />
    </span>
  );
}
