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
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
  Search,
  Send,
  Share2,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  User,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Card, CardLink, GhostButton, cx } from "@/components/ui";
import {
  kimbalApi,
  type AnswerMode,
  type ChatCapabilities,
  type Conversation,
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
  return source.snippet ?? source.content ?? "Source chunk returned by hybrid search.";
}

function sourcesFromMessage(message: MessageOut | undefined): RagSource[] {
  if (!message?.citations?.length) return [];
  return message.citations.map((citation) => ({
    chunk_id: citation.chunk_id,
    document_id: citation.document_id,
    title: `Citation [${citation.marker}]`,
    document_title: `Citation [${citation.marker}]`,
    marker: citation.marker,
    score: citation.score,
    snippet: citation.snippet,
  }));
}

function InlineMarkdown({ text }: { text: string }) {
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
          return (
            <span
              key={`${part}-${index}`}
              className="ml-0.5 align-super text-[10.5px] font-bold leading-none text-brand-600"
            >
              {part}
            </span>
          );
        }
        return <span key={`${part}-${index}`}>{part}</span>;
      })}
    </>
  );
}

function MarkdownAnswer({ content, busy }: { content: string; busy: boolean }) {
  const blocks: React.ReactNode[] = [];
  let paragraph: string[] = [];
  let list: Array<{ kind: "ol" | "ul"; text: string }> = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="text-[14px] leading-7 text-ink-700">
        <InlineMarkdown text={paragraph.join(" ")} />
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
          "space-y-2 pl-5 text-[14px] leading-7 text-ink-700",
          kind === "ol" ? "list-decimal" : "list-disc"
        )}
      >
        {list.map((item, index) => (
          <li key={`${item.text}-${index}`} className="pl-1">
            <InlineMarkdown text={item.text} />
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
      flushList();
      continue;
    }

    const heading = line.match(/^\*\*(.+?)\*\*:?\s*$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push(
        <h3 key={`h-${blocks.length}`} className="pt-2 text-[15px] font-bold text-ink-900">
          {heading[1]}
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
    <div className="space-y-4">
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
  const [viewMode, setViewMode] = useState<"workbench" | "focus">("focus");
  const [focusRailExpanded, setFocusRailExpanded] = useState(false);
  const [focusDrawer, setFocusDrawer] = useState<"sources" | "history" | null>(null);
  const [modePanel, setModePanel] = useState<"web" | "council" | null>(null);

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

  useEffect(() => {
    let cancelled = false;
    async function loadCapabilities() {
      try {
        await kimbalApi.ensureSession();
        const [web, chat] = await Promise.all([kimbalApi.webSearchStatus(), kimbalApi.chatCapabilities()]);
        if (!cancelled) {
          setWebStatus(web);
          setChatCapabilities(chat);
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
    if (!initialQuestion.trim()) return;
    if (autoAsked.current) return;
    autoAsked.current = true;
    void ask(initialQuestion);
    // initialQuestion is intentionally captured once per page load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    setState("preparing");
    setError("");
    setFeedback("");
    setActionStatus("");
    setTurn({ question: trimmed, answer: "", sources: [], timings: {} });

    try {
      const kb = await kimbalApi.ensureKnowledgeBase();
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const conversation = await kimbalApi.createConversation(kb.id, trimmed.slice(0, 80));
        activeConversationId = conversation.id;
        setConversationId(conversation.id);
      }
      setState("searching");
      for await (const event of kimbalApi.ask(activeConversationId, trimmed, sourceMode, answerMode)) {
        if (event.type === "sources") {
          const sources = event.data.sources ?? event.data.hits ?? [];
          setTurn((current) => ({ ...current, sources }));
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
  const councilReady = chatCapabilities?.council_configured === true;
  const sourceModeText =
    sourceMode === "knowledge"
      ? "Retrieval uses synced Jira, Confluence, and uploaded documents."
      : sourceMode === "web"
        ? "Retrieval uses configured web search and stores citable web snippets locally."
        : "Retrieval blends internal knowledge with configured web search.";

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

  function chooseAnswerMode(next: AnswerMode) {
    if (next === "council" && !councilReady) {
      setModePanel("council");
      setActionStatus(chatCapabilities?.council_reason ?? "LLM Council is not configured.");
      return;
    }
    setAnswerMode(next);
    setModePanel(null);
    setActionStatus("");
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
            return (
              <button
                key={mode.value}
                type="button"
                disabled={busy}
                aria-pressed={answerMode === mode.value}
                title={unavailable ? (chatCapabilities?.council_reason ?? "LLM Council is not configured.") : mode.label}
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
                : councilReady
                  ? `Ready with ${chatCapabilities?.council_models.join(", ") || "configured models"}.`
                  : (chatCapabilities?.council_reason ?? "LLM Council is not configured.")}
            </p>
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

  function renderActionButtons() {
    return (
      <div className="flex flex-wrap items-center gap-2.5 border-t border-line pt-4">
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
        {actionStatus && <span className="ml-auto text-[12px] font-semibold text-ink-500">{actionStatus}</span>}
      </div>
    );
  }

  function renderSourcesList(limit = 6) {
    return (
      <ul className="mt-4 space-y-4">
        {turn.sources.slice(0, limit).map((source, index) => {
          const isWeb = source.source_type === "web";
          const SourceIcon = isWeb ? Globe : FileText;
          return (
            <li key={`${source.chunk_id}-${index}`} className="flex items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] border border-line bg-white text-brand-500">
                <SourceIcon size={16} />
              </span>
              <div className="min-w-0 flex-1">
                {source.url ? (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-[13px] font-semibold text-ink-900 hover:text-brand-600"
                  >
                    [{source.marker ?? index + 1}] {sourceTitle(source)}
                  </a>
                ) : (
                  <p className="truncate text-[13px] font-semibold text-ink-900">
                    [{source.marker ?? index + 1}] {sourceTitle(source)}
                  </p>
                )}
                <p className="line-clamp-2 text-[11.5px] text-ink-500">{sourceSnippet(source)}</p>
              </div>
              {typeof source.score === "number" && (
                <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11.5px] font-bold text-emerald-600">
                  {Math.round(source.score * 100)}%
                </span>
              )}
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

  if (viewMode === "focus") {
    const focusRailWidth = focusRailExpanded ? 248 : 72;
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

        <main className="min-h-screen transition-[padding]" style={{ paddingLeft: focusRailWidth }}>
          <div className="flex items-center justify-between px-8 py-5">
            <div className="flex items-center gap-3">
              <Link href="/" className="text-ink-400 transition hover:text-ink-900" aria-label="Back to home">
                <ArrowLeft size={18} />
              </Link>
              <p className="text-[14px] font-semibold text-ink-700">Kimbal Council</p>
            </div>
            {!turn.question && (
              <div className="hidden items-center gap-6 text-[13px] font-semibold text-ink-500 md:flex">
                <span>Discover</span>
                <span>Finance</span>
                <span>Health</span>
                <span>Academic</span>
                <span>Patents</span>
              </div>
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
              <div className="mb-6 w-full space-y-4">
                <div className="flex justify-end">
                  <div className="max-w-[680px] rounded-[18px] rounded-tr-[5px] bg-ink-900 px-5 py-3 text-[14px] font-medium leading-6 text-white shadow-[var(--shadow-pop)]">
                    {turn.question}
                  </div>
                </div>
                <Card className="p-6">
                  <div className="flex items-center gap-2.5">
                    <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-brand-50 text-brand-500">
                      <Sparkles size={15} />
                    </span>
                    <p className="text-[14.5px] font-semibold text-ink-900">Kimbal AI</p>
                  </div>
                  {error ? (
                    <div className="mt-4 rounded-[12px] border border-rose-100 bg-rose-50 px-4 py-3 text-[13px] text-rose-700">
                      {error}
                    </div>
                  ) : (
                    <div className="mt-5 min-h-[180px]">
                      <MarkdownAnswer content={hasAnswer ? turn.answer : ""} busy={busy} />
                    </div>
                  )}
                  <div className="mt-5">{renderActionButtons()}</div>
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
                placeholder="Ask with internal knowledge, web search, or council mode..."
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
            {!turn.question && (
              <div className="mt-6 grid w-full grid-cols-1 gap-3 md:grid-cols-2">
                <button type="button" className="rounded-[14px] border border-line bg-white p-4 text-left shadow-[var(--shadow-card)]">
                  <span className="flex items-center gap-2 text-[14px] font-bold text-ink-900"><Search size={16} /> Search anything</span>
                  <span className="mt-1 block text-[12.5px] text-ink-500">Fast cited answers from trusted internal and web sources.</span>
                </button>
                <button type="button" className="rounded-[14px] border border-line bg-white p-4 text-left shadow-[var(--shadow-card)]">
                  <span className="flex items-center gap-2 text-[14px] font-bold text-ink-900"><Users size={16} /> Council mode</span>
                  <span className="mt-1 block text-[12.5px] text-ink-500">Run a multi-pass answer review with your configured model.</span>
                </button>
              </div>
            )}
            <p className="mt-4 text-[12px] font-semibold text-ink-400">
              Kimbal can make mistakes. Please verify.
            </p>
          </section>
        </main>

        {focusDrawer && (
          <aside className="fixed inset-y-0 right-0 z-50 w-[420px] border-l border-line bg-white p-6 shadow-[0_20px_70px_-42px_rgba(23,26,44,0.45)]">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[17px] font-bold text-ink-900">
                  {focusDrawer === "sources" ? "Sources" : "Past Chats"}
                </p>
                <p className="mt-1 text-[12.5px] text-ink-500">
                  {focusDrawer === "sources"
                    ? "Current answer evidence and web links."
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
            {focusDrawer === "sources" ? renderSourcesList(12) : renderHistoryList()}
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
            Ask Kimbal <span className="font-normal text-ink-500">(Powered by RAG)</span>
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
          {renderModeControls()}
          <p className="text-[12.5px] font-medium text-ink-500">{sourceModeText}</p>
        </div>
        {renderModePanel()}

        {turn.question && (
          <div className="mt-5 flex items-start justify-end gap-3">
            <div>
              <div className="rounded-[16px] rounded-tr-[4px] bg-gradient-to-r from-brand-500 to-brand-600 px-5 py-3.5 text-[14px] font-medium text-white shadow-[var(--shadow-pop)]">
                {turn.question}
              </div>
              <p className="mt-1.5 text-right text-[11.5px] text-ink-400">Now</p>
            </div>
            <span className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-brand-50 text-brand-400">
              <User size={16} />
            </span>
          </div>
        )}

        <Card className="mt-2 p-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-brand-50 text-brand-500">
              <Sparkles size={15} />
            </span>
            <p className="text-[14.5px] font-semibold text-ink-900">Kimbal AI</p>
          </div>

          {error ? (
            <div className="mt-4 rounded-[12px] border border-rose-100 bg-rose-50 px-4 py-3 text-[13px] text-rose-700">
              {error}
            </div>
          ) : (
            <div className="mt-5 min-h-[220px]">
              <MarkdownAnswer content={hasAnswer ? turn.answer : ""} busy={busy} />
            </div>
          )}

          <div className="mt-5 flex items-start gap-2.5 rounded-[12px] border border-brand-100 bg-brand-50/60 px-4 py-3">
            <Info size={15} className="mt-0.5 shrink-0 text-brand-500" />
            <p className="text-[13px] leading-relaxed text-ink-700">
              {sourceModeText} Citation markers such as <span className="font-semibold text-brand-600">[1]</span> map to the source chunks in the right rail.
            </p>
          </div>

          <div className="mt-5">{renderActionButtons()}</div>
        </Card>

        <form
          onSubmit={submit}
          className="mt-5 flex items-center gap-2 rounded-[16px] border border-line bg-white py-1.5 pl-5 pr-1.5 shadow-[var(--shadow-card)] transition focus-within:border-brand-300 focus-within:ring-4 focus-within:ring-brand-50"
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask across synced Jira, Confluence, and uploaded documents..."
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
      </div>

      <div className="col-span-4 space-y-5 animate-rise-1">
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
