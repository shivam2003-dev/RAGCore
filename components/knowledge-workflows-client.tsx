"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import {
  AlertTriangle,
  CalendarDays,
  ExternalLink,
  History,
  Loader2,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react";
import { Badge, Card, CardTitle, PageHeader, PrimaryButton, cx } from "@/components/ui";
import {
  kimbalApi,
  type ChangeResponse,
  type ExpertResponse,
  type IncidentCopilot,
  type Project,
} from "@/lib/kimbal-api";

type WorkflowTab = "incident" | "experts" | "changes";

const workflowTabs = [
  ["incident", "Incident Copilot", AlertTriangle],
  ["experts", "Who Knows This?", Users],
  ["changes", "What Changed?", History],
] as const;

function inputDate(daysAgo: number) {
  const value = new Date();
  value.setDate(value.getDate() - daysAgo);
  return value.toISOString().slice(0, 10);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function sourceTone(source: string): "blue" | "green" | "amber" | "gray" {
  if (source === "jira") return "blue";
  if (source === "github" || source === "github_pr") return "green";
  if (source === "slack") return "amber";
  return "gray";
}

export function KnowledgeWorkflowsClient() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [tab, setTab] = useState<WorkflowTab>("incident");
  const [issueKey, setIssueKey] = useState("DEVO-10416");
  const [expertQuery, setExpertQuery] = useState("gateway retry ownership");
  const [startDate, setStartDate] = useState(inputDate(30));
  const [endDate, setEndDate] = useState(inputDate(0));
  const [incident, setIncident] = useState<IncidentCopilot | null>(null);
  const [experts, setExperts] = useState<ExpertResponse | null>(null);
  const [changes, setChanges] = useState<ChangeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const tabButtons = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [rows, user] = await Promise.all([kimbalApi.listProjects(), kimbalApi.ensureSession()]);
        if (cancelled) return;
        setProjects(rows);
        setProjectId(rows.find((item) => item.id === user.default_project_id)?.id ?? rows[0]?.id ?? "");
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load projects");
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  const activeProject = useMemo(() => projects.find((item) => item.id === projectId), [projects, projectId]);

  async function runIncident(event: FormEvent) {
    event.preventDefault();
    if (!projectId || !issueKey.trim()) return;
    setLoading(true);
    setError("");
    setIncident(null);
    try {
      setIncident(await kimbalApi.incidentCopilot(projectId, issueKey.trim()));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Incident analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function runExperts(event: FormEvent) {
    event.preventDefault();
    if (!projectId || !expertQuery.trim()) return;
    setLoading(true);
    setError("");
    setExperts(null);
    try {
      setExperts(await kimbalApi.findExperts(projectId, expertQuery.trim()));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Expert search failed");
    } finally {
      setLoading(false);
    }
  }

  async function runChanges(event: FormEvent) {
    event.preventDefault();
    if (!projectId || !startDate || !endDate) return;
    setLoading(true);
    setError("");
    setChanges(null);
    try {
      setChanges(await kimbalApi.whatChanged(projectId, startDate, endDate));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Change summary failed");
    } finally {
      setLoading(false);
    }
  }

  function numberedFact(fact: string) {
    let result = fact;
    incident?.evidence.forEach((item, index) => {
      result = result.split(`[${item.citation_identity}]`).join(`[${index + 1}]`);
    });
    return result;
  }

  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % workflowTabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + workflowTabs.length) % workflowTabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = workflowTabs.length - 1;
    else return;
    event.preventDefault();
    setTab(workflowTabs[next][0]);
    setError("");
    tabButtons.current[next]?.focus();
  }

  return (
    <div>
      <PageHeader
        title="Incident Copilot"
        subtitle="Project-scoped operational workflows with cited facts, explicit inference, and permission-aware evidence."
        actions={activeProject ? <Badge tone="blue">{activeProject.name}</Badge> : undefined}
      />

      <Card className="mb-5 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="text-[12px] font-semibold text-ink-600">
            Project Lens
            <select
              aria-label="Workflow project"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              className="mt-1 h-10 w-full min-w-[220px] rounded-[10px] border border-line bg-white px-3 text-[13px] text-ink-900 outline-none focus:border-brand-300 sm:w-auto"
            >
              {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
            </select>
          </label>
          <p className="text-[12px] leading-5 text-ink-500 sm:ml-auto sm:max-w-[560px]">
            Results include only sources authorized for this project and your account. Private Slack participation is never queried.
          </p>
        </div>
      </Card>

      <div role="tablist" aria-label="Knowledge workflows" className="mb-5 grid grid-cols-3 gap-2 rounded-[14px] border border-line bg-white p-1.5">
        {workflowTabs.map(([value, label, Icon], index) => (
          <button
            key={value}
            ref={(element) => { tabButtons.current[index] = element; }}
            id={`workflow-tab-${value}`}
            type="button"
            role="tab"
            aria-selected={tab === value}
            aria-controls={`workflow-panel-${value}`}
            tabIndex={tab === value ? 0 : -1}
            onClick={() => { setTab(value); setError(""); }}
            onKeyDown={(event) => handleTabKey(event, index)}
            className={cx(
              "flex min-h-11 items-center justify-center gap-2 rounded-[10px] px-2 text-[12px] font-semibold transition sm:text-[13px]",
              tab === value ? "bg-brand-50 text-brand-600" : "text-ink-500 hover:bg-canvas hover:text-ink-900"
            )}
          >
            <Icon size={16} /> <span className="hidden sm:inline">{label}</span><span className="sm:hidden">{label.split(" ")[0]}</span>
          </button>
        ))}
      </div>

      {error && <div role="alert"><Card className="mb-5 border-rose-100 bg-rose-50 p-4 text-[13px] font-semibold text-rose-700">{error}</Card></div>}

      {tab === "incident" && (
        <div id="workflow-panel-incident" role="tabpanel" aria-labelledby="workflow-tab-incident" className="space-y-5">
          <Card className="p-5">
            <form onSubmit={runIncident} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="flex-1 text-[12px] font-semibold text-ink-600">
                Jira or CVIR key
                <input
                  aria-label="Incident key"
                  value={issueKey}
                  onChange={(event) => setIssueKey(event.target.value.toUpperCase())}
                  placeholder="CVIR-4242"
                  pattern="[A-Za-z][A-Za-z0-9]{1,9}-[0-9]+"
                  className="mt-1 h-11 w-full rounded-[10px] border border-line px-3 text-[14px] font-semibold uppercase outline-none focus:border-brand-300"
                />
              </label>
              <PrimaryButton type="submit" disabled={loading || !projectId || !issueKey.trim()} className="h-11 justify-center px-5">
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />} Investigate
              </PrimaryButton>
            </form>
          </Card>

          {!loading && !incident && <EmptyState title="No incident analysis yet" detail="Enter an issue key to assemble Jira, public Slack, Confluence, code, and recent PR evidence." />}
          {incident && (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <SummaryCard label="Incident" value={incident.issue_key} />
                <SummaryCard label="Current status" value={incident.current_status} />
                <SummaryCard label="Owner" value={incident.owner} />
              </div>
              {incident.partial && (
                <Card className="border-amber-100 bg-amber-50 p-4 text-[12.5px] text-amber-800">
                  Partial analysis: missing source families are shown below; no incident history was inferred to fill those gaps.
                </Card>
              )}
              <div className="grid gap-5 xl:grid-cols-2">
                <Card className="p-5">
                  <CardTitle icon={ShieldCheck} title="Facts" tint="bg-emerald-50 text-emerald-600" />
                  <ul className="mt-4 space-y-3 text-[13px] leading-6 text-ink-700">
                    {incident.facts.map((fact) => <li key={fact} className="rounded-[10px] bg-canvas px-3 py-2">{numberedFact(fact)}</li>)}
                    {!incident.facts.length && <li className="text-ink-500">No facts were found in authorized evidence.</li>}
                  </ul>
                </Card>
                <Card className="p-5">
                  <CardTitle icon={History} title="Cited timeline" tint="bg-sky-50 text-sky-600" />
                  <ol className="mt-4 space-y-4">
                    {incident.timeline.map((item) => {
                      const marker = incident.evidence.findIndex((source) => source.citation_identity === item.citation_identity) + 1;
                      return (
                        <li key={`${item.citation_identity}-${item.occurred_at}`} className="border-l-2 border-brand-100 pl-3">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">{formatDate(item.occurred_at)} · {item.source_type} [{marker}]</p>
                          <p className="mt-1 text-[13px] font-semibold text-ink-900">{item.label}</p>
                          <p className="mt-1 line-clamp-3 text-[12px] leading-5 text-ink-500">{item.detail}</p>
                        </li>
                      );
                    })}
                    {!incident.timeline.length && <li className="text-[13px] text-ink-500">No dated evidence was available.</li>}
                  </ol>
                </Card>
              </div>
              <div className="grid gap-5 lg:grid-cols-3">
                <ListCard title="Immediate checks" items={incident.immediate_checks} />
                <ListCard title="Likely next actions" items={incident.likely_next_actions} />
                <ListCard title="Missing evidence" items={incident.missing_evidence} />
              </div>
              <Card className="p-5">
                <CardTitle icon={Search} title={`Evidence (${incident.evidence.length})`} />
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {incident.evidence.map((item, index) => (
                    <div key={item.citation_identity} className="rounded-[12px] border border-line p-3">
                      <div className="flex items-center gap-2"><Badge tone={sourceTone(item.source_type)}>{item.source_type}</Badge><span className="text-[11px] font-bold text-brand-600">[{index + 1}]</span></div>
                      <p className="mt-2 line-clamp-1 text-[13px] font-semibold text-ink-900">{item.title}</p>
                      <p className="mt-1 line-clamp-2 text-[11.5px] leading-5 text-ink-500">{item.snippet}</p>
                      {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[11.5px] font-semibold text-brand-600">Open source <ExternalLink size={12} /></a>}
                    </div>
                  ))}
                </div>
              </Card>
            </>
          )}
        </div>
      )}

      {tab === "experts" && (
        <div id="workflow-panel-experts" role="tabpanel" aria-labelledby="workflow-tab-experts" className="space-y-5">
          <Card className="p-5">
            <form onSubmit={runExperts} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="flex-1 text-[12px] font-semibold text-ink-600">Topic, system, or incident<input aria-label="Expert topic" value={expertQuery} onChange={(event) => setExpertQuery(event.target.value)} className="mt-1 h-11 w-full rounded-[10px] border border-line px-3 text-[14px] outline-none focus:border-brand-300" /></label>
              <PrimaryButton type="submit" disabled={loading || !projectId || expertQuery.trim().length < 2} className="h-11 justify-center px-5">{loading ? <Loader2 size={16} className="animate-spin" /> : <Users size={16} />} Rank experts</PrimaryButton>
            </form>
          </Card>
          {!loading && !experts && <EmptyState title="No expert search yet" detail="Rank people from authorized Slack participation, Jira ownership, Confluence authorship, CODEOWNERS, and code contribution." />}
          {experts && !experts.experts.length && <EmptyState title="No expertise signals found" detail={experts.empty_reason ?? "Try a more specific system or issue key."} />}
          {experts?.experts.map((expert) => (
            <Card key={expert.person} className="p-5">
              <div className="flex items-start gap-4">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[14px] font-bold text-brand-600">#{expert.rank}</span>
                <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="text-[15px] font-semibold text-ink-900">{expert.person}</h2><Badge tone="blue">score {expert.score.toFixed(1)}</Badge></div><p className="mt-1 text-[12.5px] leading-5 text-ink-500">{expert.explanation}</p><div className="mt-3 flex flex-wrap gap-2">{expert.signals.map((signal, index) => <Badge key={`${String(signal.signal)}-${index}`} tone="gray">{String(signal.signal).replaceAll("_", " ")} · {String(signal.weight)}</Badge>)}</div></div>
                {expert.source_url && <a href={expert.source_url} target="_blank" rel="noreferrer" aria-label={`Open evidence for ${expert.person}`} className="text-ink-400 hover:text-brand-600"><ExternalLink size={16} /></a>}
              </div>
            </Card>
          ))}
        </div>
      )}

      {tab === "changes" && (
        <div id="workflow-panel-changes" role="tabpanel" aria-labelledby="workflow-tab-changes" className="space-y-5">
          <Card className="p-5">
            <form onSubmit={runChanges} className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <label className="text-[12px] font-semibold text-ink-600">Start date<input aria-label="Change start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 h-11 w-full rounded-[10px] border border-line px-3 text-[13px] outline-none focus:border-brand-300" /></label>
              <label className="text-[12px] font-semibold text-ink-600">End date<input aria-label="Change end date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 h-11 w-full rounded-[10px] border border-line px-3 text-[13px] outline-none focus:border-brand-300" /></label>
              <PrimaryButton type="submit" disabled={loading || !projectId || !startDate || !endDate} className="h-11 justify-center px-5">{loading ? <Loader2 size={16} className="animate-spin" /> : <CalendarDays size={16} />} Summarize</PrimaryButton>
            </form>
          </Card>
          {!loading && !changes && <EmptyState title="No change summary yet" detail="Choose a range up to 366 days to deduplicate authorized Jira, Confluence, Slack, and GitHub changes." />}
          {changes && !changes.changes.length && <EmptyState title="No changes found" detail="No authorized source changes have source timestamps inside this range." />}
          {changes?.changes.map((item) => (
            <Card key={item.citation_identity} className="p-5">
              <div className="flex flex-wrap items-center gap-2"><Badge tone={sourceTone(item.source_type)}>{item.source_type}</Badge><Badge tone="gray">{item.change_type}</Badge><span className="ml-auto text-[11px] text-ink-400">{formatDate(item.changed_at)}</span></div>
              <h2 className="mt-3 text-[15px] font-semibold text-ink-900">{item.title}</h2>
              <p className="mt-1 line-clamp-3 text-[12.5px] leading-5 text-ink-500">{item.summary}</p>
              {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-[11.5px] font-semibold text-brand-600">Original evidence <ExternalLink size={12} /></a>}
            </Card>
          ))}
          {changes && changes.deduplicated_count > 0 && <p className="text-center text-[11.5px] text-ink-400">Deduplicated {changes.deduplicated_count} related source change record(s).</p>}
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return <Card className="p-4"><p className="text-[10.5px] font-bold uppercase tracking-[0.1em] text-ink-400">{label}</p><p className="mt-2 truncate text-[17px] font-bold text-ink-900">{value}</p></Card>;
}

function ListCard({ title, items }: { title: string; items: string[] }) {
  return <Card className="p-5"><h2 className="text-[14px] font-semibold text-ink-900">{title}</h2><ul className="mt-3 space-y-2 text-[12px] leading-5 text-ink-600">{items.map((item) => <li key={item} className="rounded-[9px] bg-canvas px-3 py-2">{item}</li>)}{!items.length && <li className="text-ink-400">None</li>}</ul></Card>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <Card className="flex min-h-[220px] items-center justify-center p-8 text-center"><div><Search size={24} className="mx-auto text-ink-300" /><p className="mt-3 text-[14px] font-semibold text-ink-900">{title}</p><p className="mx-auto mt-1 max-w-[520px] text-[12.5px] leading-5 text-ink-500">{detail}</p></div></Card>;
}
