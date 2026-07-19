"use client";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type?: string;
};

export type UserOut = {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  default_project_id: string | null;
  created_at: string;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  embedding_model: string;
  access_scope: "organization" | "restricted";
  created_at: string;
};

export type Project = {
  id: string;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
  source_ids: string[];
  authorized_source_ids: string[];
  member_count: number;
  user_project_role: "member" | "manager" | null;
  created_at: string;
  updated_at: string;
};

export type ProjectMember = {
  user_id: string;
  full_name: string;
  email: string;
  project_role: "member" | "manager";
};

export type SourcePermission = {
  knowledge_base_id: string;
  access_scope: "organization" | "restricted";
  user_ids: string[];
};

export type DocumentOut = {
  id: string;
  knowledge_base_id: string;
  collection_id: string | null;
  title: string;
  source_type: string;
  knowledge_base_name: string | null;
  status: string;
  error: string | null;
  current_version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentLineage = {
  id: string;
  knowledge_base_id: string;
  knowledge_base_name: string | null;
  title: string;
  source_type: string;
  source_system: string;
  source_id: string | null;
  source_url: string | null;
  source_version: string | number | null;
  source_updated_at: string | null;
  source_sha256: string | null;
  status: string;
  current_version: number;
  chunk_count: number;
  active_chunk_count: number;
  embedding_model: string | null;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  versions: Array<{
    version: number;
    file_sha256: string;
    file_size_bytes: number;
    created_at: string;
  }>;
};

export type SearchHit = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  score: number;
  dense_score: number;
  sparse_score: number;
};

export type SearchResponse = {
  hits: SearchHit[];
  confidence: number | null;
  timings_ms: Record<string, number>;
};

export type Conversation = {
  id: string;
  knowledge_base_id: string;
  project_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
};

export type CitationOut = {
  chunk_id: string;
  document_id: string;
  marker: number;
  score: number;
  snippet: string;
  document_title?: string | null;
  title?: string | null;
  source_type?: string | null;
  url?: string | null;
};

export type MessageOut = {
  id: string;
  role: "user" | "assistant";
  content: string;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  timings: Record<string, number>;
  model: string | null;
  created_at: string;
  citations: CitationOut[];
};

export type ConfluenceStatus = {
  configured: boolean;
  read_only: boolean;
  base_url: string | null;
  space_key: string;
  default_kb_name: string;
  auth_mode: string;
  email_configured: boolean;
  token_configured: boolean;
  requires_email: boolean;
};

export type ConfluenceSyncedDocument = {
  page_id: string;
  title: string;
  url: string;
  version: number | null;
  document_id: string;
  document_status: string;
  action: "created" | "updated" | "skipped";
};

export type ConfluenceSyncResponse = {
  knowledge_base_id: string;
  knowledge_base_name: string;
  space_key: string;
  space_name: string;
  total_pages: number;
  created: number;
  updated: number;
  skipped: number;
  documents: ConfluenceSyncedDocument[];
};

export type JiraStatus = {
  configured: boolean;
  read_only: boolean;
  base_url: string | null;
  project_key: string;
  board_id: number;
  default_kb_name: string;
  auth_mode: string;
  email_configured: boolean;
  token_configured: boolean;
  using_atlassian_fallback_credentials: boolean;
  requires_email: boolean;
};

export type JiraSyncedDocument = {
  issue_id: string;
  issue_key: string;
  title: string;
  url: string;
  status: string | null;
  updated_at: string | null;
  document_id: string;
  document_status: string;
  action: "created" | "updated" | "skipped";
};

export type JiraSyncResponse = {
  knowledge_base_id: string;
  knowledge_base_name: string;
  project_key: string;
  board_id: number;
  board_name: string;
  total_issues: number;
  created: number;
  updated: number;
  skipped: number;
  documents: JiraSyncedDocument[];
};

export type SourceMetric = {
  knowledge_base_id: string | null;
  name: string;
  source_type: string;
  source_scope: string | null;
  connector: string | null;
  health: string;
  documents: number;
  ready_documents: number;
  pending_documents: number;
  uploaded_documents: number;
  processing_documents: number;
  failed_documents: number;
  chunks_active: number;
  last_updated_at: string | null;
  last_ingested_at: string | null;
  last_run_at: string | null;
  last_run_detail: string | null;
};

export type ConnectorRun = {
  connector: string;
  knowledge_base_id: string | null;
  status: string;
  total: number;
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  detail: string | null;
  created_at: string;
};

export type ActivityMetric = {
  action: string;
  resource_type: string;
  detail: string | null;
  created_at: string;
};

export type QuestionMetric = {
  question: string;
  count: number;
  last_asked_at: string;
};

export type MetricsOverview = {
  knowledge_bases: number;
  documents_total: number;
  documents_ready: number;
  documents_processing: number;
  documents_failed: number;
  chunks_active: number;
  conversations: number;
  questions_asked: number;
  assistant_answers: number;
  active_users: number;
  avg_latency_ms: number | null;
  feedback: {
    helpful: number;
    not_helpful: number;
    total: number;
    helpful_rate: number | null;
  };
  sources: SourceMetric[];
  connector_runs: ConnectorRun[];
  recent_activity: ActivityMetric[];
  top_questions: QuestionMetric[];
};

export type EvalScore = {
  id: string;
  label: string;
  value: number | null;
  display: string;
  status: "good" | "watch" | "needs_attention" | "no_data" | string;
  detail: string;
};

export type EvalLatency = {
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  sample_size: number;
};

export type EvalModel = {
  model: string;
  answers: number;
  avg_latency_ms: number | null;
  citation_coverage: number | null;
  groundedness_score: number | null;
};

export type EvalRecentAnswer = {
  message_id: string;
  conversation_id: string;
  question: string;
  answer_preview: string;
  model: string | null;
  created_at: string;
  latency_ms: number | null;
  citations: number;
  groundedness_score: number | null;
  relevance_score: number | null;
  unsupported_claim_rate: number | null;
  source_mode: string;
  answer_mode: string;
  verdict: "healthy" | "needs_review" | "failure" | "unknown" | string;
  issues: string[];
};

export type EvalMode = {
  source_mode: string;
  answer_mode: string;
  answers: number;
  avg_latency_ms: number | null;
  groundedness_score: number | null;
  unsupported_claim_rate: number | null;
  failure_rate: number | null;
};

export type EvalQuality = {
  evaluated: number;
  healthy: number;
  needs_review: number;
  failures: number;
  issue_counts: Record<string, number>;
};

export type EvalBenchmarkComponent = {
  id: string;
  label: string;
  value: number | null;
  weight: number;
  display: string;
};

export type EvalBenchmark = {
  label: string;
  score: number | null;
  value: number | null;
  display: string;
  status: "good" | "watch" | "needs_attention" | "no_data" | string;
  sample_size: number;
  detail: string;
  components: EvalBenchmarkComponent[];
};

export type GoldenEvalCase = {
  id: string;
  category: string;
  question: string;
  expected_source_types: string[];
  expected_answer_traits: string[];
  tags: string[];
};

export type GoldenEvalDataset = {
  dataset_path: string;
  cases: number;
  categories: Record<string, number>;
  source_types: Record<string, number>;
  benchmark_ready: boolean;
  run_command: string;
  sample: GoldenEvalCase[];
};

export type EvalGateMetric = {
  id: string;
  label: string;
  value: number | null;
  display: string;
  threshold: number | null;
  passed: boolean;
  detail: string;
};

export type EvalGateCase = {
  id: string;
  category: string;
  question: string;
  passed: boolean;
  expected_sources: string[];
  returned_sources: string[];
  returned_source_titles: string[];
  answer_text: string;
  judge_rationale: string;
  latency_ms: number;
  scores: Record<string, number | null>;
  model_comparison: Record<string, number | string | null>;
  role_space_checks: Record<string, boolean>;
};

export type EvalGateRun = {
  generated_at: string;
  dataset_path: string;
  cases: number;
  passed: boolean;
  score: number | null;
  display: string;
  thresholds: Record<string, number>;
  metrics: EvalGateMetric[];
  failing_cases: EvalGateCase[];
  cases_detail: EvalGateCase[];
  regression_trend: Record<string, number | string | null>[];
  methodology: string[];
};

export type EvalOverview = {
  generated_at: string;
  answers_total: number;
  sample_size: number;
  benchmark: EvalBenchmark;
  golden_dataset: GoldenEvalDataset;
  feedback: {
    helpful: number;
    not_helpful: number;
    total: number;
    helpful_rate: number | null;
  };
  scores: EvalScore[];
  latency: EvalLatency;
  models: EvalModel[];
  modes: EvalMode[];
  quality: EvalQuality;
  recent_answers: EvalRecentAnswer[];
  methodology: string[];
};

export type SourceMode = "knowledge" | "web" | "blended";
export type AnswerMode = "fast" | "council";

export type WebSearchStatus = {
  configured: boolean;
  provider: string;
  default_kb_name: string;
  top_k: number;
  reason: string;
};

export type WebSearchTest = {
  ok: boolean;
  provider: string;
  latency_ms: number;
  result_count: number;
  results: Array<{ title: string; url: string }>;
};

export type RuntimeConfig = {
  app_env: string;
  auth_disabled: boolean;
  retrieval: { top_k: number; candidate_k: number; dense_weight: number; sparse_weight: number };
  chunking: Record<string, {
    profile: string;
    size_tokens: number;
    overlap_tokens: number;
    excluded_issue_types?: string[];
    comments_indexed?: boolean;
    attachments_extracted?: boolean;
  }>;
  web: { provider: string; top_k: number; configured: boolean };
  council: { enabled: boolean; models: string[]; chair_model: string | null };
};

export type DiscoverDepartment = {
  id: string;
  label: string;
  description: string;
  query: string;
};

export type DiscoverArticle = {
  id: string;
  title: string;
  url: string;
  source: string;
  summary: string;
  section: "articles" | "alerts" | "research" | string;
  department: string;
  published_at: string | null;
  score: number;
};

export type DiscoverBoardItem = {
  title: string;
  url: string | null;
  source_type: string;
  status: string;
  updated_at: string;
};

export type DiscoverFeed = {
  generated_at: string;
  provider: string;
  configured: boolean;
  department: string;
  departments: DiscoverDepartment[];
  lead: DiscoverArticle | null;
  articles: DiscoverArticle[];
  alerts: DiscoverArticle[];
  research: DiscoverArticle[];
  board_pulse: {
    jira_documents: number;
    confluence_documents: number;
    upload_documents: number;
    web_documents: number;
    latest_items: DiscoverBoardItem[];
  };
  warnings: string[];
};

export type ChatCapabilities = {
  answer_modes: AnswerMode[];
  council_configured: boolean;
  council_models: string[];
  council_available_models: string[];
  council_chair_model: string | null;
  council_reason: string;
};

export type RagSource = {
  chunk_id: string;
  document_id: string;
  document_title?: string;
  title?: string;
  marker?: number;
  score?: number;
  dense_score?: number;
  sparse_score?: number;
  snippet?: string;
  content?: string;
  source_type?: string;
  url?: string;
  source_updated_at?: string | null;
  freshness_label?: string;
};

export type AskStreamEvent =
  | {
      type: "sources";
      data: {
        sources?: RagSource[];
        hits?: RagSource[];
        source_mode?: SourceMode;
        answer_mode?: AnswerMode;
        query_classification?: string;
      };
    }
  | { type: "delta"; data: { text?: string; delta?: string; content?: string } }
  | {
      type: "done";
      data: {
        answer?: string;
        message_id?: string;
        timings_ms?: Record<string, number>;
        citations?: RagSource[];
        model?: string | null;
        source_mode?: SourceMode;
        answer_mode?: AnswerMode;
        query_classification?: string;
      };
    }
  | { type: "error"; data: { code?: string; message?: string } };

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  auth?: boolean;
};

export type CouncilConfig = {
  models: string[];
  chairModel: string;
};

export type AssistantRoleConfig = {
  name: string;
  prompt: string;
};

export type RoleGenerateInput = {
  name: string;
  goal: string;
  sourceFocus: string;
  outputStyle: string;
};

export type UserCreateInput = {
  email: string;
  password: string;
  full_name: string;
  role: "admin" | "editor" | "viewer";
};

const API_BASE =
  process.env.NEXT_PUBLIC_CVUM_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";
const SESSION_KEY = "kimbal.local.session.v1";
const PREFERRED_KB_NAMES = ["Jira DEVO", "Confluence DevOps1", "CVUM Local Uploads"];
const SESSION_CACHE_MS = 30_000;
const LIVE_CACHE_MS = 15_000;

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function readJson<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

function writeJson(key: string, value: unknown) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(key, JSON.stringify(value));
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `${response.status} ${response.statusText}`;
  let code: string | undefined;
  try {
    const payload = await response.json();
    message = payload?.error?.message ?? payload?.detail ?? message;
    code = payload?.error?.code;
  } catch {
    const text = await response.text().catch(() => "");
    if (text) message = text;
  }
  return new ApiError(message, response.status, code);
}

export class CVUMApi {
  private token: TokenPair | null = readJson<TokenPair>(SESSION_KEY);
  private sessionPromise: Promise<UserOut> | null = null;
  private sessionUser: UserOut | null = null;
  private sessionCheckedAt = 0;
  private liveCache = new Map<string, { expiresAt: number; value: unknown }>();

  get baseUrl() {
    return API_BASE;
  }

  get accessToken() {
    return this.token?.access_token ?? null;
  }

  hasSession() {
    return Boolean(this.token?.access_token);
  }

  setSession(token: TokenPair) {
    this.token = token;
    this.sessionUser = null;
    this.sessionCheckedAt = 0;
    writeJson(SESSION_KEY, token);
  }

  clearSession() {
    this.token = null;
    this.sessionUser = null;
    this.sessionCheckedAt = 0;
    this.clearLiveCache();
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(SESSION_KEY);
    }
  }

  private clearLiveCache() {
    this.liveCache.clear();
  }

  refreshLiveData() {
    this.clearLiveCache();
  }

  private async cached<T>(key: string, ttlMs: number, loader: () => Promise<T>): Promise<T> {
    const cached = this.liveCache.get(key);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.value as T;
    }
    const value = await loader();
    this.liveCache.set(key, { value, expiresAt: Date.now() + ttlMs });
    return value;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const headers = new Headers(options.headers);
    if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (options.auth !== false && this.token?.access_token) {
      headers.set("Authorization", `Bearer ${this.token.access_token}`);
    }
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      body: options.body instanceof FormData ? options.body : JSON.stringify(options.body),
    });
    if (response.status === 204) return undefined as T;
    if (!response.ok) throw await parseError(response);
    return (await response.json()) as T;
  }

  async form<T>(path: string, body: URLSearchParams): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!response.ok) throw await parseError(response);
    return (await response.json()) as T;
  }

  async ensureSession(): Promise<UserOut> {
    if (!this.sessionPromise) {
      this.sessionPromise = this.ensureSessionOnce().finally(() => {
        this.sessionPromise = null;
      });
    }
    return this.sessionPromise;
  }

  private async ensureSessionOnce(): Promise<UserOut> {
    if (this.sessionUser && Date.now() - this.sessionCheckedAt < SESSION_CACHE_MS) {
      return this.sessionUser;
    }
    try {
      const user = await this.request<UserOut>("/auth/me");
      this.sessionUser = user;
      this.sessionCheckedAt = Date.now();
      return user;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        this.clearSession();
      }
      throw error;
    }
  }

  async login(email: string, password: string): Promise<UserOut> {
    const body = new URLSearchParams();
    body.set("username", email.trim().toLowerCase());
    body.set("password", password);
    const token = await this.form<TokenPair>("/auth/login", body);
    this.setSession(token);
    return this.ensureSession();
  }

  async logout() {
    try {
      if (this.hasSession()) {
        await this.request<void>("/auth/logout", { method: "POST" });
      }
    } finally {
      this.clearSession();
    }
  }

  async listKnowledgeBases() {
    return this.request<KnowledgeBase[]>("/knowledge-bases");
  }

  async ensureKnowledgeBase(projectId?: string): Promise<KnowledgeBase> {
    await this.ensureSession();
    const [existing, projects] = await Promise.all([
      this.listKnowledgeBases(),
      projectId ? this.listProjects() : Promise.resolve([]),
    ]);
    const project = projects.find((item) => item.id === projectId);
    const scoped = project
      ? existing.filter((item) => project.authorized_source_ids.includes(item.id))
      : existing;
    const kb = PREFERRED_KB_NAMES.map((name) => scoped.find((item) => item.name === name)).find(Boolean) ?? scoped[0];
    if (kb) return kb;
    return this.request<KnowledgeBase>("/knowledge-bases", {
      method: "POST",
      body: {
        name: "CVUM Local Uploads",
        description: "Operator-uploaded documents used when no external knowledge base has been synced yet.",
      },
    });
  }

  async ensureUploadKnowledgeBase(projectId?: string): Promise<KnowledgeBase> {
    await this.ensureSession();
    const existing = await this.listKnowledgeBases();
    let kb = existing.find((item) => item.name === "CVUM Local Uploads");
    if (!kb) {
      kb = await this.request<KnowledgeBase>("/knowledge-bases", {
        method: "POST",
        body: {
          name: "CVUM Local Uploads",
          description: "Operator-uploaded documents kept separate from read-only external source syncs.",
        },
      });
    }
    if (projectId) {
      const project = (await this.listProjects()).find((item) => item.id === projectId);
      if (project && !project.source_ids.includes(kb.id)) {
        await this.updateProjectSources(project.id, [...project.source_ids, kb.id]);
      }
    }
    return kb;
  }

  async listDocuments(kbId?: string, limit = 50, offset = 0) {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    if (kbId) params.set("knowledge_base_id", kbId);
    return this.request<{ items: DocumentOut[]; total: number }>(`/documents?${params.toString()}`);
  }

  async documentLineage(documentId: string) {
    return this.request<DocumentLineage>(`/documents/${encodeURIComponent(documentId)}/lineage`);
  }

  async getDocument(documentId: string) {
    return this.request<DocumentOut>(`/documents/${encodeURIComponent(documentId)}`);
  }

  async uploadDocument(kbId: string, file: File) {
    const form = new FormData();
    form.set("knowledge_base_id", kbId);
    form.set("file", file);
    return this.request<DocumentOut>("/documents/upload", {
      method: "POST",
      body: form,
    });
  }

  async reindexDocument(documentId: string) {
    return this.request<DocumentOut>(`/documents/${documentId}/reindex`, {
      method: "POST",
    });
  }

  async deleteDocument(documentId: string) {
    return this.request<void>(`/documents/${documentId}`, {
      method: "DELETE",
    });
  }

  async search(kbId: string, query: string, topK = 6) {
    return this.request<SearchResponse>("/search", {
      method: "POST",
      body: {
        knowledge_base_id: kbId,
        query,
        top_k: topK,
      },
    });
  }

  async listProjects() {
    return this.request<Project[]>("/projects");
  }

  async createProject(input: { name: string; slug?: string; description?: string }) {
    const project = await this.request<Project>("/projects", {
      method: "POST",
      body: input,
    });
    this.clearLiveCache();
    return project;
  }

  async updateProject(
    projectId: string,
    input: Partial<Pick<Project, "name" | "slug" | "description" | "is_active">>
  ) {
    const project = await this.request<Project>(`/projects/${encodeURIComponent(projectId)}`, {
      method: "PATCH",
      body: input,
    });
    this.clearLiveCache();
    return project;
  }

  async deleteProject(projectId: string) {
    await this.request<void>(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
    this.clearLiveCache();
  }

  async updateProjectSources(projectId: string, knowledgeBaseIds: string[]) {
    const project = await this.request<Project>(`/projects/${encodeURIComponent(projectId)}/sources`, {
      method: "PUT",
      body: { knowledge_base_ids: knowledgeBaseIds },
    });
    this.clearLiveCache();
    return project;
  }

  async listProjectMembers(projectId: string) {
    return this.request<ProjectMember[]>(`/projects/${encodeURIComponent(projectId)}/members`);
  }

  async updateProjectMembers(
    projectId: string,
    members: Array<{ user_id: string; project_role: "member" | "manager" }>
  ) {
    const result = await this.request<ProjectMember[]>(`/projects/${encodeURIComponent(projectId)}/members`, {
      method: "PUT",
      body: { members },
    });
    this.clearLiveCache();
    return result;
  }

  async setDefaultProject(projectId: string) {
    const project = await this.request<Project>("/users/me/default-project", {
      method: "PUT",
      body: { project_id: projectId },
    });
    this.sessionUser = this.sessionUser
      ? { ...this.sessionUser, default_project_id: project.id }
      : null;
    this.sessionCheckedAt = Date.now();
    this.clearLiveCache();
    return project;
  }

  async sourcePermissions(knowledgeBaseId: string) {
    return this.request<SourcePermission>(
      `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/permissions`
    );
  }

  async updateSourcePermissions(
    knowledgeBaseId: string,
    accessScope: "organization" | "restricted",
    userIds: string[]
  ) {
    const result = await this.request<SourcePermission>(
      `/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/permissions`,
      {
        method: "PUT",
        body: { access_scope: accessScope, user_ids: userIds },
      }
    );
    this.clearLiveCache();
    return result;
  }

  async createConversation(kbId: string, title: string, projectId?: string) {
    return this.request<Conversation>("/conversations", {
      method: "POST",
      body: {
        knowledge_base_id: kbId,
        project_id: projectId ?? null,
        title,
      },
    });
  }

  async listConversations() {
    return this.request<Conversation[]>("/conversations?limit=25");
  }

  async listMessages(conversationId: string) {
    return this.request<MessageOut[]>(`/conversations/${encodeURIComponent(conversationId)}/messages`);
  }

  async deleteConversation(conversationId: string) {
    await this.request<void>(`/conversations/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
    });
    this.clearLiveCache();
  }

  async clearConversationHistory(conversationId: string) {
    await this.request<void>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "DELETE",
    });
    this.clearLiveCache();
  }

  async listUsers() {
    return this.request<UserOut[]>("/admin/users?limit=200");
  }

  async runtimeConfig() {
    return this.cached("runtimeConfig", LIVE_CACHE_MS, () =>
      this.request<RuntimeConfig>("/admin/runtime-config")
    );
  }

  async createUser(input: UserCreateInput) {
    const user = await this.request<UserOut>("/admin/users", {
      method: "POST",
      body: input,
    });
    this.clearLiveCache();
    return user;
  }

  async updateUserRole(userId: string, role: "admin" | "editor" | "viewer") {
    const user = await this.request<UserOut>(`/admin/users/${userId}/role`, {
      method: "PATCH",
      body: { role },
    });
    this.clearLiveCache();
    return user;
  }

  async submitFeedback(messageId: string, rating: 1 | -1, comment?: string) {
    const result = await this.request<{ status: string }>("/feedback", {
      method: "POST",
      body: {
        message_id: messageId,
        rating,
        comment,
      },
    });
    this.clearLiveCache();
    return result;
  }

  async confluenceStatus() {
    return this.cached("confluenceStatus", LIVE_CACHE_MS, () => this.request<ConfluenceStatus>("/confluence/status"));
  }

  async syncConfluence(kbId?: string, maxPages?: number) {
    const body: { knowledge_base_id: string | null; max_pages?: number } = {
      knowledge_base_id: kbId ?? null,
    };
    if (maxPages !== undefined) body.max_pages = maxPages;
    const result = await this.request<ConfluenceSyncResponse>("/confluence/sync", {
      method: "POST",
      body,
    });
    this.clearLiveCache();
    return result;
  }

  async jiraStatus() {
    return this.cached("jiraStatus", LIVE_CACHE_MS, () => this.request<JiraStatus>("/jira/status"));
  }

  async syncJira(kbId?: string, maxIssues?: number) {
    const body: { knowledge_base_id: string | null; max_issues?: number } = {
      knowledge_base_id: kbId ?? null,
    };
    if (maxIssues !== undefined) body.max_issues = maxIssues;
    const result = await this.request<JiraSyncResponse>("/jira/sync", {
      method: "POST",
      body,
    });
    this.clearLiveCache();
    return result;
  }

  async metricsOverview() {
    return this.cached("metricsOverview", LIVE_CACHE_MS, () => this.request<MetricsOverview>("/metrics/overview"));
  }

  async evalsOverview() {
    return this.cached("evalsOverview", LIVE_CACHE_MS, () => this.request<EvalOverview>("/evals/overview"));
  }

  async evalsOfflineGate() {
    return this.cached("evalsOfflineGate", LIVE_CACHE_MS, () => this.request<EvalGateRun>("/evals/offline"));
  }

  async webSearchStatus() {
    return this.cached("webSearchStatus", LIVE_CACHE_MS, () => this.request<WebSearchStatus>("/web-search/status"));
  }

  async testWebSearch() {
    const result = await this.request<WebSearchTest>("/web-search/test", { method: "POST" });
    this.clearLiveCache();
    return result;
  }

  async discoverFeed(department = "for-you") {
    return this.cached(`discoverFeed:${department}`, LIVE_CACHE_MS, () =>
      this.request<DiscoverFeed>(`/discover/feed?department=${encodeURIComponent(department)}`)
    );
  }

  async chatCapabilities() {
    return this.cached("chatCapabilities", LIVE_CACHE_MS, () => this.request<ChatCapabilities>("/chat/capabilities"));
  }

  async generateRolePrompt(input: RoleGenerateInput) {
    return this.request<AssistantRoleConfig>("/chat/roles/generate", {
      method: "POST",
      body: {
        name: input.name,
        goal: input.goal,
        source_focus: input.sourceFocus,
        output_style: input.outputStyle,
      },
    });
  }

  async *ask(
    conversationId: string,
    question: string,
    sourceMode: SourceMode = "knowledge",
    answerMode: AnswerMode = "fast",
    council?: CouncilConfig,
    assistantRole?: AssistantRoleConfig,
    projectId?: string
  ): AsyncGenerator<AskStreamEvent> {
    const body: {
      question: string;
      source_mode: SourceMode;
      answer_mode: AnswerMode;
      assistant_role?: string;
      assistant_role_prompt?: string;
      council_models?: string[];
      council_chair_model?: string;
      project_id?: string;
    } = { question, source_mode: sourceMode, answer_mode: answerMode };
    if (projectId) body.project_id = projectId;
    if (assistantRole?.name && assistantRole.prompt) {
      body.assistant_role = assistantRole.name;
      body.assistant_role_prompt = assistantRole.prompt;
    }
    if (answerMode === "council" && council) {
      body.council_models = council.models;
      body.council_chair_model = council.chairModel;
    }
    const headers = new Headers({ "Content-Type": "application/json" });
    if (this.token?.access_token) {
      headers.set("Authorization", `Bearer ${this.token.access_token}`);
    }
    const response = await fetch(`${API_BASE}/conversations/${conversationId}/ask`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!response.ok || !response.body) throw await parseError(response);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = decodeSseFrame(frame);
        if (event) yield event;
      }
    }
    const finalEvent = decodeSseFrame(buffer);
    if (finalEvent) yield finalEvent;
  }
}

function decodeSseFrame(frame: string): AskStreamEvent | null {
  if (!frame.trim()) return null;
  let type = "message";
  const data: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!data.length) return null;
  try {
    return { type, data: JSON.parse(data.join("\n")) } as AskStreamEvent;
  } catch {
    return { type: "error", data: { message: data.join("\n") } };
  }
}

export const kimbalApi = new CVUMApi();
