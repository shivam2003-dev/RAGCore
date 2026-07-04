"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Bookmark,
  BookOpen,
  Check,
  Clock,
  FileText,
  Globe,
  Info,
  Layers,
  Loader2,
  Maximize2,
  MessageSquarePlus,
  Minimize2,
  Newspaper,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
  Send,
  Share2,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User,
  Users,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Card, CardLink, GhostButton, cx } from "@/components/ui";
import { DiscoverClient } from "@/components/discover-client";
import {
  kimbalApi,
  type AssistantRoleConfig,
  type AnswerMode,
  type ChatCapabilities,
  type Conversation,
  type CouncilConfig,
  type MessageOut,
  type RagSource,
  type SourceMode,
  type WebSearchStatus,
} from "@/lib/kimbal-api";

type ChatState = "idle" | "preparing" | "searching" | "streaming" | "done" | "error";

type Turn = {
  question: string;
  answer: string;
  sources: RagSource[];
  timings: Record<string, number>;
  sourceMode?: SourceMode;
  answerMode?: AnswerMode;
  assistantRole?: string;
  model?: string | null;
  messageId?: string;
};

const SOURCE_MODES: Array<{ value: SourceMode; label: string; icon: LucideIcon }> = [
  { value: "knowledge", label: "Knowledge", icon: BookOpen },
  { value: "web", label: "Web", icon: Globe },
  { value: "blended", label: "Both", icon: Layers },
];

const ANSWER_MODES: Array<{ value: AnswerMode; label: string; icon: LucideIcon }> = [
  { value: "fast", label: "Fast", icon: Zap },
  { value: "council", label: "Council", icon: Users },
];
const COUNCIL_SETTINGS_KEY = "kimbal.council.settings.v1";
const CUSTOM_ROLE_SETTINGS_KEY = "kimbal.custom.role.v1";

type OrgSpaceId = "sre" | "devops" | "developer" | "hr" | "custom";

type OrgSpace = {
  id: OrgSpaceId;
  label: string;
  shortLabel: string;
  description: string;
  prompt: string;
  placeholder: string;
  radar: string[];
  icon: LucideIcon;
};

const ORG_SPACES: OrgSpace[] = [
  {
    id: "sre",
    label: "SRE Space",
    shortLabel: "SRE",
    icon: Zap,
    description: "Incident triage, reliability, logs, metrics, and production debugging.",
    placeholder: "Ask SRE questions about incidents, alerts, logs, latency, rollout health...",
    radar: [
      "Latest SRE incident response patterns",
      "Major reliability alerts this week",
      "SRE conference talks to read",
      "New observability research and articles",
    ],
    prompt:
      "Act as a senior Site Reliability Engineer for Kimbal. Focus on incident triage, production debugging, reliability risk, service health, logs, metrics, SLO impact, rollback safety, and validation steps. Prefer Jira incidents, operational runbooks, postmortems, Confluence production notes, and deployment evidence. Give tight next actions, commands/checks when supported by sources, severity/blast-radius framing, and escalation criteria.",
  },
  {
    id: "devops",
    label: "DevOps Space",
    shortLabel: "DevOps",
    icon: Layers,
    description: "Kubernetes, CI/CD, ArgoCD, deployment, access, and infra workflows.",
    placeholder: "Ask DevOps questions about Kubernetes, ArgoCD, CI/CD, Jira deploy work...",
    radar: [
      "Kubernetes security releases and CVEs",
      "ArgoCD and GitOps best practices this month",
      "DevOps conference talks and articles",
      "New CI/CD supply chain hardening guidance",
    ],
    prompt:
      "Act as a senior DevOps engineer for Kimbal. Focus on Kubernetes, CI/CD, ArgoCD, Terraform, deployment safety, release validation, rollback procedure, secrets handling, access requests, and infrastructure automation. Prefer synced Confluence DevOps runbooks, Jira DEVO work items, and uploaded deployment docs. Keep responses operational, ordered, and ready for an engineer to execute.",
  },
  {
    id: "developer",
    label: "Dev Space",
    shortLabel: "Dev",
    icon: Wrench,
    description: "Code, APIs, services, databases, implementation plans, and debugging.",
    placeholder: "Ask developer questions about services, APIs, database errors, tickets...",
    radar: [
      "New backend engineering research to read",
      "Postgres debugging articles this week",
      "API design books and long-form guides",
      "Major framework releases and migration notes",
    ],
    prompt:
      "Act as a senior software engineer. Focus on code-level diagnosis, API contracts, database behavior, integration bugs, implementation plans, tests, and production-safe changes. Prefer Jira engineering tickets, design docs, runbooks, and uploaded technical documents. Be precise about assumptions, affected components, reproduction steps, and verification.",
  },
  {
    id: "hr",
    label: "HR Space",
    shortLabel: "HR",
    icon: Users,
    description: "People policy, onboarding, team process, access paths, and internal guidance.",
    placeholder: "Ask HR questions about onboarding, policy, access path, team process...",
    radar: [
      "Remote onboarding practices to compare",
      "Engineering manager books and articles",
      "People ops compliance updates",
      "Developer experience research summaries",
    ],
    prompt:
      "Act as an HR and people-operations assistant for Kimbal. Focus on onboarding, role/process guidance, people policy, access request paths, team communication, and internal operating procedures. Prefer HR policy documents, onboarding docs, and approved internal guidance. Avoid legal, compensation, or private employee claims unless directly supported by sources.",
  },
  {
    id: "custom",
    label: "Custom Role",
    shortLabel: "Custom",
    icon: Sparkles,
    description: "Build a focused role prompt for a team, workflow, or domain.",
    placeholder: "Ask with your custom role prompt...",
    radar: [
      "Latest news for my custom role",
      "Research and articles for this role",
      "Conferences and books for this role",
      "Risks and alerts for this role",
    ],
    prompt:
      "Act according to the user's custom role prompt. Keep source-grounding, security, and citation rules above the custom role.",
  },
];

function statusLabel(state: ChatState) {
  if (state === "preparing") return "Preparing session and source scope";
  if (state === "searching") return "Running hybrid retrieval";
  if (state === "streaming") return "Streaming answer";
  if (state === "done") return "Answer persisted";
  if (state === "error") return "Request failed";
  return "Ready";
}

function sourceTitle(source: RagSource) {
  return source.title ?? source.document_title ?? "Retrieved source";
}

function sourceSnippet(source: RagSource) {
  const raw = source.snippet ?? source.content ?? "Source chunk returned by hybrid search.";
  return cleanSourceSnippet(raw);
}

function cleanSourceSnippet(value: string) {
  const lines = value.replace(/\r\n/g, "\n").split("\n");
  const withoutRenderedTitle = lines.filter((line, index) => {
    const trimmed = line.trim();
    if (index === 0 && trimmed.startsWith("# ")) return false;
    if (/^URL:\s+/i.test(trimmed)) return false;
    return true;
  });
  return withoutRenderedTitle.join(" ").replace(/\s+/g, " ").trim() || value;
}

function sourceScorePercent(score: number) {
  return Math.round(Math.min(Math.max(score, 0), 1) * 100);
}

function answerModeFromModel(model?: string | null): AnswerMode | undefined {
  if (!model) return undefined;
  return model.startsWith("llm-council:") ? "council" : "fast";
}

function modelDisplayName(model?: string | null) {
  if (!model) return "";
  return model.replace(/^llm-council:/, "").replace(/^openrouter\//, "");
}

function sourceModeDescription(mode: SourceMode) {
  if (mode === "knowledge") return "Retrieval uses synced Jira, Confluence, and uploaded documents.";
  if (mode === "web") return "Retrieval uses configured web search and stores citable web snippets locally.";
  return "Retrieval blends internal knowledge with configured web search.";
}

function councilChoicesFromCapabilities(chat: ChatCapabilities | null) {
  if (!chat) return [];
  const choices = chat.council_available_models?.length ? chat.council_available_models : chat.council_models;
  return Array.from(new Set(choices.filter(Boolean)));
}

function preferredLeaderModel(models: string[]) {
  if (!models.length) return "";
  const preferred = ["anthropic/claude-haiku-4.5", "anthropic/claude-sonnet-4.5"];
  return preferred.find((model) => models.includes(model)) ?? models[0];
}

function readStoredCouncilConfig(available: string[]): CouncilConfig | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(COUNCIL_SETTINGS_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<CouncilConfig>;
    const models = Array.from(new Set((parsed.models ?? []).filter((model) => available.includes(model)))).slice(0, 3);
    const chairModel = parsed.chairModel && models.includes(parsed.chairModel) ? parsed.chairModel : models[0];
    return models.length >= 2 && chairModel ? { models, chairModel } : null;
  } catch {
    window.localStorage.removeItem(COUNCIL_SETTINGS_KEY);
    return null;
  }
}

function readStoredCustomRole(): AssistantRoleConfig | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(CUSTOM_ROLE_SETTINGS_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AssistantRoleConfig>;
    if (!parsed.name?.trim() || !parsed.prompt?.trim()) return null;
    return { name: parsed.name.trim().slice(0, 80), prompt: parsed.prompt.trim().slice(0, 1800) };
  } catch {
    window.localStorage.removeItem(CUSTOM_ROLE_SETTINGS_KEY);
    return null;
  }
}

function sourcesFromMessage(message: MessageOut | undefined): RagSource[] {
  if (!message?.citations?.length) return [];
  return message.citations.map((citation) => ({
    chunk_id: citation.chunk_id,
    document_id: citation.document_id,
    title: citation.title ?? citation.document_title ?? `Citation [${citation.marker}]`,
    document_title: citation.document_title ?? citation.title ?? `Citation [${citation.marker}]`,
    marker: citation.marker,
    score: citation.score,
    snippet: citation.snippet,
    source_type: citation.source_type ?? undefined,
    url: citation.url ?? undefined,
  }));
}

function InlineMarkdown({ text, onCitationClick }: { text: string; onCitationClick?: (marker: number) => void }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={`${part}-${index}`} className="font-semibold text-ink-900">
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return (
            <code key={`${part}-${index}`} className="rounded-md bg-brand-50 px-1.5 py-0.5 font-mono text-[12.5px] text-brand-700">
              {part.slice(1, -1)}
            </code>
          );
        }
        if (/^\[\d+\]$/.test(part)) {
          const marker = Number(part.slice(1, -1));
          return (
            <button
              key={`${part}-${index}`}
              type="button"
              onClick={() => onCitationClick?.(marker)}
              className="ml-0.5 cursor-pointer align-super text-[10.5px] font-bold leading-none text-brand-600 underline-offset-2 transition hover:text-brand-700 hover:underline"
              title={`Open source ${part}`}
            >
              {part}
            </button>
          );
        }
        return <span key={`${part}-${index}`}>{part}</span>;
      })}
    </>
  );
}

function MarkdownAnswer({
  content,
  busy,
  onCitationClick,
}: {
  content: string;
  busy: boolean;
  onCitationClick?: (marker: number) => void;
}) {
  const blocks: React.ReactNode[] = [];
  let paragraph: string[] = [];
  let list: Array<{ kind: "ol" | "ul"; text: string }> = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="text-[13.5px] leading-6 text-ink-700">
        <InlineMarkdown text={paragraph.join(" ")} onCitationClick={onCitationClick} />
      </p>
    );
    paragraph = [];
  }

  function flushList() {
    if (!list.length) return;
    const kind = list[0].kind;
    const Tag = kind === "ol" ? "ol" : "ul";
    blocks.push(
      <Tag
        key={`list-${blocks.length}`}
        className={cx(
          "space-y-1.5 pl-4 text-[13.5px] leading-6 text-ink-700",
          kind === "ol" ? "list-decimal" : "list-disc"
        )}
      >
        {list.map((item, index) => (
          <li key={`${item.text}-${index}`} className="pl-1">
            <InlineMarkdown text={item.text} onCitationClick={onCitationClick} />
          </li>
        ))}
      </Tag>
    );
    list = [];
  }

  for (const rawLine of content.replace(/\r\n/g, "\n").split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      continue;
    }

    const markdownHeading = line.match(/^(#{1,4})\s+(.+)$/);
    if (markdownHeading) {
      flushParagraph();
      flushList();
      const level = markdownHeading[1].length;
      const text = markdownHeading[2].replace(/\s+#+$/, "").trim();
      const className =
        level === 1
          ? "text-[17px] font-bold leading-7 text-ink-900"
          : level === 2
            ? "pt-1.5 text-[15px] font-bold leading-6 text-ink-900"
            : "pt-1 text-[14px] font-bold leading-6 text-ink-900";
      blocks.push(
        <h3 key={`h-${blocks.length}`} className={className}>
          <InlineMarkdown text={text} onCitationClick={onCitationClick} />
        </h3>
      );
      continue;
    }

    const boldHeading = line.match(/^\*\*(.+?)\*\*:?\s*$/);
    if (boldHeading) {
      flushParagraph();
      flushList();
      blocks.push(
        <h3 key={`h-${blocks.length}`} className="pt-1 text-[14px] font-bold leading-6 text-ink-900">
          <InlineMarkdown text={boldHeading[1]} onCitationClick={onCitationClick} />
        </h3>
      );
      continue;
    }

    const numbered = line.match(/^\d+\.\s+(.+)$/);
    if (numbered) {
      flushParagraph();
      if (list.length && list[0].kind !== "ol") flushList();
      list.push({ kind: "ol", text: numbered[1] });
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      if (list.length && list[0].kind !== "ul") flushList();
      list.push({ kind: "ul", text: bullet[1] });
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();

  if (!blocks.length) {
    return (
      <p className="text-[13.5px] leading-relaxed text-ink-500">
        Live answer will appear here after retrieval finishes.
      </p>
    );
  }

  return (
    <div className="space-y-2.5">
      {blocks}
      {busy && <span className="inline-block h-4 w-1.5 animate-pulse rounded-full bg-brand-400 align-middle" />}
    </div>
  );
}

export function AskClient() {
  const params = useSearchParams();
  const initialQuestion = params.get("q") ?? "";
  const autoAsked = useRef(false);
  const [input, setInput] = useState(initialQuestion);
  const [state, setState] = useState<ChatState>("idle");
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turn, setTurn] = useState<Turn>({
    question: "",
    answer: "",
    sources: [],
    timings: {},
  });
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [openingConversationId, setOpeningConversationId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<"helpful" | "unhelpful" | "saved" | "shared" | "">("");
  const [actionStatus, setActionStatus] = useState("");
  const [sourceMode, setSourceMode] = useState<SourceMode>("knowledge");
  const [answerMode, setAnswerMode] = useState<AnswerMode>("fast");
  const [webStatus, setWebStatus] = useState<WebSearchStatus | null>(null);
  const [chatCapabilities, setChatCapabilities] = useState<ChatCapabilities | null>(null);
  const [councilModels, setCouncilModels] = useState<string[]>([]);
  const [councilSize, setCouncilSize] = useState<2 | 3>(3);
  const [councilChairModel, setCouncilChairModel] = useState("");
  const [viewMode, setViewMode] = useState<"workbench" | "focus">("focus");
  const [focusRailExpanded, setFocusRailExpanded] = useState(false);
  const [focusDrawer, setFocusDrawer] = useState<"sources" | "history" | "discover" | null>(null);
  const [highlightedMarker, setHighlightedMarker] = useState<number | null>(null);
  const [modePanel, setModePanel] = useState<"web" | "council" | null>(null);
  const [selectedSpaceId, setSelectedSpaceId] = useState<OrgSpaceId>("devops");
  const [customRole, setCustomRole] = useState<AssistantRoleConfig | null>(() => readStoredCustomRole());
  const [customBuilderOpen, setCustomBuilderOpen] = useState(false);
  const [customRoleGenerating, setCustomRoleGenerating] = useState(false);
  const [customRoleName, setCustomRoleName] = useState(() => readStoredCustomRole()?.name ?? "");
  const [customRoleGoal, setCustomRoleGoal] = useState("");
  const [customRoleSourceFocus, setCustomRoleSourceFocus] = useState("");
  const [customRoleOutputStyle, setCustomRoleOutputStyle] = useState("");

  const loadConversations = useCallback(async () => {
    setLoadingConversations(true);
    try {
      await kimbalApi.ensureSession();
      setConversations(await kimbalApi.listConversations());
    } catch {
      setConversations([]);
    } finally {
      setLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadConversations();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadConversations]);

  function applyCouncilDefaults(chat: ChatCapabilities) {
    const available = councilChoicesFromCapabilities(chat);
    if (available.length < 2) {
      setCouncilModels(available);
      setCouncilSize(2);
      setCouncilChairModel(available[0] ?? "");
      return;
    }

    const stored = readStoredCouncilConfig(available);
    const configured = chat.council_models.filter((model) => available.includes(model));
    const preferred = stored?.models.length ? stored.models : configured.length >= 2 ? configured : available;
    const size = Math.min(Math.max(preferred.length, 2), 3) as 2 | 3;
    const models = [...preferred, ...available.filter((model) => !preferred.includes(model))].slice(0, size);
    const chair =
      (stored?.chairModel && models.includes(stored.chairModel) && stored.chairModel) ||
      (chat.council_chair_model && models.includes(chat.council_chair_model) && chat.council_chair_model) ||
      preferredLeaderModel(models);
    setCouncilModels(models);
    setCouncilSize(size);
    setCouncilChairModel(chair ?? models[0]);
  }

  useEffect(() => {
    let cancelled = false;
    async function loadCapabilities() {
      try {
        await kimbalApi.ensureSession();
        const [web, chat] = await Promise.all([kimbalApi.webSearchStatus(), kimbalApi.chatCapabilities()]);
        if (!cancelled) {
          setWebStatus(web);
          setChatCapabilities(chat);
          applyCouncilDefaults(chat);
        }
      } catch {
        if (!cancelled) {
          setWebStatus(null);
          setChatCapabilities(null);
        }
      }
    }
    void loadCapabilities();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    document.body.classList.toggle("ask-focus-mode", viewMode === "focus");
    return () => {
      document.body.classList.remove("ask-focus-mode");
    };
  }, [viewMode]);

  useEffect(() => {
    if (!councilModels.length) return;
    const activeModels = councilModels.slice(0, councilSize).filter(Boolean);
    const uniqueModels = Array.from(new Set(activeModels));
    const nextChairModel =
      councilChairModel && uniqueModels.includes(councilChairModel)
        ? councilChairModel
        : preferredLeaderModel(uniqueModels);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        COUNCIL_SETTINGS_KEY,
        JSON.stringify({ models: uniqueModels, chairModel: nextChairModel })
      );
    }
  }, [councilChairModel, councilModels, councilSize]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || state === "preparing" || state === "searching" || state === "streaming") return;
    if ((sourceMode === "web" || sourceMode === "blended") && webStatus?.configured !== true) {
      setState("error");
      setError(webStatus?.reason ?? "Web search is not configured.");
      return;
    }
    if (answerMode === "council" && chatCapabilities?.council_configured !== true) {
      setState("error");
      setError(chatCapabilities?.council_reason ?? "LLM Council is not configured.");
      return;
    }
    const requestedCouncilModels = Array.from(new Set(councilModels.slice(0, councilSize).filter(Boolean)));
    const availableCouncilModels = councilChoicesFromCapabilities(chatCapabilities);
    const councilConfig: CouncilConfig | undefined =
      answerMode === "council" &&
      requestedCouncilModels.length >= 2 &&
      requestedCouncilModels.length <= 3 &&
      requestedCouncilModels.every((model) => availableCouncilModels.includes(model)) &&
      Boolean(councilChairModel) &&
      requestedCouncilModels.includes(councilChairModel)
        ? { models: requestedCouncilModels, chairModel: councilChairModel }
        : undefined;
    if (answerMode === "council" && !councilConfig) {
      setState("error");
      setError("Select two or three Council models and choose one selected model as chair.");
      setModePanel("council");
      return;
    }
    const requestSpace = ORG_SPACES.find((space) => space.id === selectedSpaceId) ?? ORG_SPACES[0];
    const requestAssistantRole: AssistantRoleConfig =
      requestSpace.id === "custom" && customRole
        ? customRole
        : { name: requestSpace.label, prompt: requestSpace.prompt };
    setState("preparing");
    setError("");
    setFeedback("");
    setActionStatus("");
    setHighlightedMarker(null);
    setTurn({
      question: trimmed,
      answer: "",
      sources: [],
      timings: {},
      sourceMode,
      answerMode,
      assistantRole: requestAssistantRole.name,
    });

    try {
      const kb = await kimbalApi.ensureKnowledgeBase();
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const conversation = await kimbalApi.createConversation(kb.id, trimmed.slice(0, 80));
        activeConversationId = conversation.id;
        setConversationId(conversation.id);
      }
      setState("searching");
      for await (const event of kimbalApi.ask(
        activeConversationId,
        trimmed,
        sourceMode,
        answerMode,
        councilConfig,
        requestAssistantRole
      )) {
        if (event.type === "sources") {
          const sources = event.data.sources ?? event.data.hits ?? [];
          setTurn((current) => ({
            ...current,
            sources,
            sourceMode: event.data.source_mode ?? current.sourceMode,
            answerMode: event.data.answer_mode ?? current.answerMode,
          }));
          setState("streaming");
        }
        if (event.type === "delta") {
          const text = event.data.text ?? event.data.delta ?? event.data.content ?? "";
          setTurn((current) => ({ ...current, answer: current.answer + text }));
          setState("streaming");
        }
        if (event.type === "done") {
          setTurn((current) => ({
            ...current,
            messageId: event.data.message_id,
            timings: event.data.timings_ms ?? current.timings,
            model: event.data.model ?? current.model,
            sourceMode: event.data.source_mode ?? current.sourceMode,
            answerMode: event.data.answer_mode ?? current.answerMode,
          }));
          setState("done");
          void loadConversations();
        }
        if (event.type === "error") {
          throw new Error(event.data.message ?? event.data.code ?? "SSE stream failed");
        }
      }
    } catch (cause) {
      setState("error");
      setError(cause instanceof Error ? cause.message : "Unknown error");
    }
  }

  useEffect(() => {
    if (!initialQuestion.trim()) return;
    if (autoAsked.current) return;
    autoAsked.current = true;
    void ask(initialQuestion);
    // initialQuestion is intentionally captured once per page load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask(input);
  }

  function startNewChat() {
    if (busy) return;
    setConversationId(null);
    setTurn({ question: "", answer: "", sources: [], timings: {} });
    setInput("");
    setError("");
    setFeedback("");
    setHighlightedMarker(null);
    setActionStatus("New chat started");
    setState("idle");
  }

  async function openConversation(conversation: Conversation) {
    if (busy) return;
    setOpeningConversationId(conversation.id);
    setConversationId(conversation.id);
    setState("preparing");
    setError("");
    setFeedback("");
    setActionStatus("");
    try {
      const messages = await kimbalApi.listMessages(conversation.id);
      let assistantIndex = -1;
      for (let index = messages.length - 1; index >= 0; index -= 1) {
        if (messages[index].role === "assistant") {
          assistantIndex = index;
          break;
        }
      }

      const assistantMessage = assistantIndex >= 0 ? messages[assistantIndex] : undefined;
      let userMessage: MessageOut | undefined;
      const startIndex = assistantIndex >= 0 ? assistantIndex - 1 : messages.length - 1;
      for (let index = startIndex; index >= 0; index -= 1) {
        if (messages[index].role === "user") {
          userMessage = messages[index];
          break;
        }
      }

      setTurn({
        question: userMessage?.content ?? conversation.title,
        answer: assistantMessage?.content ?? "",
        sources: sourcesFromMessage(assistantMessage),
        timings: assistantMessage?.timings ?? {},
        answerMode: answerModeFromModel(assistantMessage?.model),
        model: assistantMessage?.model ?? null,
        messageId: assistantMessage?.id,
      });
      setInput("");
      setState(assistantMessage ? "done" : "idle");
      setActionStatus("Conversation opened");
    } catch (cause) {
      setState("error");
      setError(cause instanceof Error ? cause.message : "Failed to open conversation");
    } finally {
      setOpeningConversationId(null);
    }
  }

  async function rate(rating: 1 | -1) {
    if (!turn.messageId) {
      setActionStatus("Feedback is available after the answer is persisted.");
      return;
    }
    try {
      await kimbalApi.submitFeedback(turn.messageId, rating);
      setFeedback(rating === 1 ? "helpful" : "unhelpful");
      setActionStatus(rating === 1 ? "Marked helpful" : "Marked not helpful");
    } catch (cause) {
      setActionStatus(cause instanceof Error ? cause.message : "Feedback failed");
    }
  }

  function saveAnswer() {
    if (!turn.answer) {
      setActionStatus("There is no answer to save yet.");
      return;
    }
    const raw = window.localStorage.getItem("kimbal.saved.answers.v1");
    let saved: unknown[] = [];
    try {
      const parsed = raw ? JSON.parse(raw) : [];
      saved = Array.isArray(parsed) ? parsed : [];
    } catch {
      saved = [];
    }
    const id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now());
    window.localStorage.setItem(
      "kimbal.saved.answers.v1",
      JSON.stringify([{ id, ...turn, savedAt: new Date().toISOString() }, ...saved].slice(0, 20))
    );
    setFeedback("saved");
    setActionStatus("Saved to Saved Answers");
  }

  async function shareAnswer() {
    if (!turn.answer) {
      setActionStatus("There is no answer to share yet.");
      return;
    }
    const text = `${turn.question}\n\n${turn.answer}`;
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(text);
      } else if (navigator.share) {
        await navigator.share({ title: "Kimbal answer", text });
      } else {
        throw new Error("Clipboard sharing is not available in this browser");
      }
      setFeedback("shared");
      setActionStatus("Share text copied");
    } catch (cause) {
      setActionStatus(cause instanceof Error ? cause.message : "Share failed");
    }
  }

  const busy = state === "preparing" || state === "searching" || state === "streaming";
  const hasAnswer = Boolean(turn.answer);
  const webReady = webStatus?.configured === true;
  const councilAvailableModels = councilChoicesFromCapabilities(chatCapabilities);
  const activeCouncilModels = councilModels.slice(0, councilSize).filter(Boolean);
  const uniqueCouncilModels = Array.from(new Set(activeCouncilModels));
  const councilReady = chatCapabilities?.council_configured === true && councilAvailableModels.length >= 2;
  const sourceModeText = sourceModeDescription(sourceMode);
  const answerSourceModeText = sourceModeDescription(turn.sourceMode ?? sourceMode);
  const selectedSpace = ORG_SPACES.find((space) => space.id === selectedSpaceId) ?? ORG_SPACES[0];
  const assistantRoleConfig: AssistantRoleConfig =
    selectedSpace.id === "custom" && customRole
      ? customRole
      : { name: selectedSpace.label, prompt: selectedSpace.prompt };
  const activePlaceholder = selectedSpace.placeholder;
  const roleModeText =
    selectedSpace.id === "custom" && !customRole
      ? "Custom role is not generated yet."
      : `${assistantRoleConfig.name} active`;

  function chooseOrgSpace(space: OrgSpace) {
    setSelectedSpaceId(space.id);
    setActionStatus(`${space.label} selected`);
    if (space.id === "custom" && !customRole) {
      setCustomBuilderOpen(true);
      return;
    }
    if (webReady) {
      setSourceMode("blended");
    }
  }

  function runRadarSearch(query: string) {
    setInput(query);
    if (webReady) {
      setSourceMode("blended");
      setActionStatus("Radar uses internal knowledge plus web search.");
    } else {
      setSourceMode("knowledge");
      setActionStatus(webStatus?.reason ?? "Web search is not configured; using internal knowledge only.");
    }
  }

  async function generateCustomRole() {
    const name = customRoleName.trim() || "Custom Specialist";
    const goal = customRoleGoal.trim();
    if (!goal) {
      setActionStatus("Describe what the custom role should optimize for.");
      return;
    }
    setCustomRoleGenerating(true);
    setActionStatus("Generating role prompt with the configured LLM");
    try {
      const generated = await kimbalApi.generateRolePrompt({
        name,
        goal,
        sourceFocus: customRoleSourceFocus,
        outputStyle: customRoleOutputStyle,
      });
      setCustomRole(generated);
      setCustomRoleName(generated.name);
      setSelectedSpaceId("custom");
      setCustomBuilderOpen(false);
      window.localStorage.setItem(CUSTOM_ROLE_SETTINGS_KEY, JSON.stringify(generated));
      setActionStatus(`Custom role generated: ${generated.name}`);
    } catch (cause) {
      setActionStatus(cause instanceof Error ? cause.message : "Role generation failed");
    } finally {
      setCustomRoleGenerating(false);
    }
  }

  function chooseSourceMode(next: SourceMode) {
    if ((next === "web" || next === "blended") && !webReady) {
      setModePanel("web");
      setActionStatus(webStatus?.reason ?? "Web search is not configured.");
      return;
    }
    setSourceMode(next);
    setModePanel(null);
    setActionStatus("");
  }

  function openCitationReference(marker: number) {
    setHighlightedMarker(marker);
    if (viewMode === "focus") {
      setFocusDrawer("sources");
    }
    const source = turn.sources.find((item) => item.marker === marker);
    setActionStatus(source ? `Reference [${marker}] selected` : `Reference [${marker}] was not returned in the source list`);
  }

  function chooseAnswerMode(next: AnswerMode) {
    if (next === "council" && !councilReady) {
      setModePanel("council");
      setActionStatus(chatCapabilities?.council_reason ?? "LLM Council is not configured.");
      return;
    }
    setAnswerMode(next);
    setModePanel(next === "council" ? "council" : null);
    setActionStatus("");
  }

  function setCouncilModel(index: number, value: string) {
    const next = [...councilModels];
    next[index] = value;
    const selected = Array.from(new Set(next.slice(0, councilSize).filter(Boolean)));
    setCouncilModels(next);
    if (selected.length && (!councilChairModel || !selected.includes(councilChairModel))) {
      setCouncilChairModel(preferredLeaderModel(selected));
    }
  }

  function setCouncilModelCount(size: 2 | 3) {
    const fallback = councilAvailableModels.filter((model) => !councilModels.includes(model));
    const next = [...councilModels, ...fallback].slice(0, size);
    const selected = Array.from(new Set(next.filter(Boolean)));
    setCouncilSize(size);
    setCouncilModels(next);
    if (selected.length && (!councilChairModel || !selected.includes(councilChairModel))) {
      setCouncilChairModel(preferredLeaderModel(selected));
    }
  }

  function renderModeControls(compact = false) {
    return (
      <div className={cx("flex flex-wrap items-center gap-2", compact && "justify-center")}>
        <div className="inline-flex rounded-[12px] border border-line bg-white p-1 shadow-[var(--shadow-card)]">
          {SOURCE_MODES.map((mode) => {
            const Icon = mode.icon;
            const unavailable = (mode.value === "web" || mode.value === "blended") && !webReady;
            return (
              <button
                key={mode.value}
                type="button"
                disabled={busy}
                aria-pressed={sourceMode === mode.value}
                title={unavailable ? (webStatus?.reason ?? "Web search is not configured.") : mode.label}
                onClick={() => chooseSourceMode(mode.value)}
                className={cx(
                  "inline-flex h-8 items-center gap-1.5 rounded-[9px] px-2.5 text-[12px] font-semibold transition",
                  sourceMode === mode.value ? "bg-brand-500 text-white" : "text-ink-500 hover:bg-canvas hover:text-ink-900",
                  unavailable && "opacity-55"
                )}
              >
                <Icon size={13} />
                {mode.label}
              </button>
            );
          })}
        </div>

        <div className="inline-flex rounded-[12px] border border-line bg-white p-1 shadow-[var(--shadow-card)]">
          {ANSWER_MODES.map((mode) => {
            const Icon = mode.icon;
            const unavailable = mode.value === "council" && !councilReady;
            const title =
              unavailable
                ? (chatCapabilities?.council_reason ?? "LLM Council is not configured.")
                : mode.value === "council"
                  ? `Council mode: choose ${councilReady ? "2-3" : "available"} models and one chair`
                  : mode.label;
            return (
              <button
                key={mode.value}
                type="button"
                disabled={busy}
                aria-pressed={answerMode === mode.value}
                title={title}
                onClick={() => chooseAnswerMode(mode.value)}
                className={cx(
                  "inline-flex h-8 items-center gap-1.5 rounded-[9px] px-2.5 text-[12px] font-semibold transition",
                  answerMode === mode.value ? "bg-ink-900 text-white" : "text-ink-500 hover:bg-canvas hover:text-ink-900",
                  unavailable && "opacity-55"
                )}
              >
                <Icon size={13} />
                {mode.label}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  function renderModePanel() {
    if (!modePanel) return null;
    const isWeb = modePanel === "web";
    const councilText =
      councilReady && uniqueCouncilModels.length > 1
        ? `Ready with ${uniqueCouncilModels.join(", ")}. Chair: ${councilChairModel || uniqueCouncilModels[0]}.`
        : councilReady
          ? "Select two or three models below."
          : (chatCapabilities?.council_reason ?? "LLM Council is not configured.");
    return (
      <div className="mt-3 rounded-[14px] border border-line bg-white px-4 py-3 text-[12.5px] shadow-[var(--shadow-card)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-bold text-ink-900">{isWeb ? "Web search" : "LLM Council"}</p>
            <p className="mt-1 leading-5 text-ink-500">
              {isWeb
                ? webReady
                  ? `Ready through ${webStatus?.provider ?? "web search"}.`
                  : (webStatus?.reason ?? "Web search is not configured.")
                : councilText}
            </p>
            {!isWeb && councilReady && (
              <div className="mt-3 space-y-3">
                <div className="inline-flex rounded-[10px] border border-line bg-canvas p-1">
                  {[2, 3].map((size) => {
                    const unavailable = councilAvailableModels.length < size;
                    return (
                      <button
                        key={size}
                        type="button"
                        disabled={unavailable}
	                        onClick={() => setCouncilModelCount(size as 2 | 3)}
                        className={cx(
                          "rounded-[8px] px-2.5 py-1 text-[12px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-45",
                          councilSize === size ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500"
                        )}
                      >
                        {size} models
                      </button>
                    );
                  })}
                </div>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                  {Array.from({ length: councilSize }).map((_, index) => (
                    <label key={index} className="block">
                      <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">
                        Member {index + 1}
                      </span>
                      <select
                        value={councilModels[index] ?? ""}
                        onChange={(event) => setCouncilModel(index, event.target.value)}
                        className="h-9 w-full rounded-[10px] border border-line bg-white px-2 text-[12px] font-semibold text-ink-700 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
                      >
                        {councilAvailableModels.map((model) => (
                          <option
                            key={model}
                            value={model}
                            disabled={activeCouncilModels.some((selected, selectedIndex) => selected === model && selectedIndex !== index)}
                          >
                            {model}
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
                <label className="block max-w-sm">
                  <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">
                    Chair model
                  </span>
                  <select
                    value={councilChairModel}
                    onChange={(event) => setCouncilChairModel(event.target.value)}
                    className="h-9 w-full rounded-[10px] border border-line bg-white px-2 text-[12px] font-semibold text-ink-700 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
                  >
                    {uniqueCouncilModels.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setModePanel(null)}
            className="text-ink-400 transition hover:text-ink-900"
            aria-label="Close mode details"
          >
            <Minimize2 size={15} />
          </button>
        </div>
      </div>
    );
  }

  function renderActionButtons(compact = false) {
    return (
      <div className={cx("flex flex-wrap items-center gap-2 border-t border-line", compact ? "pt-3" : "pt-4")}>
        <button
          type="button"
          onClick={() => void rate(1)}
          className={cx(actionClass, feedback === "helpful" && "border-emerald-200 bg-emerald-50 text-emerald-600")}
        >
          <ThumbsUp size={14} />
          Helpful
        </button>
        <button
          type="button"
          onClick={() => void rate(-1)}
          className={cx(actionClass, feedback === "unhelpful" && "border-rose-200 bg-rose-50 text-rose-600")}
        >
          <ThumbsDown size={14} />
          Not Helpful
        </button>
        <button
          type="button"
          disabled={!hasAnswer}
          onClick={saveAnswer}
          className={cx(actionClass, feedback === "saved" && "border-brand-200 bg-brand-50 text-brand-600")}
        >
          <Bookmark size={14} />
          Save
        </button>
        <button
          type="button"
          disabled={!hasAnswer}
          onClick={() => void shareAnswer()}
          className={cx(actionClass, feedback === "shared" && "border-sky-200 bg-sky-50 text-sky-600")}
        >
          <Share2 size={14} />
          Share
        </button>
        {actionStatus && <span className="ml-auto text-[11.5px] font-semibold text-ink-500">{actionStatus}</span>}
      </div>
    );
  }

  function renderSourcesList(limit = 6) {
    return (
      <ul className="mt-3 space-y-3">
        {turn.sources.slice(0, limit).map((source, index) => {
          const isWeb = source.source_type === "web";
          const SourceIcon = isWeb ? Globe : FileText;
          const marker = source.marker ?? index + 1;
          const highlighted = highlightedMarker === marker;
          return (
            <li
              key={`${source.chunk_id}-${index}`}
              className={cx(
                "rounded-[12px] border p-3 transition",
                highlighted ? "border-brand-300 bg-brand-50 shadow-[var(--shadow-card)]" : "border-line bg-white"
              )}
            >
              <div className="flex items-start gap-2.5">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] border border-line bg-white text-brand-500">
                <SourceIcon size={14} />
              </span>
              <div className="min-w-0 flex-1">
                {source.url ? (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-[12.5px] font-semibold text-ink-900 hover:text-brand-600"
                  >
                    [{marker}] {sourceTitle(source)}
                  </a>
                ) : (
                  <p className="truncate text-[12.5px] font-semibold text-ink-900">
                    [{marker}] {sourceTitle(source)}
                  </p>
                )}
                <p className="line-clamp-2 text-[11px] leading-4 text-ink-500">{sourceSnippet(source)}</p>
              </div>
              {typeof source.score === "number" && (
                <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-bold text-emerald-600">
                  {sourceScorePercent(source.score)}%
                </span>
              )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 pl-9">
                <button
                  type="button"
                  onClick={() => openCitationReference(marker)}
                  className="text-[11px] font-bold text-brand-600 transition hover:text-brand-700"
                >
                  Highlight citation [{marker}]
                </button>
                {source.url && (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] font-bold text-ink-500 transition hover:text-ink-900"
                  >
                    Open source
                  </a>
                )}
              </div>
            </li>
          );
        })}
        {!turn.sources.length && (
          <li className="rounded-[12px] bg-canvas px-4 py-3 text-[12.5px] text-ink-500">
            Sources appear after retrieval.
          </li>
        )}
      </ul>
    );
  }

  function renderHistoryList() {
    return (
      <ul className="mt-2 divide-y divide-line">
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            <button
              type="button"
              disabled={busy || openingConversationId === conversation.id}
              onClick={() => void openConversation(conversation)}
              className={cx(
                "w-full py-2.5 text-left transition hover:text-brand-600 disabled:cursor-wait disabled:opacity-60",
                conversation.id === conversationId ? "text-brand-600" : "text-ink-700"
              )}
            >
              <span className="line-clamp-2 text-[13px] font-semibold">{conversation.title}</span>
              <span className="mt-1 block text-[11.5px] font-medium text-ink-400">
                {new Date(conversation.updated_at).toLocaleString()}
              </span>
            </button>
          </li>
        ))}
        {loadingConversations && (
          <li className="flex items-center gap-2 py-2.5 text-[12.5px] text-ink-500">
            <Loader2 size={13} className="animate-spin" />
            Loading conversation history
          </li>
        )}
        {!loadingConversations && !conversations.length && (
          <li className="py-2.5 text-[12.5px] text-ink-500">No previous conversations yet.</li>
        )}
      </ul>
    );
  }

  function renderSpaceTabs(compact = false) {
    return (
      <div className={cx("flex flex-wrap items-center justify-center gap-2", compact ? "max-w-[820px]" : "")}>
        {ORG_SPACES.map((space) => {
          const Icon = space.icon;
          const selected = selectedSpaceId === space.id;
          return (
            <button
              key={space.id}
              type="button"
              onClick={() => chooseOrgSpace(space)}
              className={cx(
                "inline-flex items-center gap-2 rounded-full px-3 py-2 text-[13px] font-semibold transition",
                selected
                  ? "bg-ink-900 text-white shadow-[var(--shadow-card)]"
                  : "text-ink-500 hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]"
              )}
              title={space.description}
            >
              <Icon size={14} />
              {space.label}
            </button>
          );
        })}
      </div>
    );
  }

  function renderRadarChips() {
    return (
      <div className="mt-4 flex max-w-[820px] flex-wrap justify-center gap-2">
        {selectedSpace.radar.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => runRadarSearch(`${item} for ${selectedSpace.shortLabel} teams`)}
            className="rounded-full border border-[#e8e5dc] bg-white px-3 py-1.5 text-[12px] font-semibold text-ink-500 shadow-[var(--shadow-card)] transition hover:border-ink-200 hover:text-ink-900"
          >
            {item}
          </button>
        ))}
      </div>
    );
  }

  function renderCustomRoleBuilder() {
    if (!customBuilderOpen) return null;
    return (
      <div className="mt-3 w-full rounded-[16px] border border-line bg-white p-4 text-left shadow-[var(--shadow-card)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[14px] font-bold text-ink-900">Custom role builder</p>
            <p className="mt-1 text-[12.5px] leading-5 text-ink-500">
              Answer these prompts once. Kimbal uses the configured LLM to generate a reusable background role prompt.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setCustomBuilderOpen(false)}
            className="rounded-full p-1.5 text-ink-400 transition hover:bg-canvas hover:text-ink-900"
            aria-label="Close custom role builder"
          >
            <Minimize2 size={15} />
          </button>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Role name</span>
            <input
              value={customRoleName}
              onChange={(event) => setCustomRoleName(event.target.value)}
              placeholder="Security Architect, SRE Lead, HR Ops Partner"
              className="h-9 w-full rounded-[10px] border border-line bg-white px-3 text-[12.5px] font-semibold text-ink-700 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Source focus</span>
            <input
              value={customRoleSourceFocus}
              onChange={(event) => setCustomRoleSourceFocus(event.target.value)}
              placeholder="security Jira, zero-day advisories, architecture docs"
              className="h-9 w-full rounded-[10px] border border-line bg-white px-3 text-[12.5px] font-semibold text-ink-700 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">What should this role optimize for?</span>
            <textarea
              value={customRoleGoal}
              onChange={(event) => setCustomRoleGoal(event.target.value)}
              placeholder="Help security engineers assess risk, explain impact, and produce prioritized remediation steps."
              className="min-h-[74px] w-full resize-none rounded-[10px] border border-line bg-white px-3 py-2 text-[12.5px] font-medium leading-5 text-ink-700 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
            />
          </label>
          <label className="block md:col-span-2">
            <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.08em] text-ink-400">Output style</span>
            <input
              value={customRoleOutputStyle}
              onChange={(event) => setCustomRoleOutputStyle(event.target.value)}
              placeholder="Brief risk summary, evidence, remediation plan, owner questions"
              className="h-9 w-full rounded-[10px] border border-line bg-white px-3 text-[12.5px] font-semibold text-ink-700 outline-none transition focus:border-brand-300 focus:ring-4 focus:ring-brand-50"
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11.5px] font-medium text-ink-400">Stored in this browser and sent with Ask requests.</p>
          <button
            type="button"
            disabled={customRoleGenerating}
            onClick={() => void generateCustomRole()}
            className="inline-flex items-center gap-2 rounded-[10px] bg-ink-900 px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:bg-ink-800 disabled:cursor-wait disabled:opacity-60"
          >
            {customRoleGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {customRoleGenerating ? "Generating" : "Generate role"}
          </button>
        </div>
      </div>
    );
  }

  function renderRunBadge() {
    const mode = turn.answerMode ?? answerModeFromModel(turn.model);
    if (!mode && !turn.model) return null;
    const model = modelDisplayName(turn.model);
    return (
      <span
        className={cx(
          "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold",
          mode === "council" ? "bg-ink-900 text-white" : "bg-brand-50 text-brand-600"
        )}
      >
        {mode === "council" ? "Council" : "Fast"}
        {model && <span className="max-w-[220px] truncate opacity-80">- {model}</span>}
      </span>
    );
  }

  function renderRoleBadge() {
    const name = turn.assistantRole ?? assistantRoleConfig.name;
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-[#f3f1ea] px-2 py-0.5 text-[11px] font-semibold text-ink-600">
        <Sparkles size={11} />
        {name}
      </span>
    );
  }

  if (viewMode === "focus") {
    const focusRailWidth = focusRailExpanded ? 248 : 72;
    const focusRightRailWidth = focusDrawer ? 400 : 0;
    return (
      <div className="min-h-screen bg-[#f8f8f6] text-ink-900">
        <aside
          className={cx(
            "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-[#ecebe6] bg-white/70 py-5 backdrop-blur-xl transition-[width]",
            focusRailExpanded ? "w-[248px] px-4" : "w-[68px] items-center"
          )}
        >
          <Link
            href="/"
            className={cx(
              "flex h-9 items-center gap-2 rounded-full text-ink-900",
              focusRailExpanded ? "w-full px-2 text-[15px] font-bold" : "w-9 justify-center bg-ink-900 text-white"
            )}
            aria-label="Home"
          >
            <Sparkles size={16} />
            {focusRailExpanded && "kimbal"}
          </Link>
          <div className={cx("mt-8 flex flex-col gap-3", focusRailExpanded && "w-full")}>
            <button
              type="button"
              onClick={startNewChat}
              disabled={busy}
              title="New chat"
              className={cx(
                "flex h-10 items-center gap-3 rounded-full text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)] disabled:opacity-50",
                focusRailExpanded ? "w-full px-3 text-[13px] font-semibold" : "w-10 justify-center"
              )}
            >
              <MessageSquarePlus size={18} />
              {focusRailExpanded && "New"}
            </button>
            <button
              type="button"
              onClick={() => setFocusDrawer(focusDrawer === "history" ? null : "history")}
              title="Past chats"
              className={cx(
                "flex h-10 items-center gap-3 rounded-full transition hover:bg-white hover:shadow-[var(--shadow-card)]",
                focusRailExpanded ? "w-full px-3 text-[13px] font-semibold" : "w-10 justify-center",
                focusDrawer === "history" ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500"
              )}
            >
              <Clock size={18} />
              {focusRailExpanded && "History"}
            </button>
            <button
              type="button"
              onClick={() => setFocusDrawer(focusDrawer === "sources" ? null : "sources")}
              title="Sources"
              className={cx(
                "flex h-10 items-center gap-3 rounded-full transition hover:bg-white hover:shadow-[var(--shadow-card)]",
                focusRailExpanded ? "w-full px-3 text-[13px] font-semibold" : "w-10 justify-center",
                focusDrawer === "sources" ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500"
              )}
            >
              <BookOpen size={18} />
              {focusRailExpanded && "Sources"}
            </button>
            <button
              type="button"
              onClick={() => setFocusDrawer(focusDrawer === "discover" ? null : "discover")}
              title="Discover"
              className={cx(
                "flex h-10 items-center gap-3 rounded-full transition hover:bg-white hover:shadow-[var(--shadow-card)]",
                focusRailExpanded ? "w-full px-3 text-[13px] font-semibold" : "w-10 justify-center",
                focusDrawer === "discover" ? "bg-white text-ink-900 shadow-[var(--shadow-card)]" : "text-ink-500"
              )}
            >
              <Newspaper size={18} />
              {focusRailExpanded && "Discover"}
            </button>
          </div>
          {focusRailExpanded && (
            <div className="mt-8 w-full space-y-3 text-[12.5px] font-semibold text-ink-500">
              <p>Connectors</p>
              <p>Skills</p>
              <p>Workflows</p>
            </div>
          )}
          <button
            type="button"
            onClick={() => setFocusRailExpanded((value) => !value)}
            title={focusRailExpanded ? "Collapse rail" : "Expand rail"}
            className={cx(
              "mt-auto flex h-10 items-center gap-3 rounded-full text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]",
              focusRailExpanded ? "w-full px-3 text-[13px] font-semibold" : "w-10 justify-center"
            )}
          >
            {focusRailExpanded ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            {focusRailExpanded && "Collapse"}
          </button>
          <button
            type="button"
            onClick={() => setViewMode("workbench")}
            title="Workbench view"
            className={cx(
              "mt-3 flex h-10 items-center gap-3 rounded-full text-ink-500 transition hover:bg-white hover:text-ink-900 hover:shadow-[var(--shadow-card)]",
              focusRailExpanded ? "w-full px-3 text-[13px] font-semibold" : "w-10 justify-center"
            )}
          >
            <PanelRight size={18} />
            {focusRailExpanded && "Workbench"}
          </button>
          <span className={cx("mt-4 flex h-9 items-center justify-center rounded-full bg-brand-500 text-[12px] font-bold text-white", focusRailExpanded ? "w-full" : "w-9")}>
            SK
          </span>
        </aside>

        <main
          className="min-h-screen transition-[padding]"
          style={{ paddingLeft: focusRailWidth, paddingRight: focusRightRailWidth }}
        >
          <div className="flex items-center justify-between px-8 py-5">
            <div className="flex items-center gap-3">
              <Link href="/" className="text-ink-400 transition hover:text-ink-900" aria-label="Back to home">
                <ArrowLeft size={18} />
              </Link>
              <p className="text-[14px] font-semibold text-ink-700">{selectedSpace.label}</p>
            </div>
            {!turn.question && (
              <div className="hidden md:block">{renderSpaceTabs(true)}</div>
            )}
            <div className="flex items-center gap-2">
              <span
                className={cx(
                  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-semibold",
                  state === "error"
                    ? "border-rose-100 bg-rose-50 text-rose-600"
                    : "border-[#ebe8dd] bg-white text-ink-500"
                )}
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                {statusLabel(state)}
              </span>
              <button
                type="button"
                onClick={() => setViewMode("workbench")}
                className="flex h-9 w-9 items-center justify-center rounded-full border border-[#e8e5dc] bg-white text-ink-500 shadow-[var(--shadow-card)] transition hover:text-ink-900"
                aria-label="Switch to workbench view"
              >
                <PanelRight size={16} />
              </button>
            </div>
          </div>

          <section className="mx-auto flex min-h-[calc(100vh-86px)] max-w-[920px] flex-col items-center justify-center px-6 pb-12">
            {!turn.question && (
              <div className="mb-8 flex flex-col items-center">
                <h2 className="text-[54px] font-semibold tracking-[-0.04em] text-ink-900">kimbal</h2>
              </div>
            )}

            {turn.question && (
              <div className="mb-5 w-full space-y-3">
                <div className="flex justify-end">
                  <div className="max-w-[680px] rounded-[16px] rounded-tr-[5px] bg-ink-900 px-4 py-2.5 text-[13.5px] font-medium leading-6 text-white shadow-[var(--shadow-pop)]">
                    {turn.question}
                  </div>
                </div>
                <Card className="p-5">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className="flex h-7 w-7 items-center justify-center rounded-[9px] bg-brand-50 text-brand-500">
                      <Sparkles size={14} />
                    </span>
                    <p className="text-[14px] font-semibold text-ink-900">Kimbal AI</p>
                    {renderRoleBadge()}
                    {renderRunBadge()}
                  </div>
                  {error ? (
                    <div className="mt-4 rounded-[12px] border border-rose-100 bg-rose-50 px-4 py-3 text-[13px] text-rose-700">
                      {error}
                    </div>
                  ) : (
                    <div className="mt-4">
                      <MarkdownAnswer
                        content={hasAnswer ? turn.answer : ""}
                        busy={busy}
                        onCitationClick={openCitationReference}
                      />
                    </div>
                  )}
                  <div className="mt-4">{renderActionButtons(true)}</div>
                </Card>
              </div>
            )}

            <form
              onSubmit={submit}
              className="w-full rounded-[18px] border border-[#e8e5dc] bg-white p-3 shadow-[0_18px_60px_-38px_rgba(23,26,44,0.55)] transition focus-within:border-ink-300"
            >
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder={activePlaceholder}
                className="h-12 w-full bg-transparent px-3 text-[15px] outline-none placeholder:text-ink-400"
              />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-3 border-t border-[#f0eee8] pt-3">
                {renderModeControls(true)}
                <button
                  type="submit"
                  disabled={busy}
                  aria-label="Send"
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-[#e5dcc0] text-white shadow-[var(--shadow-card)] transition hover:bg-brand-500 disabled:opacity-60"
                >
                  {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                </button>
              </div>
              {renderModePanel()}
            </form>
            {renderCustomRoleBuilder()}
            {!turn.question && (
              renderRadarChips()
            )}
            <p className="mt-4 text-[12px] font-semibold text-ink-400">
              Kimbal can make mistakes. Please verify.
            </p>
          </section>
        </main>

        {focusDrawer && (
          <aside className="fixed inset-y-0 right-0 z-40 w-[400px] overflow-y-auto border-l border-line bg-white p-6 shadow-[0_20px_70px_-42px_rgba(23,26,44,0.45)]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[17px] font-bold text-ink-900">
                  {focusDrawer === "sources" ? "Sources" : focusDrawer === "discover" ? "Discover" : "Past Chats"}
                </p>
                <p className="mt-1 text-[12.5px] text-ink-500">
                  {focusDrawer === "sources"
                    ? "Current answer evidence and web links."
                    : focusDrawer === "discover"
                      ? "Live department updates and alerts."
                      : "Backend conversation history."}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setFocusDrawer(null)}
                className="rounded-full p-2 text-ink-400 transition hover:bg-canvas hover:text-ink-900"
                aria-label="Close drawer"
              >
                <Minimize2 size={17} />
              </button>
            </div>
            {focusDrawer === "sources" ? renderSourcesList(12) : focusDrawer === "discover" ? <div className="mt-5"><DiscoverClient surface="ask" /></div> : renderHistoryList()}
          </aside>
        )}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className="col-span-8 animate-rise">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-ink-500 transition hover:text-brand-600" aria-label="Back to home">
            <ArrowLeft size={18} />
          </Link>
          <h1 className="text-[17px] font-bold text-ink-900">
            Ask Kimbal <span className="font-normal text-ink-500">({selectedSpace.label})</span>
          </h1>
          <div className="ml-auto flex items-center gap-2">
            <GhostButton className="px-3 py-2 text-[12.5px]" disabled={busy} onClick={startNewChat}>
              <MessageSquarePlus size={14} />
              New Chat
            </GhostButton>
            <GhostButton className="px-3 py-2 text-[12.5px]" onClick={() => setViewMode("focus")}>
              <Maximize2 size={14} />
              Focus
            </GhostButton>
            <span
              className={cx(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] font-semibold",
                state === "error"
                  ? "border-rose-100 bg-rose-50 text-rose-600"
                  : "border-brand-100 bg-brand-50 text-brand-600"
              )}
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              {statusLabel(state)}
            </span>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          {renderSpaceTabs()}
          <p className="text-[12.5px] font-medium text-ink-500">{roleModeText}</p>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          {renderModeControls()}
          <p className="text-[12.5px] font-medium text-ink-500">{sourceModeText}</p>
        </div>
        {renderModePanel()}
        {renderCustomRoleBuilder()}

        {turn.question && (
          <div className="mt-4 flex items-start justify-end gap-3">
            <div>
              <div className="rounded-[15px] rounded-tr-[4px] bg-gradient-to-r from-brand-500 to-brand-600 px-4 py-2.5 text-[13.5px] font-medium leading-6 text-white shadow-[var(--shadow-pop)]">
                {turn.question}
              </div>
              <p className="mt-1.5 text-right text-[11.5px] text-ink-400">Now</p>
            </div>
            <span className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-brand-50 text-brand-400">
              <User size={16} />
            </span>
          </div>
        )}

        {(turn.question || error || busy) && (
          <Card className="mt-2 p-5">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-[9px] bg-brand-50 text-brand-500">
                <Sparkles size={14} />
              </span>
              <p className="text-[14px] font-semibold text-ink-900">Kimbal AI</p>
              {renderRoleBadge()}
              {renderRunBadge()}
            </div>

            {error ? (
              <div className="mt-4 rounded-[12px] border border-rose-100 bg-rose-50 px-4 py-3 text-[13px] text-rose-700">
                {error}
              </div>
            ) : (
              <div className="mt-4">
                <MarkdownAnswer
                  content={hasAnswer ? turn.answer : ""}
                  busy={busy}
                  onCitationClick={openCitationReference}
                />
              </div>
            )}

            <div className="mt-4 flex items-start gap-2 rounded-[10px] border border-brand-100 bg-brand-50/60 px-3 py-2.5">
              <Info size={14} className="mt-0.5 shrink-0 text-brand-500" />
              <p className="text-[12.5px] leading-5 text-ink-700">
                {answerSourceModeText} Citation markers such as <span className="font-semibold text-brand-600">[1]</span> map to the source chunks in the right rail.
              </p>
            </div>

            <div className="mt-4">{renderActionButtons(true)}</div>
          </Card>
        )}

        <form
          onSubmit={submit}
          className="mt-5 flex items-center gap-2 rounded-[16px] border border-line bg-white py-1.5 pl-5 pr-1.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50"
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={activePlaceholder}
            className="h-10 min-w-0 flex-1 bg-transparent text-[14px] outline-none placeholder:text-ink-400"
          />
          <button
            type="submit"
            disabled={busy}
            aria-label="Send"
            className="flex h-10 w-10 items-center justify-center rounded-full bg-brand-500 text-white shadow-[0_4px_14px_-4px_rgba(91,92,235,0.6)] transition hover:bg-brand-600 disabled:opacity-60"
          >
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </form>
        {!turn.question && renderRadarChips()}
      </div>

      <div className="col-span-4 space-y-5 animate-rise-1">
        <DiscoverClient surface="ask" />

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <p className="flex items-center gap-2 text-[15px] font-bold text-ink-900">
              Sources
              <span className="rounded-md bg-canvas px-1.5 py-0.5 text-[11.5px] font-semibold text-ink-500">
                {turn.sources.length}
              </span>
            </p>
            <CardLink href="/knowledge-sources">View all</CardLink>
          </div>
          {renderSourcesList()}
        </Card>

        <Card className="p-5">
          <p className="text-[15px] font-bold text-ink-900">Previous Conversations</p>
          {renderHistoryList()}
          <div className="mt-2 flex items-center gap-1.5 text-[11.5px] text-ink-400">
            <Clock size={12} />
            Stored in the backend conversation history
          </div>
        </Card>
      </div>
    </div>
  );
}

const actionClass =
  "inline-flex items-center gap-2 rounded-[10px] border border-line bg-white px-3.5 py-2 text-[12.5px] font-semibold text-ink-700 transition hover:border-brand-200 hover:text-brand-600 disabled:cursor-not-allowed disabled:opacity-50";
