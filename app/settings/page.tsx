import {
  Settings,
  User,
  Lock,
  ShieldCheck,
  Database,
  ListChecks,
  Sun,
  Workflow,
  Bell,
  Shield,
  ScrollText,
  SlidersHorizontal,
  Building2,
  Globe,
  Palette,
  Search,
  Wand2,
  Layers,
  Moon,
  Monitor,
  Copy,
  ChevronDown,
  Check,
  BadgeCheck,
  type LucideIcon,
} from "lucide-react";
import { Card, CardTitle, PageHeader, PrimaryButton, Toggle, CardLink, cx } from "@/components/ui";

const sections: Array<{ label: string; icon: LucideIcon; active?: boolean }> = [
  { label: "General", icon: Settings, active: true },
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-[12.5px] font-semibold text-ink-700">{label}</p>
      {children}
    </div>
  );
}

function TextInput({ value, copy }: { value: string; copy?: boolean }) {
  return (
    <div className="flex h-10 items-center rounded-[10px] border border-line bg-white px-3.5 text-[13.5px] text-ink-900 transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50">
      <input defaultValue={value} className="min-w-0 flex-1 bg-transparent outline-none" />
      {copy && <Copy size={14} className="text-ink-400" />}
    </div>
  );
}

function Select({ value }: { value: string }) {
  return (
    <button className="flex h-10 w-full items-center justify-between rounded-[10px] border border-line bg-white px-3.5 text-[13.5px] text-ink-900 transition hover:border-brand-200">
      {value}
      <ChevronDown size={15} className="text-ink-400" />
    </button>
  );
}

function UpdateButton() {
  return (
    <div className="mt-4 flex justify-end">
      <button className="rounded-[9px] bg-brand-500 px-4 py-2 text-[12.5px] font-semibold text-white shadow-[0_4px_12px_-4px_rgba(91,92,235,0.5)] transition hover:bg-brand-600">
        Update
      </button>
    </div>
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

function ToggleRow({ title, desc, on = true }: { title: string; desc: string; on?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-6">
      <div>
        <p className="text-[13.5px] font-semibold text-ink-900">{title}</p>
        <p className="text-[12px] text-ink-500">{desc}</p>
      </div>
      <Toggle on={on} label={title} />
    </div>
  );
}

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Manage your preferences, configurations and system settings."
        actions={<PrimaryButton>Save Changes</PrimaryButton>}
      />

      <div className="grid grid-cols-12 gap-6">
        {/* section nav */}
        <div className="col-span-3 animate-rise-1">
          <Card className="p-2.5">
            <ul className="space-y-0.5">
              {sections.map((s) => (
                <li key={s.label}>
                  <button
                    className={cx(
                      "flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left text-[13.5px] font-medium transition",
                      s.active
                        ? "bg-brand-50 font-semibold text-brand-600"
                        : "text-ink-500 hover:bg-canvas hover:text-ink-900"
                    )}
                  >
                    <s.icon size={16} className={s.active ? "text-brand-500" : "text-ink-400"} />
                    {s.label}
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          <Card className="mt-5 bg-gradient-to-br from-brand-50/70 to-white p-5">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white text-brand-500 shadow-[var(--shadow-card)]">
              <BadgeCheck size={17} />
            </span>
            <p className="mt-3 text-[14px] font-bold text-ink-900">Need help?</p>
            <p className="mt-1 text-[12.5px] text-ink-500">Check our documentation or contact support.</p>
            <div className="mt-3">
              <CardLink href="#">View Documentation</CardLink>
            </div>
          </Card>
        </div>

        {/* content */}
        <div className="col-span-9 animate-rise-2">
          <Card className="p-6">
            <h2 className="text-[17px] font-bold text-ink-900">General Settings</h2>

            <div className="mt-5 grid grid-cols-3 gap-5">
              <SettingCard icon={Building2} title="Organization Details" desc="Manage your organization information.">
                <Field label="Organization Name"><TextInput value="Kimbal" /></Field>
                <Field label="Organization ID"><TextInput value="kimbal-tech" copy /></Field>
                <Field label="Time Zone"><Select value="(GMT+05:30) Asia/Kolkata" /></Field>
                <UpdateButton />
              </SettingCard>

              <SettingCard icon={Globe} title="Language & Region" desc="Set your preferred language and region." tint="bg-sky-50 text-sky-500">
                <Field label="Language"><Select value="English" /></Field>
                <Field label="Date Format"><Select value="DD MMM, YYYY" /></Field>
                <Field label="Time Format"><Select value="12-hour (AM/PM)" /></Field>
                <UpdateButton />
              </SettingCard>

              <SettingCard icon={Palette} title="Theme" desc="Choose your preferred appearance.">
                <div className="grid grid-cols-3 gap-2.5">
                  {[
                    { label: "Light", icon: Sun, active: true },
                    { label: "Dark", icon: Moon },
                    { label: "System", icon: Monitor },
                  ].map((t) => (
                    <button
                      key={t.label}
                      className={cx(
                        "relative flex flex-col items-center gap-2 rounded-[12px] border py-4 text-[12.5px] font-semibold transition",
                        t.active
                          ? "border-brand-300 bg-brand-50/60 text-brand-600 ring-2 ring-brand-100"
                          : "border-line text-ink-500 hover:border-brand-200"
                      )}
                    >
                      {t.active && (
                        <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-brand-500 text-white">
                          <Check size={10} strokeWidth={3} />
                        </span>
                      )}
                      <t.icon size={18} />
                      {t.label}
                    </button>
                  ))}
                </div>
                <Field label="Accent Color">
                  <div className="flex gap-2.5">
                    {["#5b5ceb", "#38bdf8", "#22c55e", "#f97316", "#f43f5e", "#14b8a6"].map((c, i) => (
                      <button
                        key={c}
                        aria-label={`Accent ${c}`}
                        className={cx(
                          "flex h-7 w-7 items-center justify-center rounded-full transition hover:scale-110",
                          i === 0 && "ring-2 ring-brand-300 ring-offset-2"
                        )}
                        style={{ background: c }}
                      >
                        {i === 0 && <Check size={12} strokeWidth={3} className="text-white" />}
                      </button>
                    ))}
                  </div>
                </Field>
                <UpdateButton />
              </SettingCard>

              <SettingCard icon={Search} title="Search Settings" desc="Configure search and retrieval preferences." tint="bg-sky-50 text-sky-500">
                <Field label="Default Search Model"><Select value="kimbal-embed-v2" /></Field>
                <Field label="Top K Results"><TextInput value="5" /></Field>
                <Field label="Chunk Size"><Select value="500 tokens" /></Field>
                <UpdateButton />
              </SettingCard>

              <SettingCard icon={Wand2} title="RAG Settings" desc="Configure retrieval and generation settings.">
                <Field label="Retrieval Mode"><Select value="Hybrid (Vector + Keyword)" /></Field>
                <Field label="Reranker Model"><Select value="kimbal-rerank-v1" /></Field>
                <Field label="Answer Generation Model"><Select value="claude-sonnet-5" /></Field>
                <UpdateButton />
              </SettingCard>

              <SettingCard icon={Layers} title="Content & Indexing" desc="Manage indexing and content processing.">
                <ToggleRow title="Auto-sync Sources" desc="Automatically sync documents from sources" />
                <Field label="Re-index Interval"><Select value="Daily" /></Field>
                <ToggleRow title="Incremental Indexing" desc="Only index changed documents" />
                <UpdateButton />
              </SettingCard>
            </div>

            {/* other preferences */}
            <div className="mt-5 grid grid-cols-3 gap-5">
              <Card className="col-span-2 p-5">
                <CardTitle icon={SlidersHorizontal} title="Other Preferences" />
                <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-5">
                  <ToggleRow title="Enable Answer Feedback" desc="Allow users to provide feedback on answers" />
                  <ToggleRow title="Enable Query Suggestions" desc="Show suggested questions on search" />
                  <ToggleRow title="Show Source Citations" desc="Display sources for all answers" />
                  <ToggleRow title="Enable Analytics Tracking" desc="Help improve Kimbal with usage analytics" />
                </div>
              </Card>
              <Card className="flex flex-col items-center justify-center bg-gradient-to-br from-brand-50/60 to-white p-5 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-brand-500 shadow-[var(--shadow-pop)]">
                  <ShieldCheck size={22} />
                </span>
                <p className="mt-3 text-[14px] font-bold text-ink-900">Your settings are secure</p>
                <p className="mt-1 text-[12.5px] text-ink-500">
                  All preferences are encrypted and saved securely.
                </p>
              </Card>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
