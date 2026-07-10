"use client";

import {
  type ChangeEvent,
  type ClipboardEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  ExternalLink,
  FileText,
  Globe2,
  Image as ImageIcon,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  MessageSquarePlus,
  PanelRightClose,
  Paperclip,
  Search,
  Settings2,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Users,
  X,
  Zap,
} from "lucide-react";
import { CVUMMark } from "@/components/brand-icons";
import { cx } from "@/components/ui";
import {
  kimbalApi,
  type AnswerMode,
  type AssistantRoleConfig,
  type ChatCapabilities,
  type Conversation,
  type CouncilConfig,
  type MessageOut,
  type RagSource,
  type SourceMode,
  type UserOut,
  type WebSearchStatus,
} from "@/lib/kimbal-api";

type ChatPhase = "idle" | "uploading" | "searching" | "answering";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: RagSource[];
  model?: string | null;
  messageId?: string;
  pending?: boolean;
  error?: boolean;
};

type RoleOption = {
  id: "general" | "sre" | "devops" | "developer" | "hr" | "custom";
  label: string;
  prompt: string;
};

const ROLE_STORAGE_KEY = "cvum.custom.role.v2";
const ATTACHMENT_ACCEPT = ".md,.txt,.pdf,.docx,.csv,.html,.png,.jpg,.jpeg,.gif,.bmp,.webp,.tif,.tiff";
const MAX_ATTACHMENTS = 8;

const ROLES: RoleOption[] = [
  {
    id: "general",
    label: "General",
    prompt:
      "Act as an enterprise knowledge assistant. Give a direct, source-grounded answer with concrete facts and next steps.",
  },
  {
    id: "sre",
    label: "SRE",
    prompt:
      "Act as a senior Site Reliability Engineer. Prioritize incident evidence, service impact, logs, metrics, runbooks, rollback safety, and verification steps.",
  },
  {
    id: "devops",
    label: "DevOps",
    prompt:
      "Act as a senior DevOps engineer. Prioritize Kubernetes, CI/CD, ArgoCD, Terraform, deployment safety, access paths, rollback, and release validation.",
  },
  {
    id: "developer",
    label: "Developer",
    prompt:
      "Act as a senior software engineer. Prioritize API contracts, code-level diagnosis, database behavior, implementation details, tests, and production-safe verification.",
  },
  {
    id: "hr",
    label: "HR",
    prompt:
      "Act as an HR and people-operations assistant. Prioritize approved policy, onboarding, access paths, team process, and internal guidance.",
  },
  {
    id: "custom",
    label: "Custom",
    prompt: "Use the saved custom role while keeping source-grounding and security rules authoritative.",
  },
];

const STARTERS = [
  "Summarize the latest production incidents and their root causes",
  "Explain the HES architecture and its major components",
  "Show open Jira work that needs DevOps attention",
  "Find the broker restart procedure and validation steps",
];

function readCustomRole(): AssistantRoleConfig | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(ROLE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AssistantRoleConfig>;
    if (!parsed.name?.trim() || !parsed.prompt?.trim()) return null;
    return { name: parsed.name.trim(), prompt: parsed.prompt.trim() };
  } catch {
    window.localStorage.removeItem(ROLE_STORAGE_KEY);
    return null;
  }
}

function sourceTitle(source: RagSource) {
  return source.title ?? source.document_title ?? "Retrieved source";
}

function sourceSnippet(source: RagSource) {
  const value = source.snippet ?? source.content ?? "No preview is available for this source.";
  return value
    .replace(/\r\n/g, "\n")
    .split("\n")
    .filter((line, index) => !(index === 0 && line.trim().startsWith("# ")) && !/^URL:\s+/i.test(line.trim()))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

function citationsFromMessage(message: MessageOut): RagSource[] {
  return message.citations.map((citation) => ({
    chunk_id: citation.chunk_id,
    document_id: citation.document_id,
    marker: citation.marker,
    score: citation.score,
    snippet: citation.snippet,
    title: citation.title ?? citation.document_title ?? `Source ${citation.marker}`,
    document_title: citation.document_title ?? citation.title ?? `Source ${citation.marker}`,
    source_type: citation.source_type ?? undefined,
    url: citation.url ?? undefined,
  }));
}

function messageFromApi(message: MessageOut): ChatMessage {
  return {
    id: message.id,
    messageId: message.role === "assistant" ? message.id : undefined,
    role: message.role,
    content: message.content,
    citations: citationsFromMessage(message),
    model: message.model,
  };
}

function formatConversationDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date();
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function phaseLabel(phase: ChatPhase) {
  if (phase === "uploading") return "Indexing attachments";
  if (phase === "searching") return "Searching and grading sources";
  if (phase === "answering") return "Writing a grounded answer";
  return "";
}

async function waitForDocument(documentId: string) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const document = await kimbalApi.getDocument(documentId);
    if (document.status === "ready") return;
    if (document.status === "failed") {
      throw new Error(document.error || `Could not index ${document.title}.`);
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  throw new Error("The attachment is still indexing. Try again in a moment.");
}

function InlineMarkdown({ text, onCitationClick }: { text: string; onCitationClick: (marker: number) => void }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[\d+\])/g).filter(Boolean);
  return (
    <>
      {parts.map((part, index) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={`${part}-${index}`} className="font-semibold text-[#202123]">{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("`") && part.endsWith("`")) {
          return <code key={`${part}-${index}`} className="rounded bg-[#f1f3f4] px-1.5 py-0.5 font-mono text-[13px] text-[#343541]">{part.slice(1, -1)}</code>;
        }
        if (/^\[\d+\]$/.test(part)) {
          const marker = Number(part.slice(1, -1));
          return (
            <button
              key={`${part}-${index}`}
              type="button"
              onClick={() => onCitationClick(marker)}
              className="ml-0.5 align-super text-[10px] font-bold leading-none text-[#5b5ceb] underline-offset-2 hover:underline"
              title={`Open source ${marker}`}
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

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  const label = language.trim().toLowerCase() || "code";

  async function copyCode() {
    try {
      await window.navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="my-4 overflow-hidden rounded-lg border border-[#2f2f2f] bg-[#0d0d0d] text-white">
      <div className="flex h-10 items-center justify-between bg-[#2f2f2f] px-4 text-xs text-[#d1d5db]">
        <span className="font-mono">{label}</span>
        <button
          type="button"
          onClick={() => void copyCode()}
          className="flex items-center gap-1.5 text-[#e5e7eb] transition hover:text-white"
          aria-label="Copy code"
          title="Copy code"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          <span>{copied ? "Copied" : "Copy code"}</span>
        </button>
      </div>
      <pre className="max-w-full overflow-x-auto p-4 text-[13px] leading-6 sm:text-[14px]">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}

function MarkdownAnswer({
  content,
  pending,
  onCitationClick,
}: {
  content: string;
  pending: boolean;
  onCitationClick: (marker: number) => void;
}) {
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: Array<{ kind: "ol" | "ul"; text: string }> = [];
  let codeFence: { marker: "```" | "~~~"; language: string; lines: string[] } | null = null;

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="text-[15px] leading-7 text-[#343541]">
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
        className={cx("space-y-1.5 pl-5 text-[15px] leading-7 text-[#343541]", kind === "ol" ? "list-decimal" : "list-disc")}
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
    const fence = rawLine.trim().match(/^(```|~~~)\s*([^\s`]*)?.*$/);
    if (codeFence) {
      if (fence?.[1] === codeFence.marker) {
        blocks.push(
          <CodeBlock
            key={`code-${blocks.length}`}
            code={codeFence.lines.join("\n").replace(/\n+$/, "")}
            language={codeFence.language}
          />
        );
        codeFence = null;
      } else {
        codeFence.lines.push(rawLine);
      }
      continue;
    }
    if (fence) {
      flushParagraph();
      flushList();
      codeFence = {
        marker: fence[1] as "```" | "~~~",
        language: fence[2] || "code",
        lines: [],
      };
      continue;
    }

    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(
        <h3 key={`h-${blocks.length}`} className={cx("font-semibold text-[#202123]", level === 1 ? "text-[20px] leading-8" : "pt-2 text-[16px] leading-7")}>
          <InlineMarkdown text={heading[2].replace(/\s+#+$/, "")} onCitationClick={onCitationClick} />
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
  if (codeFence) {
    blocks.push(
      <CodeBlock
        key={`code-${blocks.length}`}
        code={codeFence.lines.join("\n").replace(/\n+$/, "")}
        language={codeFence.language}
      />
    );
  }

  return (
    <div className="space-y-3">
      {blocks}
      {pending && <span className="inline-block h-4 w-1.5 animate-pulse rounded-sm bg-[#5b5ceb] align-middle" />}
    </div>
  );
}

export function ChatAskClient() {
  const params = useSearchParams();
  const initialQuestion = params.get("q") ?? "";
  const autoAsked = useRef(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const attachmentRef = useRef<HTMLInputElement>(null);

  const [user, setUser] = useState<UserOut | null>(null);
  const [input, setInput] = useState(initialQuestion);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationKbId, setConversationKbId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [historySearch, setHistorySearch] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [openingConversation, setOpeningConversation] = useState<string | null>(null);
  const [phase, setPhase] = useState<ChatPhase>("idle");
  const [error, setError] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [sourceMode, setSourceMode] = useState<SourceMode>("knowledge");
  const [answerMode, setAnswerMode] = useState<AnswerMode>("fast");
  const [roleId, setRoleId] = useState<RoleOption["id"]>("devops");
  const [webStatus, setWebStatus] = useState<WebSearchStatus | null>(null);
  const [capabilities, setCapabilities] = useState<ChatCapabilities | null>(null);
  const [councilModels, setCouncilModels] = useState<string[]>([]);
  const [councilChair, setCouncilChair] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [activeSources, setActiveSources] = useState<RagSource[]>([]);
  const [highlightedMarker, setHighlightedMarker] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<Record<string, "up" | "down">>({});
  const [customRole, setCustomRole] = useState<AssistantRoleConfig | null>(() => readCustomRole());
  const [customName, setCustomName] = useState(() => readCustomRole()?.name ?? "");
  const [customGoal, setCustomGoal] = useState("");
  const [customSources, setCustomSources] = useState("");
  const [customStyle, setCustomStyle] = useState("");
  const [generatingRole, setGeneratingRole] = useState(false);

  const busy = phase !== "idle";
  const availableCouncilModels = capabilities?.council_available_models ?? [];

  const filteredConversations = useMemo(() => {
    const needle = historySearch.trim().toLowerCase();
    if (!needle) return conversations;
    return conversations.filter((conversation) => conversation.title.toLowerCase().includes(needle));
  }, [conversations, historySearch]);

  const loadConversations = useCallback(async () => {
    try {
      setLoadingHistory(true);
      setConversations(await kimbalApi.listConversations());
    } catch {
      setConversations([]);
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const currentUser = await kimbalApi.ensureSession();
        const [history, web, chat] = await Promise.all([
          kimbalApi.listConversations(),
          kimbalApi.webSearchStatus(),
          kimbalApi.chatCapabilities(),
        ]);
        if (cancelled) return;
        setUser(currentUser);
        setConversations(history);
        setWebStatus(web);
        setCapabilities(chat);
        const available = chat.council_available_models;
        const chair = chat.council_chair_model && available.includes(chat.council_chair_model)
          ? chat.council_chair_model
          : available[0] ?? "";
        const members = (chat.council_models.length ? chat.council_models : available)
          .filter((model) => model !== chair)
          .slice(0, 2);
        setCouncilModels(members);
        setCouncilChair(chair);
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load the workspace.");
      } finally {
        if (!cancelled) setLoadingHistory(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth", block: "end" });
  }, [busy, messages]);

  useEffect(() => {
    if (!sourcesOpen || highlightedMarker === null) return;
    const timer = window.setTimeout(() => {
      document.getElementById(`chat-source-${highlightedMarker}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [highlightedMarker, sourcesOpen]);

  function activeRole(): AssistantRoleConfig {
    if (roleId === "custom" && customRole) return customRole;
    const role = ROLES.find((item) => item.id === roleId) ?? ROLES[0];
    return { name: role.label, prompt: role.prompt };
  }

  function councilConfig(): CouncilConfig | undefined {
    const models = Array.from(new Set(councilModels.filter(Boolean))).slice(0, 2);
    if (answerMode !== "council" || models.length !== 2 || !councilChair || models.includes(councilChair)) {
      return undefined;
    }
    return { models, chairModel: councilChair };
  }

  function updateAssistant(id: string, update: (message: ChatMessage) => ChatMessage) {
    setMessages((current) => current.map((message) => (message.id === id ? update(message) : message)));
  }

  async function askQuestion(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    if ((sourceMode === "web" || sourceMode === "blended") && webStatus?.configured !== true) {
      setError(webStatus?.reason ?? "Web search is not configured.");
      return;
    }
    if (answerMode === "council" && capabilities?.council_configured !== true) {
      setError(capabilities?.council_reason ?? "Council mode is not configured.");
      setSettingsOpen(true);
      return;
    }
    const requestedCouncil = councilConfig();
    if (answerMode === "council" && !requestedCouncil) {
      setError("Select two response models and a different evaluator model.");
      setSettingsOpen(true);
      return;
    }
    if (roleId === "custom" && !customRole) {
      setError("Create the custom role before using it.");
      setSettingsOpen(true);
      return;
    }

    setError("");
    setInput("");
    setPhase(attachments.length ? "uploading" : "searching");
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      citations: [],
    };
    const assistantId = `assistant-${Date.now()}`;
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
      pending: true,
    };
    setMessages((current) => [...current, userMessage, assistantMessage]);

    try {
      await kimbalApi.ensureSession();
      let activeConversationId = conversationId;
      let activeKbId = conversationKbId;

      if (attachments.length) {
        const uploadKb = await kimbalApi.ensureUploadKnowledgeBase();
        for (const attachment of attachments) {
          const document = await kimbalApi.uploadDocument(uploadKb.id, attachment);
          await waitForDocument(document.id);
        }
        setAttachments([]);
        if (!activeConversationId || activeKbId !== uploadKb.id) {
          const conversation = await kimbalApi.createConversation(uploadKb.id, trimmed.slice(0, 80));
          activeConversationId = conversation.id;
          activeKbId = conversation.knowledge_base_id;
          setConversationId(conversation.id);
          setConversationKbId(conversation.knowledge_base_id);
        }
      }

      if (!activeConversationId) {
        const kb = await kimbalApi.ensureKnowledgeBase();
        const conversation = await kimbalApi.createConversation(kb.id, trimmed.slice(0, 80));
        activeConversationId = conversation.id;
        activeKbId = conversation.knowledge_base_id;
        setConversationId(conversation.id);
        setConversationKbId(conversation.knowledge_base_id);
      }
      if (!activeKbId) setConversationKbId(conversationKbId);

      setPhase("searching");
      for await (const event of kimbalApi.ask(
        activeConversationId,
        trimmed,
        sourceMode,
        answerMode,
        requestedCouncil,
        activeRole()
      )) {
        if (event.type === "sources") {
          const citations = event.data.sources ?? event.data.hits ?? [];
          updateAssistant(assistantId, (message) => ({ ...message, citations }));
          setActiveSources(citations);
          setPhase("answering");
        } else if (event.type === "delta") {
          const text = event.data.text ?? event.data.delta ?? event.data.content ?? "";
          updateAssistant(assistantId, (message) => ({ ...message, content: message.content + text }));
          setPhase("answering");
        } else if (event.type === "done") {
          updateAssistant(assistantId, (message) => ({
            ...message,
            id: event.data.message_id ?? message.id,
            messageId: event.data.message_id,
            content: event.data.answer ?? message.content,
            model: event.data.model,
            pending: false,
          }));
        } else if (event.type === "error") {
          throw new Error(event.data.message ?? event.data.code ?? "The answer stream failed.");
        }
      }
      await loadConversations();
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "The request failed.";
      setError(message);
      updateAssistant(assistantId, (current) => ({ ...current, content: message, pending: false, error: true }));
    } finally {
      setPhase("idle");
      textareaRef.current?.focus();
    }
  }

  useEffect(() => {
    if (!initialQuestion.trim() || autoAsked.current) return;
    autoAsked.current = true;
    const timer = window.setTimeout(() => void askQuestion(initialQuestion), 0);
    return () => window.clearTimeout(timer);
    // Run once for a query-linked first request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openConversation(conversation: Conversation) {
    if (busy) return;
    setOpeningConversation(conversation.id);
    setError("");
    try {
      const loaded = await kimbalApi.listMessages(conversation.id);
      setConversationId(conversation.id);
      setConversationKbId(conversation.knowledge_base_id);
      setMessages(loaded.map(messageFromApi));
      setSidebarOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not open this conversation.");
    } finally {
      setOpeningConversation(null);
    }
  }

  function newChat() {
    if (busy) return;
    setConversationId(null);
    setConversationKbId(null);
    setMessages([]);
    setInput("");
    setAttachments([]);
    setError("");
    setActiveSources([]);
    setSourcesOpen(false);
    setSidebarOpen(false);
    textareaRef.current?.focus();
  }

  async function deleteConversation(conversation: Conversation) {
    if (busy) return;
    try {
      await kimbalApi.deleteConversation(conversation.id);
      if (conversationId === conversation.id) newChat();
      await loadConversations();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this conversation.");
    }
  }

  function openSources(sources: RagSource[], marker?: number) {
    setActiveSources(sources);
    setHighlightedMarker(marker ?? null);
    setSourcesOpen(true);
  }

  async function rateMessage(message: ChatMessage, rating: 1 | -1) {
    const id = message.messageId ?? message.id;
    if (!id || message.pending) return;
    try {
      await kimbalApi.submitFeedback(id, rating);
      setFeedback((current) => ({ ...current, [id]: rating === 1 ? "up" : "down" }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save feedback.");
    }
  }

  async function copyAnswer(content: string) {
    try {
      await navigator.clipboard.writeText(content);
    } catch {
      setError("Clipboard access is unavailable.");
    }
  }

  async function generateCustomRole(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!customName.trim() || !customGoal.trim()) return;
    setGeneratingRole(true);
    setError("");
    try {
      const role = await kimbalApi.generateRolePrompt({
        name: customName,
        goal: customGoal,
        sourceFocus: customSources,
        outputStyle: customStyle,
      });
      setCustomRole(role);
      setCustomName(role.name);
      setRoleId("custom");
      window.localStorage.setItem(ROLE_STORAGE_KEY, JSON.stringify(role));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the custom role.");
    } finally {
      setGeneratingRole(false);
    }
  }

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = event.target.files ? Array.from(event.target.files) : [];
    if (files.length) addAttachments(files);
    event.target.value = "";
  }

  function addAttachments(files: File[]) {
    if (attachments.length + files.length > MAX_ATTACHMENTS) {
      setError(`You can attach up to ${MAX_ATTACHMENTS} files per message.`);
    }
    setAttachments((current) => {
      const next = [...current];
      for (const file of files) {
        const duplicate = next.some(
          (item) => item.name === file.name && item.size === file.size && item.type === file.type
        );
        if (!duplicate && next.length < MAX_ATTACHMENTS) next.push(file);
      }
      return next;
    });
  }

  function handleComposerPaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    if (busy) return;
    const imageFiles = Array.from(event.clipboardData.items)
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null)
      .map((file, index) => {
        const extension = file.type.split("/")[1]?.replace("jpeg", "jpg") || "png";
        const name = `pasted-image-${Date.now()}-${index + 1}.${extension}`;
        return new File([file], name, { type: file.type, lastModified: Date.now() });
      });
    if (!imageFiles.length) return;
    event.preventDefault();
    setError("");
    addAttachments(imageFiles);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void askQuestion(input);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void askQuestion(input);
    }
  }

  async function logout() {
    await kimbalApi.logout();
    window.location.replace("/login");
  }

  return (
    <div className="min-h-screen bg-white text-[#202123]">
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-50 flex w-[280px] flex-col border-r border-[#e5e7eb] bg-[#f7f7f8] transition-transform lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center gap-2 px-4">
          <CVUMMark size={29} />
          <span className="text-[17px] font-semibold">CVUM</span>
          <button type="button" onClick={() => setSidebarOpen(false)} className="ml-auto flex h-9 w-9 items-center justify-center rounded-lg text-[#6b7280] hover:bg-white lg:hidden" aria-label="Close chats" title="Close chats">
            <X size={18} />
          </button>
        </div>

        <div className="px-3">
          <button type="button" onClick={newChat} disabled={busy} className="flex h-11 w-full items-center gap-3 rounded-lg border border-[#d9dce1] bg-white px-3 text-[14px] font-medium shadow-sm hover:bg-[#fafafa] disabled:opacity-50">
            <MessageSquarePlus size={17} />
            New chat
          </button>
          <label className="mt-3 flex h-10 items-center gap-2 rounded-lg bg-[#ececf1] px-3 text-[#6b7280]">
            <Search size={15} />
            <input value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Search chats" className="min-w-0 flex-1 bg-transparent text-[13px] text-[#343541] outline-none placeholder:text-[#8e8ea0]" />
          </label>
        </div>

        <nav className="mt-5 flex-1 overflow-y-auto px-2 pb-4">
          <p className="px-2 pb-2 text-[11px] font-semibold uppercase text-[#8e8ea0]">Recent</p>
          {loadingHistory ? (
            <div className="flex items-center gap-2 px-3 py-3 text-[13px] text-[#8e8ea0]"><Loader2 size={14} className="animate-spin" /> Loading chats</div>
          ) : filteredConversations.length ? (
            <ul className="space-y-0.5">
              {filteredConversations.map((conversation) => (
                <li key={conversation.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => void openConversation(conversation)}
                    className={cx(
                      "flex min-h-11 w-full items-center rounded-lg px-3 pr-16 text-left text-[13px] hover:bg-[#ececf1]",
                      conversationId === conversation.id && "bg-[#e7e7ec]"
                    )}
                  >
                    <span className="truncate">{conversation.title || "Untitled chat"}</span>
                  </button>
                  <span className="pointer-events-none absolute right-9 top-3.5 text-[10px] text-[#9ca3af] group-hover:hidden">{formatConversationDate(conversation.updated_at)}</span>
                  <button type="button" onClick={() => void deleteConversation(conversation)} className="absolute right-2 top-1.5 hidden h-8 w-8 items-center justify-center rounded-md text-[#8e8ea0] hover:bg-white hover:text-[#b42318] group-hover:flex" aria-label={`Delete ${conversation.title}`} title="Delete chat">
                    {openingConversation === conversation.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 py-3 text-[13px] text-[#8e8ea0]">No chats found</p>
          )}
        </nav>

        <div className="border-t border-[#e5e7eb] p-3">
          {user?.role === "admin" && (
            <Link href="/admin" className="flex h-10 items-center gap-3 rounded-lg px-3 text-[13px] font-medium text-[#4b5563] hover:bg-white">
              <LayoutDashboard size={16} /> Admin dashboard
            </Link>
          )}
          <button type="button" onClick={() => void logout()} className="mt-1 flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[13px] font-medium text-[#4b5563] hover:bg-white">
            <LogOut size={16} /> Sign out
          </button>
        </div>
      </aside>

      {sidebarOpen && <button type="button" className="fixed inset-0 z-40 bg-black/30 lg:hidden" onClick={() => setSidebarOpen(false)} aria-label="Close chats" />}

      <div className="min-h-screen lg:pl-[280px]">
        <header className="sticky top-0 z-30 flex h-16 items-center border-b border-[#ececf1] bg-white/95 px-3 backdrop-blur-md sm:px-5">
          <button type="button" onClick={() => setSidebarOpen(true)} className="flex h-10 w-10 items-center justify-center rounded-lg text-[#4b5563] hover:bg-[#f7f7f8] lg:hidden" aria-label="Open chats" title="Open chats">
            <Menu size={20} />
          </button>
          <div className="ml-1 min-w-0">
            <p className="truncate text-[15px] font-semibold">{conversationId ? conversations.find((item) => item.id === conversationId)?.title || "CVUM" : "CVUM"}</p>
            <p className="text-[11px] text-[#8e8ea0]">Enterprise knowledge assistant</p>
          </div>
          <div className="ml-auto flex items-center gap-1">
            <label className="relative hidden sm:block">
              <span className="sr-only">Assistant role</span>
              <select
                value={roleId}
                onChange={(event) => {
                  const next = event.target.value as RoleOption["id"];
                  setRoleId(next);
                  if (next === "custom" && !customRole) setSettingsOpen(true);
                }}
                className="h-9 appearance-none rounded-lg border border-[#e5e7eb] bg-white pl-3 pr-8 text-[12px] font-medium outline-none hover:bg-[#f7f7f8]"
              >
                {ROLES.map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}
              </select>
              <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-3 text-[#8e8ea0]" />
            </label>
            <button type="button" onClick={() => setSettingsOpen(true)} className="flex h-10 w-10 items-center justify-center rounded-lg text-[#4b5563] hover:bg-[#f7f7f8]" aria-label="Ask settings" title="Ask settings">
              <Settings2 size={18} />
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[860px] px-4 pb-56 pt-8 sm:px-8">
          {!messages.length ? (
            <section className="flex min-h-[calc(100vh-300px)] flex-col justify-center">
              <div className="mx-auto flex max-w-[680px] flex-col items-center text-center">
                <CVUMMark size={46} />
                <h1 className="mt-5 text-[30px] font-semibold leading-10">How can I help?</h1>
              </div>
              <div className="mx-auto mt-9 grid w-full max-w-[680px] grid-cols-1 gap-2 sm:grid-cols-2">
                {STARTERS.map((starter) => (
                  <button key={starter} type="button" onClick={() => void askQuestion(starter)} className="min-h-[72px] rounded-lg border border-[#e5e7eb] bg-white px-4 py-3 text-left text-[13px] leading-5 text-[#4b5563] hover:bg-[#f7f7f8]">
                    {starter}
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="space-y-10">
              {messages.map((message) => (
                <article key={message.id} className={cx("flex", message.role === "user" ? "justify-end" : "justify-start")}>
                  {message.role === "user" ? (
                    <div className="max-w-[78%] rounded-2xl bg-[#f0f0f0] px-4 py-2.5 text-[15px] leading-6 text-[#202123]">
                      {message.content}
                    </div>
                  ) : (
                    <div className="flex w-full gap-3 sm:gap-4">
                      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#e5e7eb] bg-white">
                        <Sparkles size={16} className="text-[#5b5ceb]" />
                      </span>
                      <div className="min-w-0 flex-1 pt-0.5">
                        {message.error ? (
                          <p className="rounded-lg border border-[#fecdca] bg-[#fef3f2] px-3 py-2.5 text-[14px] text-[#b42318]">{message.content}</p>
                        ) : message.content ? (
                          <MarkdownAnswer content={message.content} pending={Boolean(message.pending)} onCitationClick={(marker) => openSources(message.citations, marker)} />
                        ) : (
                          <div className="flex items-center gap-2 py-1 text-[13px] text-[#6b7280]">
                            <Loader2 size={15} className="animate-spin text-[#5b5ceb]" /> {phaseLabel(phase)}
                          </div>
                        )}

                        {!message.pending && !message.error && message.content && (
                          <div className="mt-4 flex flex-wrap items-center gap-1 text-[#8e8ea0]">
                            <button type="button" onClick={() => void copyAnswer(message.content)} className="flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#f7f7f8] hover:text-[#343541]" aria-label="Copy answer" title="Copy answer"><Copy size={15} /></button>
                            <button type="button" onClick={() => void rateMessage(message, 1)} className={cx("flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#f7f7f8] hover:text-[#343541]", feedback[message.messageId ?? message.id] === "up" && "bg-[#ecfdf3] text-[#067647]")} aria-label="Helpful" title="Helpful"><ThumbsUp size={15} /></button>
                            <button type="button" onClick={() => void rateMessage(message, -1)} className={cx("flex h-8 w-8 items-center justify-center rounded-md hover:bg-[#f7f7f8] hover:text-[#343541]", feedback[message.messageId ?? message.id] === "down" && "bg-[#fef3f2] text-[#b42318]")} aria-label="Not helpful" title="Not helpful"><ThumbsDown size={15} /></button>
                            {message.citations.length > 0 && (
                              <button type="button" onClick={() => openSources(message.citations)} className="ml-1 inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-[12px] font-medium hover:bg-[#f7f7f8] hover:text-[#343541]">
                                <BookOpen size={14} /> {message.citations.length} source{message.citations.length === 1 ? "" : "s"}
                              </button>
                            )}
                            {message.model && <span className="ml-2 text-[11px] text-[#a1a1aa]">{message.model.replace(/^llm-council:/, "Council: ")}</span>}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </main>

        <div className="fixed inset-x-0 bottom-0 z-30 bg-white pb-3 lg:left-[280px]">
          <div className="mx-auto w-full max-w-[860px] px-3 sm:px-8">
            {error && (
              <div className="mb-2 flex items-center gap-2 rounded-lg border border-[#fecdca] bg-[#fef3f2] px-3 py-2 text-[12px] text-[#b42318]">
                <span className="min-w-0 flex-1">{error}</span>
                <button type="button" onClick={() => setError("")} className="flex h-6 w-6 items-center justify-center rounded hover:bg-white" aria-label="Dismiss error" title="Dismiss"><X size={13} /></button>
              </div>
            )}
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {attachments.map((file, index) => (
                  <span key={`${file.name}-${file.lastModified}-${index}`} className="inline-flex max-w-[220px] items-center gap-1.5 rounded-md border border-[#e5e7eb] bg-white px-2 py-1 text-[11px] text-[#4b5563]">
                    {file.type.startsWith("image/") ? <ImageIcon size={12} className="shrink-0" /> : <FileText size={12} className="shrink-0" />}<span className="truncate">{file.name}</span>
                    <button type="button" onClick={() => setAttachments((current) => current.filter((_, itemIndex) => itemIndex !== index))} className="hover:text-[#b42318]" aria-label={`Remove ${file.name}`}><X size={11} /></button>
                  </span>
                ))}
              </div>
            )}
            <form onSubmit={submit} className="rounded-2xl border border-[#d9dce1] bg-white p-2 shadow-[0_8px_30px_rgba(0,0,0,0.10)] focus-within:border-[#aeb4bd]">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                onPaste={handleComposerPaste}
                onInput={(event) => {
                  event.currentTarget.style.height = "auto";
                  event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 160)}px`;
                }}
                placeholder="Ask anything across Jira, Confluence, and your documents"
                rows={1}
                className="max-h-40 min-h-11 w-full resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 outline-none placeholder:text-[#8e8ea0]"
              />
              <input ref={attachmentRef} type="file" accept={ATTACHMENT_ACCEPT} multiple className="hidden" onChange={handleFiles} />
              <div className="flex items-center gap-1 px-1 pb-0.5">
                <button type="button" onClick={() => attachmentRef.current?.click()} disabled={busy} className="flex h-9 w-9 items-center justify-center rounded-lg text-[#6b7280] hover:bg-[#f7f7f8] disabled:opacity-40" aria-label="Attach documents" title="Attach documents"><Paperclip size={17} /></button>
                <label className="relative">
                  <span className="sr-only">Source mode</span>
                  {sourceMode === "knowledge" ? <BookOpen size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-[#6b7280]" /> : <Globe2 size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-[#6b7280]" />}
                  <select value={sourceMode} onChange={(event) => setSourceMode(event.target.value as SourceMode)} disabled={busy} className="h-9 appearance-none rounded-lg bg-transparent pl-8 pr-7 text-[12px] font-medium text-[#4b5563] outline-none hover:bg-[#f7f7f8] disabled:opacity-40">
                    <option value="knowledge">Knowledge</option>
                    <option value="web" disabled={webStatus?.configured !== true}>Web</option>
                    <option value="blended" disabled={webStatus?.configured !== true}>Both</option>
                  </select>
                  <ChevronDown size={12} className="pointer-events-none absolute right-2 top-3 text-[#8e8ea0]" />
                </label>
                <label className="relative hidden sm:block">
                  <span className="sr-only">Answer mode</span>
                  {answerMode === "fast" ? <Zap size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-[#6b7280]" /> : <Users size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-[#6b7280]" />}
                  <select value={answerMode} onChange={(event) => setAnswerMode(event.target.value as AnswerMode)} disabled={busy} className="h-9 appearance-none rounded-lg bg-transparent pl-8 pr-7 text-[12px] font-medium text-[#4b5563] outline-none hover:bg-[#f7f7f8] disabled:opacity-40">
                    <option value="fast">Fast</option>
                    <option value="council" disabled={capabilities?.council_configured !== true}>Council</option>
                  </select>
                  <ChevronDown size={12} className="pointer-events-none absolute right-2 top-3 text-[#8e8ea0]" />
                </label>
                <button type="submit" disabled={busy || (!input.trim() && !attachments.length)} className="ml-auto flex h-9 w-9 items-center justify-center rounded-lg bg-[#202123] text-white hover:bg-[#343541] disabled:bg-[#d1d5db]" aria-label="Send message" title="Send message">
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowUp size={17} />}
                </button>
              </div>
            </form>
            <p className="mt-2 text-center text-[11px] text-[#8e8ea0]">CVUM can make mistakes. Verify important details in the cited sources.</p>
          </div>
        </div>
      </div>

      {sourcesOpen && (
        <>
          <button type="button" className="fixed inset-0 z-40 bg-black/20" onClick={() => setSourcesOpen(false)} aria-label="Close sources" />
          <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-[420px] overflow-y-auto border-l border-[#e5e7eb] bg-white shadow-2xl">
            <div className="sticky top-0 flex h-16 items-center border-b border-[#e5e7eb] bg-white px-5">
              <div><p className="text-[15px] font-semibold">Sources</p><p className="text-[11px] text-[#8e8ea0]">{activeSources.length} retrieved references</p></div>
              <button type="button" onClick={() => setSourcesOpen(false)} className="ml-auto flex h-9 w-9 items-center justify-center rounded-lg text-[#6b7280] hover:bg-[#f7f7f8]" aria-label="Close sources" title="Close sources"><PanelRightClose size={18} /></button>
            </div>
            <div className="space-y-3 p-4">
              {activeSources.map((source, index) => {
                const marker = source.marker ?? index + 1;
                return (
                  <article id={`chat-source-${marker}`} key={`${source.chunk_id}-${marker}`} className={cx("rounded-lg border p-4 transition", highlightedMarker === marker ? "border-[#5b5ceb] bg-[#f7f7ff]" : "border-[#e5e7eb]")}>
                    <div className="flex items-start gap-3">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#ececf1] text-[11px] font-semibold text-[#4b5563]">{marker}</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-semibold leading-5 text-[#202123]">{sourceTitle(source)}</p>
                        <div className="mt-1.5 flex items-center gap-2 text-[10px] uppercase text-[#8e8ea0]">
                          <span>{source.source_type ?? "knowledge"}</span>
                          {typeof source.score === "number" && <span>{Math.round(Math.max(0, Math.min(1, source.score)) * 100)}% match</span>}
                        </div>
                      </div>
                      {source.url && <a href={source.url} target="_blank" rel="noreferrer" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[#6b7280] hover:bg-[#f7f7f8] hover:text-[#202123]" aria-label={`Open ${sourceTitle(source)}`} title="Open source"><ExternalLink size={15} /></a>}
                    </div>
                    <p className="mt-3 line-clamp-6 text-[12px] leading-5 text-[#6b7280]">{sourceSnippet(source)}</p>
                  </article>
                );
              })}
              {!activeSources.length && <p className="px-2 py-10 text-center text-[13px] text-[#8e8ea0]">No sources are attached to this answer.</p>}
            </div>
          </aside>
        </>
      )}

      {settingsOpen && (
        <>
          <button type="button" className="fixed inset-0 z-40 bg-black/20" onClick={() => setSettingsOpen(false)} aria-label="Close settings" />
          <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-[440px] overflow-y-auto border-l border-[#e5e7eb] bg-white shadow-2xl">
            <div className="sticky top-0 flex h-16 items-center border-b border-[#e5e7eb] bg-white px-5">
              <div><p className="text-[15px] font-semibold">Ask settings</p><p className="text-[11px] text-[#8e8ea0]">Retrieval and answer configuration</p></div>
              <button type="button" onClick={() => setSettingsOpen(false)} className="ml-auto flex h-9 w-9 items-center justify-center rounded-lg text-[#6b7280] hover:bg-[#f7f7f8]" aria-label="Close settings" title="Close settings"><X size={18} /></button>
            </div>
            <div className="space-y-7 p-5">
              <section>
                <label className="text-[12px] font-semibold text-[#4b5563]">Assistant role</label>
                <select value={roleId} onChange={(event) => setRoleId(event.target.value as RoleOption["id"])} className="mt-2 h-11 w-full rounded-lg border border-[#d9dce1] bg-white px-3 text-[13px] outline-none focus:border-[#5b5ceb]">
                  {ROLES.map((role) => <option key={role.id} value={role.id}>{role.label}</option>)}
                </select>
              </section>

              <section className="grid grid-cols-2 gap-3">
                <label className="text-[12px] font-semibold text-[#4b5563]">Sources<select value={sourceMode} onChange={(event) => setSourceMode(event.target.value as SourceMode)} className="mt-2 h-11 w-full rounded-lg border border-[#d9dce1] bg-white px-3 text-[13px] font-normal outline-none focus:border-[#5b5ceb]"><option value="knowledge">Knowledge</option><option value="web" disabled={webStatus?.configured !== true}>Web</option><option value="blended" disabled={webStatus?.configured !== true}>Both</option></select></label>
                <label className="text-[12px] font-semibold text-[#4b5563]">Answer mode<select value={answerMode} onChange={(event) => setAnswerMode(event.target.value as AnswerMode)} className="mt-2 h-11 w-full rounded-lg border border-[#d9dce1] bg-white px-3 text-[13px] font-normal outline-none focus:border-[#5b5ceb]"><option value="fast">Fast</option><option value="council" disabled={capabilities?.council_configured !== true}>Council</option></select></label>
              </section>

              {answerMode === "council" && (
                <section className="space-y-3 border-t border-[#ececf1] pt-5">
                  <p className="text-[12px] font-semibold text-[#4b5563]">Council models</p>
                  {[0, 1].map((index) => (
                    <select key={index} value={councilModels[index] ?? ""} onChange={(event) => setCouncilModels((current) => { const next = [...current]; next[index] = event.target.value; return next; })} className="h-11 w-full rounded-lg border border-[#d9dce1] bg-white px-3 text-[13px] outline-none focus:border-[#5b5ceb]">
                      <option value="">Select response model {index + 1}</option>
                      {availableCouncilModels.filter((model) => model !== councilChair && (councilModels[index === 0 ? 1 : 0] !== model)).map((model) => <option key={model} value={model}>{model}</option>)}
                    </select>
                  ))}
                  <select value={councilChair} onChange={(event) => setCouncilChair(event.target.value)} className="h-11 w-full rounded-lg border border-[#d9dce1] bg-white px-3 text-[13px] outline-none focus:border-[#5b5ceb]">
                    <option value="">Select evaluator</option>
                    {availableCouncilModels.filter((model) => !councilModels.includes(model)).map((model) => <option key={model} value={model}>{model}</option>)}
                  </select>
                </section>
              )}

              {roleId === "custom" && (
                <form onSubmit={generateCustomRole} className="space-y-3 border-t border-[#ececf1] pt-5">
                  <p className="text-[12px] font-semibold text-[#4b5563]">Custom role</p>
                  <input value={customName} onChange={(event) => setCustomName(event.target.value)} placeholder="Role name" className="h-11 w-full rounded-lg border border-[#d9dce1] px-3 text-[13px] outline-none focus:border-[#5b5ceb]" />
                  <textarea value={customGoal} onChange={(event) => setCustomGoal(event.target.value)} placeholder="Primary goal" rows={3} className="w-full resize-none rounded-lg border border-[#d9dce1] px-3 py-2.5 text-[13px] outline-none focus:border-[#5b5ceb]" />
                  <input value={customSources} onChange={(event) => setCustomSources(event.target.value)} placeholder="Preferred sources" className="h-11 w-full rounded-lg border border-[#d9dce1] px-3 text-[13px] outline-none focus:border-[#5b5ceb]" />
                  <input value={customStyle} onChange={(event) => setCustomStyle(event.target.value)} placeholder="Answer style" className="h-11 w-full rounded-lg border border-[#d9dce1] px-3 text-[13px] outline-none focus:border-[#5b5ceb]" />
                  <button type="submit" disabled={generatingRole || !customName.trim() || !customGoal.trim()} className="flex h-10 items-center gap-2 rounded-lg bg-[#202123] px-4 text-[13px] font-medium text-white hover:bg-[#343541] disabled:opacity-40">
                    {generatingRole ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} Generate role
                  </button>
                  {customRole && <p className="flex items-center gap-1.5 text-[11px] text-[#067647]"><Check size={13} /> {customRole.name} is active</p>}
                </form>
              )}
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
