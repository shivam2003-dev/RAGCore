# RAGCore / CVUM — Multi-Level System Design

**Diagram-first design snapshot:** 2026-07-20

**Legend:** blue/solid = **CURRENT**; amber/dashed = **PROPOSED / PHASED**.
**Companion:** `diagram.md` is the synchronized diagram-atlas edition of this complete visual set.

```mermaid
flowchart LR
    CUR["CURRENT<br/>verified in repository"]
    PROP["PROPOSED / PHASED<br/>requires implementation and gates"]
    INV["INVARIANT<br/>must remain true"]
    CUR --> INV
    PROP -.must preserve.-> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class CUR current
    class PROP proposed
    class INV invariant
```

## Design map

```mermaid
flowchart TB
    L0["L0 · System context"]
    L1["L1 · Containers and deployment"]
    L2["L2 · Frontend/backend components"]
    L3["L3 · Module and runtime flows"]
    AI["AI · Retrieval, ranking, context, generation"]
    DATA["Data · Models, tenancy, ACLs, cache"]
    OPS["Ops · Telemetry, evals, scale, DR, CI/CD"]

    L0 --> L1 --> L2 --> L3
    L3 --> AI
    L3 --> DATA
    AI --> OPS
    DATA --> OPS
```

## L0 — System context

```mermaid
flowchart LR
    User["Employee / Knowledge User"]
    Admin["Administrator / Editor"]
    Agent["External AI Client<br/>MCP"]
    CVUM["RAGCore Platform<br/>CVUM Assistant"]

    Sources["Enterprise Sources<br/>Confluence · Jira · Slack · GitHub"]
    Uploads["User Uploads"]
    Web["Explicit Web Search"]
    AI["LLM and Embedding Providers"]
    Obs["Metrics · Traces · Logs"]

    User -->|"Ask · search · workflows"| CVUM
    Admin -->|"Projects · grants · connectors · health"| CVUM
    Agent -->|"Authenticated read-only tools"| CVUM
    Uploads -->|"Validated document versions"| CVUM
    Sources -->|"Read-only sync/events"| CVUM
    Web -->|"Web/blended mode only"| CVUM
    CVUM -->|"Bounded prompts / embedding text"| AI
    CVUM --> Obs
    CVUM -->|"Cited, authorized answers"| User

    INV["INVARIANT<br/>Project narrows relevance;<br/>it never grants permission"]
    CVUM --> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class CVUM,User,Admin,Agent,Sources,Uploads,Web,AI,Obs current
    class INV invariant
```

## L1 — Current containers

```mermaid
flowchart TB
    Browser["Browser"]

    subgraph Current["CURRENT · Runtime containers"]
        Next["Next.js Web<br/>app/ · components/"]
        API["FastAPI API<br/>backend/api/main.py"]
        BG["In-process Background Tasks<br/>BackgroundTasksQueue"]
        PG[("PostgreSQL + pgvector<br/>metadata · FTS · HNSW")]
        Redis[("Redis<br/>cache · rate limit · embedding cache")]
        Files[("Local Version Files<br/>UPLOAD_DIR")]
        MCP["MCP stdio bridge<br/>run_mcp_server.py"]
    end

    Browser -->|"HTTPS / SSE"| Next
    Next -->|"REST / SSE"| API
    MCP -->|"Authenticated evidence REST"| API
    API --> PG
    API --> Redis
    API --> Files
    API --> BG
    BG --> PG
    BG --> Files
    BG --> Redis

    Providers["LLM · Embedding · Source APIs"]
    API --> Providers
    BG --> Providers

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    class Browser,Next,API,BG,PG,Redis,Files,MCP,Providers current
```

## L1 — Proposed production containers

```mermaid
flowchart TB
    Edge["Ingress / WAF / TLS"]
    Web["Stateless Web"]
    API["Stateless API / SSE"]
    Outbox[("PostgreSQL Outbox")]
    Queue[("Durable Queue")]
    WorkerIO["Connector Workers"]
    WorkerExtract["Extraction / OCR Workers"]
    WorkerEmbed["Embedding / Index Workers"]
    Reconcile["Reconciliation Workers"]
    PG[("Managed PostgreSQL + pgvector<br/>PITR · pooler · replica")]
    Redis[("HA Redis")]
    Object[("Versioned Object Storage")]
    Secrets["Secret Manager / Workload Identity"]
    Telemetry["OTel · Prometheus · Logs"]

    Edge --> Web
    Edge --> API
    Web --> API
    API --> PG
    API --> Outbox
    Outbox --> Queue
    Queue --> WorkerIO
    Queue --> WorkerExtract
    Queue --> WorkerEmbed
    Queue --> Reconcile
    WorkerIO --> PG
    WorkerExtract --> PG
    WorkerEmbed --> PG
    Reconcile --> PG
    API --> Redis
    WorkerEmbed --> Redis
    WorkerIO --> Object
    WorkerExtract --> Object
    API --> Secrets
    WorkerIO --> Secrets
    WorkerEmbed --> Secrets
    API --> Telemetry
    WorkerIO --> Telemetry
    WorkerExtract --> Telemetry
    WorkerEmbed --> Telemetry

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Edge,Web,API,Outbox,Queue,WorkerIO,WorkerExtract,WorkerEmbed,Reconcile,PG,Redis,Object,Secrets,Telemetry proposed
```

## L2 — Backend components

```mermaid
flowchart LR
    subgraph Transport["CURRENT · Transport"]
        Routes["API Routers<br/>backend/api/routes/"]
        Schemas["Pydantic Schemas<br/>backend/api/schemas.py"]
        Deps["Composition Root<br/>backend/api/deps.py"]
        MW["Middleware<br/>rate limit · observability"]
    end

    subgraph UseCases["CURRENT · Use cases"]
        Auth["AuthService"]
        Docs["DocumentService"]
        Connect["Connector Services"]
        Chat["ChatService"]
        Workflows["KnowledgeWorkflowService"]
        Evidence["Evidence Planner / Executor / Tools"]
    end

    subgraph Intelligence["CURRENT · Intelligence"]
        Retrieve["RetrievalPipeline"]
        CRAG["CRAG policy"]
        Rank["Fusion / Rerankers"]
        Generate["ResponseGenerator"]
        Prompt["Prompt + Citation Controls"]
    end

    subgraph Persistence["CURRENT · Persistence"]
        Repos["Repositories"]
        Models["SQLAlchemy Models"]
        DB[("PostgreSQL")]
        Cache[("Redis")]
    end

    subgraph Providers["CURRENT · Provider seams"]
        Embed["EmbeddingProvider"]
        LLM["LLMProvider"]
        Source["Read-only Source Clients"]
    end

    Routes --> Schemas
    Routes --> Deps
    MW --> Routes
    Deps --> UseCases
    Chat --> Retrieve
    Chat --> Evidence
    Chat --> Generate
    Retrieve --> CRAG
    Retrieve --> Rank
    Generate --> Prompt
    Docs --> Repos
    Connect --> Docs
    Connect --> Source
    Retrieve --> Repos
    Retrieve --> Embed
    Generate --> LLM
    Evidence --> Repos
    Repos --> Models --> DB
    UseCases --> Cache

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    class Routes,Schemas,Deps,MW,Auth,Docs,Connect,Chat,Workflows,Evidence,Retrieve,CRAG,Rank,Generate,Prompt,Repos,Models,DB,Cache,Embed,LLM,Source current
```

## L2 — Frontend components

```mermaid
flowchart TB
    App["Next.js App Router<br/>app/"]
    Shell["Auth + Admin Shell<br/>components/auth-shell.tsx"]
    Nav["Sidebar + Topbar<br/>components/sidebar.tsx<br/>components/topbar.tsx"]
    Ask["Ask / Chat<br/>home-client · chat-ask-client · home-ask"]
    Sources["Knowledge Operations<br/>knowledge-sources · documents · data-sources"]
    Governance["Governance<br/>projects · access-control · settings"]
    Quality["Quality<br/>evals · analytics · feedback · usage"]
    Workflow["Workflows<br/>incident · who-knows · what-changed · freshness"]
    API["Backend REST / SSE"]
    Local["Local UI Preferences<br/>settings-store"]

    App --> Shell --> Nav
    Shell --> Ask
    Shell --> Sources
    Shell --> Governance
    Shell --> Quality
    Shell --> Workflow
    Ask --> API
    Sources --> API
    Governance --> API
    Quality --> API
    Workflow --> API
    Shell --> Local

    INV["INVARIANT<br/>Frontend selects scope;<br/>backend resolves authority"]
    Governance --> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class App,Shell,Nav,Ask,Sources,Governance,Quality,Workflow,API,Local current
    class INV invariant
```

## L3 — Backend dependency flow

```mermaid
flowchart LR
    Route["Route<br/>transport only"]
    Service["Service<br/>use-case policy"]
    Repo["Repository<br/>SQL boundary"]
    Model["Model<br/>relational invariant"]
    Provider["Provider Protocol<br/>external dependency seam"]

    Route --> Service --> Repo --> Model
    Service --> Provider

    Bad1["No route-owned business policy"]
    Bad2["No prompt-owned authorization"]
    Bad3["No concurrent SQL on one AsyncSession"]

    Route -.guard.-> Bad1
    Service -.guard.-> Bad2
    Repo -.guard.-> Bad3

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Route,Service,Repo,Model,Provider current
    class Bad1,Bad2,Bad3 invariant
```

## Upload and ingestion — Current

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant API as documents route
    participant DS as DocumentService
    participant DB as PostgreSQL
    participant FS as UPLOAD_DIR
    participant Q as BackgroundTasksQueue
    participant IP as ingest_document
    participant EX as Extractor / Chunker
    participant EM as EmbeddingProvider

    Admin->>API: POST document upload
    API->>DS: upload(user, KB, file)
    DS->>DS: suffix + size + non-empty + magic/UTF-8
    DS->>DS: SHA-256 + normalized metadata
    DS->>DB: create Document + DocumentVersion
    DS->>FS: write immutable version file
    DS->>DB: commit
    DS->>Q: enqueue ingest_document
    API-->>Admin: accepted document state
    Q->>IP: await async background job
    IP->>DB: new session and status PROCESSING
    IP->>EX: extract + source-aware chunk
    IP->>EM: embed batches
    IP->>DB: deactivate prior chunks + insert new chunks
    IP->>DB: status READY and commit
    alt extraction or provider failure
        IP->>DB: rollback, status FAILED + bounded error
    end
```

Paths: `backend/services/document_service.py:DocumentService`, `backend/ingestion/queue.py`, `backend/ingestion/pipeline.py:ingest_document`.

## Ingestion — Proposed durable pipeline

```mermaid
flowchart LR
    API["API validation"]
    TX["One DB transaction<br/>version + outbox"]
    Outbox[("Outbox")]
    Queue[("Durable queue")]
    Lease["Worker lease<br/>idempotency key"]
    Artifact[("Object version<br/>URI + checksum")]
    Extract["Sandboxed extraction<br/>limits + malware scan"]
    Context["Contextualization<br/>versioned template/model"]
    Chunk["Structure-aware chunks<br/>manifest"]
    Embed["Batch embeddings<br/>model/text hash cache"]
    Stage["Inactive staging revision"]
    Verify["Count · dimension · lineage checks"]
    Active["Atomic activation"]
    Reconcile["Expired lease / stuck-job reconciler"]

    API --> TX
    TX --> Outbox --> Queue --> Lease
    TX --> Artifact
    Lease --> Artifact --> Extract --> Context --> Chunk --> Embed --> Stage --> Verify --> Active
    Reconcile -.reclaim.-> Lease
    Reconcile -.repair.-> Stage

    INV["INVARIANT<br/>Old active version survives<br/>until new revision is valid"]
    Verify --> INV

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class API,TX,Outbox,Queue,Lease,Artifact,Extract,Context,Chunk,Embed,Stage,Verify,Active,Reconcile proposed
    class INV invariant
```

## Source-aware normalization

```mermaid
flowchart TB
    Upload["Upload"]
    Confluence["Confluence page"]
    Jira["Jira issue family<br/>comments + attachments"]
    Slack["Allowlisted public<br/>Slack thread"]
    GitHub["Allowed GitHub path<br/>blob + commit"]
    Web["Explicit web result"]

    Normalize["Canonical source metadata<br/>source ID · URL · version · updated time<br/>connector · scope · ACL · checksum"]
    Profile{"Source profile"}
    Markdown["Heading-aware chunking"]
    JiraChunk["Relationship-aware 320/40"]
    SlackChunk["Thread summary + bursts + raw text"]
    CodeChunk["Symbol / language-aware code chunks"]
    Generic["Recursive chunking"]
    Context["Deterministic context prefix"]
    Document["Document → Version → Active Chunks"]

    Upload --> Normalize
    Confluence --> Normalize
    Jira --> Normalize
    Slack --> Normalize
    GitHub --> Normalize
    Web --> Normalize
    Normalize --> Profile
    Profile -->|Confluence / Markdown| Markdown
    Profile -->|Jira| JiraChunk
    Profile -->|Slack| SlackChunk
    Profile -->|GitHub code| CodeChunk
    Profile -->|Other| Generic
    Markdown --> Context
    JiraChunk --> Context
    SlackChunk --> Context
    CodeChunk --> Context
    Generic --> Context
    Context --> Document

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    class Upload,Confluence,Jira,Slack,GitHub,Web,Normalize,Profile,Markdown,JiraChunk,SlackChunk,CodeChunk,Generic,Context,Document current
```

## Connector control contract

```mermaid
flowchart LR
    Configure["Validate configuration"]
    Discover["Discover cursor / snapshot"]
    Policy["Apply source + path + ACL policy"]
    Fetch["Fetch immutable content"]
    Normalize["Normalize provenance"]
    Version["Create / update / skip"]
    Index["Schedule ingestion"]
    Delete["Tombstone + deactivate"]
    Checkpoint["Commit checkpoint"]
    Status["Sanitized status + lag"]
    Reconcile["Full inventory reconcile"]

    Configure --> Discover --> Policy
    Policy -->|allowed| Fetch --> Normalize --> Version --> Index --> Checkpoint --> Status
    Policy -->|removed / denied| Delete --> Checkpoint
    Reconcile --> Discover
    Status --> Reconcile

    INV["INVARIANT<br/>Credentials never enter connector status,<br/>audit detail, document metadata, or prompts"]
    Configure --> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Configure,Discover,Policy,Fetch,Normalize,Version,Index,Delete,Checkpoint,Status current
    class Reconcile proposed
    class INV invariant
```

## GitHub repository sync — Current

```mermaid
flowchart TB
    Request["Admin sync request"]
    Scope["ProjectAuthorizationRepository.require_source"]
    Lease["Atomic acquire lease<br/>lease ID + expiry"]
    Branch["Read branch snapshot<br/>commit SHA + tree SHA"]
    Existing["Bulk file states + active documents"]
    Same{"Tree unchanged and<br/>all documents ready?"}
    Tree["Read bounded recursive tree"]
    Policy["Path policy<br/>allow · deny · size · binary · secret/generated"]
    Owners["CODEOWNERS + contributors"]
    Compare{"Path/blob state"}
    Skip["Skip unchanged ready/recent job"]
    Reindex["Requeue unchanged non-ready doc"]
    Rename["Adopt rename by blob SHA"]
    Upsert["Fetch text blob + version document"]
    Remove["Soft-delete missing / denied"]
    Orphans["Bulk orphan cleanup"]
    Success["Complete owned lease<br/>commit/tree checkpoint"]
    Fail["Fail owned lease<br/>sanitized error"]

    Request --> Scope --> Lease --> Branch --> Existing --> Same
    Same -->|yes| Orphans --> Success
    Same -->|no| Tree --> Policy --> Owners --> Compare
    Compare -->|same blob| Skip
    Compare -->|same blob but not ready| Reindex
    Compare -->|blob moved| Rename
    Compare -->|new or changed| Upsert
    Compare -->|missing| Remove
    Skip --> Orphans
    Reindex --> Orphans
    Rename --> Orphans
    Upsert --> Orphans
    Remove --> Orphans
    Lease -.exception / cancellation.-> Fail
    Branch -.exception.-> Fail
    Tree -.exception.-> Fail
    Upsert -.exception.-> Fail

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    class Request,Scope,Lease,Branch,Existing,Same,Tree,Policy,Owners,Compare,Skip,Reindex,Rename,Upsert,Remove,Orphans,Success,Fail current
```

Paths: `backend/services/github_index.py:GitHubIndexService.sync_repository`, `backend/repositories/connectors.py:ConnectorRepository`, `backend/config/alembic/versions/0006_github_sync_lease.py`.

## GitHub sync lease state

```mermaid
stateDiagram-v2
    [*] --> Configured
    Configured --> Syncing: acquire if not owned or expired
    Connected --> Syncing: next sync acquires
    Failed --> Syncing: retry acquires

    Syncing --> Syncing: heartbeat renews expiry
    Syncing --> Connected: matching lease completes
    Syncing --> Failed: matching lease fails
    Syncing --> Cancelled: CancelledError records failure
    Cancelled --> Failed: persisted as failed
    Syncing --> Expired: process death / no heartbeat
    Expired --> Syncing: new lease reclaims

    Connected --> [*]
```

## GitHub lease, heartbeat, cancellation — Current sequence

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant API as GitHub route
    participant S as GitHubIndexService
    participant R as ConnectorRepository
    participant DB as PostgreSQL
    participant GH as GitHub GET API

    Admin->>API: sync mapping
    API->>S: sync_repository
    S->>R: acquire(mapping, lease_id, expires_at)
    R->>DB: atomic UPDATE with status/expiry predicate
    alt another fresh owner exists
        DB-->>R: no row
        S-->>API: conflict
    else lease acquired
        DB-->>R: mapping ID
        S->>DB: commit lease
        S->>GH: branch + tree + blobs
        loop every bounded file interval
            S->>R: renew matching lease
            R->>DB: UPDATE WHERE lease_id matches
            alt lease lost
                S-->>API: conflict, stop writes
            end
        end
        alt success
            S->>R: complete matching lease + checkpoint
            S->>DB: commit
        else cancellation
            S->>DB: rollback partial transaction
            S->>R: fail matching lease as cancelled
            S->>DB: commit failure
        else exception
            S->>DB: rollback partial transaction
            S->>R: fail matching lease
            S->>DB: commit failure
        else hard process death
            Note over DB: lease remains until expires_at
            Admin->>S: later retry
            S->>R: acquire expired lease
        end
    end
```

## RAG answer pipeline — Current

```mermaid
flowchart TB
    Question["User question + conversation"]
    Scope["Resolve authorized Project scope"]
    Rewrite["Standalone question rewrite"]
    Special{"Structured Jira count?"}
    Planner{"Knowledge planner enabled?"}
    Retrieve["ConversationalRetriever"]
    Tools["Evidence planner + tools"]
    Candidates["Authorized candidate generation"]
    Fuse["Weighted fusion or RRF"]
    Recency["Optional source recency"]
    Rerank["Heuristic or model reranker"]
    Select["Diverse final selection"]
    Neighbor["Optional adjacent chunks"]
    Grade["CRAG evidence grade"]
    Weak{"Weak internal evidence?"}
    Sources["SSE sources event"]
    Generate["ResponseGenerator stream"]
    Ground["Citation + grounding verification / repair"]
    Persist["Persist turn + citations + eval + timings"]
    Done["SSE done"]
    Refuse["Bounded refusal / missing evidence"]

    Question --> Scope --> Rewrite --> Special
    Special -->|yes| Sources
    Special -->|no| Planner
    Planner -->|yes| Tools --> Candidates
    Planner -->|no| Retrieve --> Candidates
    Candidates --> Fuse --> Recency --> Rerank --> Select --> Neighbor --> Grade --> Weak
    Weak -->|yes| Sources --> Refuse --> Persist --> Done
    Weak -->|no| Sources --> Generate --> Ground --> Persist --> Done

    INV["INVARIANT<br/>Scope resolves before every retrieval arm;<br/>rewrites and plans cannot widen it"]
    Scope --> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Question,Scope,Rewrite,Special,Planner,Retrieve,Tools,Candidates,Fuse,Recency,Rerank,Select,Neighbor,Grade,Weak,Sources,Generate,Ground,Persist,Done,Refuse current
    class INV invariant
```

## Hybrid retrieval and ranker — Current detail

```mermaid
flowchart LR
    Q["Effective query"]
    EQ["Embed query"]
    Dense["Dense arm<br/>pgvector cosine HNSW"]
    Sparse["Sparse arm<br/>PostgreSQL FTS + title boost"]
    Exact["Optional exact arm<br/>IDs · paths · flags · issue keys"]
    Rare["Optional rare-token arm<br/>document-frequency signal"]

    Scores["Per-arm native score + rank"]
    Weights["Normalize weights across active arms"]
    Mode{"Fusion mode"}
    Weighted["Weighted normalized fusion"]
    RRF["Weighted Reciprocal Rank Fusion<br/>1 / (k + rank)"]
    Decay["Optional floor-bounded<br/>source recency multiplier"]
    Heuristic["Heuristic reranker"]
    Model{"Ambiguous semantic query<br/>and model reranker enabled?"}
    ModelRank["Bounded model ranking<br/>strict IDs + timeout"]
    Fallback["Heuristic fallback"]
    Diversity["Document + source diversity"]
    Top["Selected top-k + trace"]

    Q --> EQ --> Dense
    Q --> Sparse
    Q --> Exact
    Q --> Rare
    Dense --> Scores
    Sparse --> Scores
    Exact --> Scores
    Rare --> Scores
    Scores --> Weights --> Mode
    Mode -->|weighted| Weighted --> Decay
    Mode -->|rrf| RRF --> Decay
    Decay --> Heuristic --> Model
    Model -->|yes| ModelRank --> Diversity
    Model -->|invalid / timeout / provider error| Fallback --> Diversity
    Model -->|no| Diversity
    Diversity --> Top

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    class Q,EQ,Dense,Sparse,Exact,Rare,Scores,Weights,Mode,Weighted,RRF,Decay,Heuristic,Model,ModelRank,Fallback,Diversity,Top current
```

Paths: `backend/repositories/chunks.py:ChunkSearchRepository`, `backend/retrieval/fusion.py`, `backend/retrieval/rerankers.py:ModelReranker`, `backend/retrieval/pipeline.py:select_final_context`.

## Hybrid ranker — Proposed phased quality path

```mermaid
flowchart TB
    Baseline["CURRENT<br/>dense + sparse + optional exact/rare"]
    Calibrate["PHASE 1<br/>score calibration by arm/source/query class"]
    RRFTest["PHASE 1<br/>RRF and weighted ablations"]
    Cross["PHASE 2<br/>cross-encoder / late-interaction reranker"]
    Features["Authority · freshness · source quality<br/>explicit features"]
    Learn["PHASE 3<br/>learning-to-rank only with<br/>debiased tenant-safe labels"]
    Gate{"Golden + production-like gates<br/>recall · precision · MRR/nDCG<br/>latency · safety · cost"}
    Default["Promote versioned retrieval release"]
    Reject["Keep current default"]

    Baseline --> Calibrate --> RRFTest --> Cross --> Features --> Learn --> Gate
    RRFTest --> Gate
    Cross --> Gate
    Gate -->|all pass| Default
    Gate -->|any critical regression| Reject

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Baseline current
    class Calibrate,RRFTest,Cross,Features,Learn,Gate,Default,Reject proposed
```

## Contextual retrieval — Current and proposed

```mermaid
flowchart LR
    Source["Original source span"]
    Meta["Title · source · project/space · status<br/>updated time · heading · relationships"]
    Prefix["CURRENT<br/>deterministic context prefix"]
    Embed["Embedding text"]
    Cite["Citation display<br/>original evidence identity"]

    Summary["PROPOSED<br/>bounded contextual summary<br/>model + prompt + version"]
    Verify["PROPOSED<br/>identifier / hallucination checks"]
    Cached["PROPOSED<br/>reuse by source-span hash"]

    Source --> Prefix
    Meta --> Prefix
    Prefix --> Embed
    Source --> Cite
    Source -.-> Summary
    Meta -.-> Summary
    Summary -.-> Verify -.-> Cached -.-> Embed

    INV["INVARIANT<br/>Generated context improves retrieval;<br/>it is never the cited source of truth"]
    Summary -.-> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Source,Meta,Prefix,Embed,Cite current
    class Summary,Verify,Cached proposed
    class INV invariant
```

## Context assembly and lost-in-the-middle mitigation

```mermaid
flowchart TB
    Ranked["Reranked candidate list"]
    Dedupe["Near-duplicate + mirror dedupe"]
    Diversity["Document / source-family caps"]
    Primary["Primary evidence budget"]
    Neighbors["Adjacent chunk budget<br/>same active document version"]
    Memory["Conversation memory budget"]
    Conflict["Conflict + freshness grouping"]
    Pack["Token-aware packer"]

    Start["Strong evidence at beginning"]
    Middle["Supporting / adjacent context in middle"]
    End["Second strongest or decisive evidence at end"]
    Prompt["Structured source blocks<br/>stable evidence IDs"]

    Ranked --> Dedupe --> Diversity
    Diversity --> Primary
    Diversity --> Neighbors
    Memory --> Pack
    Primary --> Conflict --> Pack
    Neighbors --> Pack
    Pack --> Start
    Pack --> Middle
    Pack --> End
    Start --> Prompt
    Middle --> Prompt
    End --> Prompt

    Current["CURRENT<br/>diversity + optional neighbors"]
    Proposed["PROPOSED<br/>dedupe + budget classes + bookend ordering"]
    Current --> Diversity
    Proposed -.-> Dedupe
    Proposed -.-> Pack

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Current,Diversity,Neighbors current
    class Proposed,Dedupe,Primary,Memory,Conflict,Pack,Start,Middle,End,Prompt proposed
```

## Corrective retrieval state machine — Current

```mermaid
stateDiagram-v2
    [*] --> Retrieve
    Retrieve --> Evaluate
    Evaluate --> Accept: confidence sufficient
    Evaluate --> WidenK: recoverable low coverage
    Evaluate --> Rewrite: query can be clarified
    Evaluate --> Fallback: weak / exhausted
    WidenK --> Retrieve: bounded larger top-k
    Rewrite --> Retrieve: bounded rewritten query
    Retrieve --> KeepBest: compare with prior attempt
    KeepBest --> Evaluate
    Accept --> FinalContext
    Fallback --> WeakEvidencePolicy
    FinalContext --> [*]
    WeakEvidencePolicy --> [*]

    note right of KeepBest
      Strongest attempt survives;
      weaker retry cannot replace it.
    end note
```

Path: `backend/retrieval/crag.py` and `backend/retrieval/pipeline.py:RetrievalPipeline.run`.

## Chat and SSE — Current sequence

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Next.js Ask
    participant API as Chat route
    participant Chat as ChatService
    participant Auth as ProjectAuthorizationRepository
    participant RAG as Retrieval / Evidence Tools
    participant LLM as ResponseGenerator
    participant DB as PostgreSQL

    User->>UI: submit question
    UI->>API: ask(conversation, Project, modes)
    API->>Chat: ask as authenticated user
    Chat->>Auth: resolve owned conversation + scope
    Auth-->>Chat: authorized knowledge-base IDs
    Chat->>DB: bounded history
    Chat->>RAG: standalone query + fixed scope
    RAG-->>Chat: ranked chunks + confidence + trace
    Chat-->>UI: SSE sources
    alt weak internal evidence
        Chat-->>UI: bounded refusal delta
    else sufficient evidence
        Chat->>LLM: structured source blocks
        loop streamed tokens
            LLM-->>Chat: delta
            Chat-->>UI: SSE delta
        end
        Chat->>Chat: citations + grounding verification/repair
    end
    Chat->>DB: turn + citations + usage + timings + evaluation
    Chat-->>UI: SSE done
    alt mid-stream provider failure
        Chat-->>UI: terminal SSE error
    end
```

Path: `backend/services/chat_service.py:ChatService.ask`, `backend/chat/prompts.py`, `backend/services/response_generator.py`.

## Claim-level grounding — Proposed high-assurance mode

```mermaid
flowchart LR
    Draft["Model structured draft"]
    Claims["Claims[]<br/>text · evidence IDs · kind · confidence"]
    Schema["Strict schema validation"]
    Allowed["Evidence ID belongs to current<br/>authorized context"]
    Support["Claim/evidence support check"]
    Conflict["Conflict / missing evidence check"]
    Render["Render cited prose"]
    Persist["Persist claim audit + versions"]
    Reject["Repair once or refuse"]

    Draft --> Claims --> Schema --> Allowed --> Support --> Conflict --> Render --> Persist
    Schema -->|invalid| Reject
    Allowed -->|unknown ID| Reject
    Support -->|unsupported| Reject
    Conflict -->|unresolved critical conflict| Reject
    Reject -->|one bounded repair| Draft

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Draft,Claims,Schema,Allowed,Support,Conflict,Render,Persist,Reject proposed
```

## Agentic search and MCP — Current

```mermaid
flowchart TB
    Question["Question + explicit Project"]
    Planner["EvidencePlanner<br/>deterministic or model-assisted"]
    Schema["EvidencePlan schema<br/>≤ 5 tools · ≤ 3 subqueries"]
    Executor["EvidenceExecutor<br/>per-tool + overall deadlines"]

    K["search_knowledge"]
    J["search_jira"]
    C["search_confluence"]
    S["search_slack"]
    Code["search_code"]
    PR["recent_prs"]
    Who["who_knows"]

    Sessions["Independent AsyncSession per tool"]
    Auth["Re-resolve active principal + Project scope"]
    Evidence["Typed Evidence<br/>PermissionContext + citation identity"]
    Synthesis["Existing grounded synthesis"]

    MCP["MCP stdio bridge"]
    REST["Authenticated REST tools"]

    Question --> Planner --> Schema --> Executor
    Executor --> K
    Executor --> J
    Executor --> C
    Executor --> S
    Executor --> Code
    Executor --> PR
    Executor --> Who
    K --> Sessions
    J --> Sessions
    C --> Sessions
    S --> Sessions
    Code --> Sessions
    PR --> Sessions
    Who --> Sessions
    Sessions --> Auth --> Evidence --> Synthesis
    MCP --> REST --> Auth

    INV["INVARIANT<br/>Tools are read-only;<br/>tool output is evidence, not authority"]
    REST --> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Question,Planner,Schema,Executor,K,J,C,S,Code,PR,Who,Sessions,Auth,Evidence,Synthesis,MCP,REST current
    class INV invariant
```

Paths: `backend/services/evidence_contract.py`, `backend/services/evidence_planner.py`, `backend/services/evidence_executor.py`, `backend/services/evidence_tools.py`, `backend/scripts/run_mcp_server.py`.

## Agentic search — Proposed bounded loop

```mermaid
stateDiagram-v2
    [*] --> Classify
    Classify --> Plan
    Plan --> ValidateAuthority
    ValidateAuthority --> ExecuteTools
    ExecuteTools --> AssessCoverage
    AssessCoverage --> Synthesize: evidence adequate
    AssessCoverage --> FollowUpPlan: missing resolvable evidence
    FollowUpPlan --> ExecuteTools: one extra round only
    AssessCoverage --> StopPartial: deadline / budget / repeated query
    Synthesize --> ValidateClaims
    ValidateClaims --> PersistTrace
    ValidateClaims --> StopPartial: unsupported claims
    PersistTrace --> [*]
    StopPartial --> [*]

    note right of FollowUpPlan
      Max three new subqueries;
      no new authority IDs.
    end note
```

## Code execution boundary — Proposed

```mermaid
flowchart LR
    Agent["Agent planner"]
    Broker["Signed tool broker"]
    Sandbox["Ephemeral sandbox<br/>no host FS · no prod creds<br/>CPU/RAM/time limits"]
    Inputs[("Read-only approved inputs")]
    Output["Structured bounded output"]
    Audit["Immutable execution audit"]
    API["RAGCore API"]
    Deny["No retrieved text → shell"]

    Agent -.optional approved tool.-> Broker --> Sandbox
    Inputs --> Sandbox --> Output --> Agent
    Sandbox --> Audit
    API -.does not execute code.-> Deny

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Agent,Broker,Sandbox,Inputs,Output,Audit proposed
    class API,Deny invariant
```

## Data model — Current

```mermaid
erDiagram
    ORGANIZATION ||--o{ USER : contains
    ORGANIZATION ||--o{ KNOWLEDGE_BASE : owns
    ORGANIZATION ||--o{ PROJECT : owns
    ORGANIZATION ||--o{ CONNECTOR_STATE : configures

    USER ||--o{ REFRESH_TOKEN : rotates
    USER ||--o{ API_KEY : owns
    USER ||--o{ AUDIT_LOG : acts

    PROJECT ||--o{ PROJECT_MEMBER : has
    USER ||--o{ PROJECT_MEMBER : joins
    PROJECT ||--o{ PROJECT_SOURCE : maps
    KNOWLEDGE_BASE ||--o{ PROJECT_SOURCE : appears_in
    USER ||--o{ SOURCE_ACCESS_GRANT : receives
    KNOWLEDGE_BASE ||--o{ SOURCE_ACCESS_GRANT : restricts

    KNOWLEDGE_BASE ||--o{ COLLECTION : groups
    KNOWLEDGE_BASE ||--o{ DOCUMENT : contains
    COLLECTION o|--o{ DOCUMENT : groups
    DOCUMENT ||--o{ DOCUMENT_VERSION : versions
    DOCUMENT_VERSION ||--o{ CHUNK : produces
    DOCUMENT ||--o{ CHUNK : owns

    USER ||--o{ CONVERSATION : owns
    PROJECT ||--o{ CONVERSATION : scopes
    CONVERSATION ||--o{ MESSAGE : contains
    MESSAGE ||--o{ CITATION : cites
    CHUNK ||--o{ CITATION : supports
    MESSAGE ||--o| FEEDBACK : receives

    CONNECTOR_STATE ||--o{ SLACK_CHANNEL_MAPPING : maps
    CONNECTOR_STATE ||--o{ SLACK_EVENT_RECEIPT : deduplicates
    PROJECT ||--o{ GITHUB_REPOSITORY_MAPPING : scopes
    KNOWLEDGE_BASE ||--o{ GITHUB_REPOSITORY_MAPPING : indexes_into
    GITHUB_REPOSITORY_MAPPING ||--o{ GITHUB_FILE_STATE : tracks
    DOCUMENT o|--o| GITHUB_FILE_STATE : materializes
```

Model paths: `backend/models/user.py`, `backend/models/project.py`, `backend/models/knowledge.py`, `backend/models/chat.py`, `backend/models/connector.py`.

## Data model — Proposed enterprise additions

```mermaid
erDiagram
    ORGANIZATION ||--o{ EXTERNAL_PRINCIPAL : owns
    EXTERNAL_PRINCIPAL ||--o{ GROUP_MEMBERSHIP : member
    EXTERNAL_PRINCIPAL ||--o{ DOCUMENT_ACL_ENTRY : grants_or_denies
    DOCUMENT ||--o{ DOCUMENT_ACL_ENTRY : protects

    DOCUMENT_VERSION ||--o{ INGESTION_JOB : schedules
    INGESTION_JOB ||--o{ JOB_ATTEMPT : retries
    CONNECTOR_STATE ||--o{ CONNECTOR_CURSOR : checkpoints
    DOCUMENT ||--o{ KNOWLEDGE_TOMBSTONE : revokes

    EMBEDDING_REVISION ||--o{ CHUNK_EMBEDDING : versions
    CHUNK ||--o{ CHUNK_EMBEDDING : embeds
    RETRIEVAL_RUN ||--o{ RETRIEVAL_CANDIDATE : traces
    MESSAGE ||--o{ ANSWER_CLAIM : decomposes
    ANSWER_CLAIM }o--o{ CHUNK : supported_by

    EXTERNAL_PRINCIPAL {
        uuid organization_id
        string provider
        string external_id
        string principal_type
        bool active
    }
    DOCUMENT_ACL_ENTRY {
        uuid document_id
        uuid principal_id
        string effect
        string permission
        string acl_version
    }
    INGESTION_JOB {
        string idempotency_key
        string state
        uuid lease_owner
        datetime lease_expires_at
        int attempt
    }
    EMBEDDING_REVISION {
        string model
        int dimensions
        string status
        float coverage
    }
```

## Authorization and tenant scope — Current

```mermaid
flowchart TB
    Principal["Authenticated active user<br/>JWT or API key"]
    Org["Organization ownership"]
    Project["Selected/default active Project<br/>membership required"]
    Mapping["ProjectSource mappings"]
    Scope{"KnowledgeBase access_scope"}
    OrgWide["organization-visible"]
    Restricted["restricted"]
    Grant["Explicit SourceAccessGrant"]
    Filter["Optional request source-family filter"]
    Effective["Effective authorized knowledge-base IDs"]

    Principal --> Org --> Project --> Mapping --> Scope
    Scope --> OrgWide --> Effective
    Scope --> Restricted --> Grant --> Effective
    Filter --> Effective

    Equation["organization ∩ membership ∩ Project mapping<br/>∩ restricted grant ∩ request filter"]
    Effective --> Equation
    Equation --> Dense["Dense"]
    Equation --> Sparse["Sparse"]
    Equation --> Exact["Exact / code"]
    Equation --> Relationships["Relationships"]
    Equation --> Workflows["Workflows"]
    Equation --> MCP["REST / MCP"]

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    class Principal,Org,Project,Mapping,Scope,OrgWide,Restricted,Grant,Filter,Effective,Equation,Dense,Sparse,Exact,Relationships,Workflows,MCP current
```

Path: `backend/repositories/projects.py:ProjectAuthorizationRepository.authorized_scope`.

## Item-level ACL — Proposed

```mermaid
sequenceDiagram
    autonumber
    participant Source as Enterprise source
    participant Sync as ACL sync
    participant DB as Policy tables
    participant API as Request
    participant Auth as AuthorizationScope resolver
    participant Search as Search repository
    participant Cache as Cache

    Source->>Sync: content version + ACL version + principals
    Sync->>DB: upsert principals/groups/ACL entries
    Sync->>DB: increment policy version
    Sync->>Cache: invalidate affected scope versions
    API->>Auth: user + Project + request filter
    Auth->>DB: resolve tenant, membership, grants, groups, denies
    Auth-->>Search: immutable AuthorizationScope
    Search->>DB: SQL pre-filter before scoring/content return
    DB-->>Search: authorized candidates only
    Search-->>API: evidence with policy version
    API->>Auth: recheck version before source emission/persistence
```

## Cache and invalidation

```mermaid
flowchart TB
    Request["Search request"]
    Auth["Current authorization scope"]
    Key["Cache key<br/>tenant · user · role · Project<br/>authorized source IDs · query · retrieval flags"]
    Redis[("CURRENT Redis response cache")]
    Search["Authorized retrieval"]
    Result["Search response"]

    Request --> Auth --> Key --> Redis
    Redis -->|miss| Search --> Result --> Redis
    Redis -->|hit| Result

    Policy["PROPOSED policy version"]
    Corpus["PROPOSED corpus checkpoint"]
    Release["PROPOSED retrieval / embedding revision"]
    Invalidate["PROPOSED targeted invalidation"]
    Policy -.-> Key
    Corpus -.-> Key
    Release -.-> Key
    Policy -.-> Invalidate
    Corpus -.-> Invalidate
    Invalidate -.-> Redis

    INV["INVARIANT<br/>No cache key omits tenant and authorization scope"]
    Key --> INV

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class Request,Auth,Key,Redis,Search,Result current
    class Policy,Corpus,Release,Invalidate proposed
    class INV invariant
```

Paths: `backend/services/cache.py:ResponseCache`, `backend/api/routes/search.py:search`, `backend/embeddings/cache.py`.

## Observability — Current and proposed completion

```mermaid
flowchart LR
    Req["HTTP / SSE request"]
    MW["CURRENT ObservabilityMiddleware<br/>request ID · count · latency · logs"]
    RAG["RAG stages"]
    Jobs["Ingestion / connector jobs"]
    Providers["LLM / embedding / source APIs"]

    Prom[("Prometheus")]
    Logs[("Structured redacted logs")]
    OTel[("Optional OpenTelemetry")]
    Dash["Dashboards + alerts"]

    Req --> MW --> Prom
    MW --> Logs
    MW --> OTel
    RAG -.complete instrumentation.-> Prom
    RAG -.spans.-> OTel
    Jobs -.queue age · stage · freshness.-> Prom
    Jobs -.correlated events.-> Logs
    Providers -.latency · timeout · cost.-> Prom
    Providers -.child spans.-> OTel
    Prom --> Dash
    Logs --> Dash
    OTel --> Dash

    Current["CURRENT<br/>HTTP metrics, request IDs,<br/>redacted logs, health, optional OTel"]
    Proposed["PROPOSED<br/>wire all declared RAG/token/ingestion metrics;<br/>job/provider/freshness traces and SLO alerts"]
    Current --> MW
    Proposed -.-> RAG
    Proposed -.-> Jobs
    Proposed -.-> Providers

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class MW,Prom,Logs,OTel,Current current
    class RAG,Jobs,Providers,Dash,Proposed proposed
```

Paths: `backend/middleware/observability.py`, `backend/core/metrics.py`, `backend/core/logging.py`, `backend/api/routes/health.py`.

## Evaluation and release gate

```mermaid
flowchart TB
    Golden["Golden dataset<br/>source expectations + roles + refusal cases"]
    Candidate["Candidate retrieval release"]
    Baseline["Current default"]
    Run["Offline and integration eval"]

    Retrieval["Retrieval<br/>recall@k · precision · top-k · MRR · nDCG<br/>identifier · relationship · freshness"]
    Context["Context<br/>coverage · diversity · duplicate rate<br/>token efficiency · position sensitivity"]
    Answer["Answer<br/>groundedness · faithfulness · relevance<br/>citation coverage/correctness · completeness"]
    Safety["Safety<br/>ACL leakage · injection · secret leakage<br/>refusal correctness"]
    Ops["Operations<br/>p50/p95/p99 · first token · timeout<br/>provider calls · tokens · cost"]
    Slices["Slices<br/>source · query class · tenant size · role"]

    Gate{"All critical gates pass?"}
    Promote["Promote versioned release"]
    Hold["Keep baseline + record regression"]
    Observe["Canary + production quality telemetry"]
    Rollback["Fast rollback to prior release"]

    Golden --> Run
    Candidate --> Run
    Baseline --> Run
    Run --> Retrieval
    Run --> Context
    Run --> Answer
    Run --> Safety
    Run --> Ops
    Retrieval --> Slices
    Context --> Slices
    Answer --> Slices
    Safety --> Slices
    Ops --> Slices
    Slices --> Gate
    Gate -->|yes| Promote --> Observe
    Gate -->|no| Hold
    Observe -->|SLO/quality regression| Rollback

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Golden,Baseline,Run,Retrieval,Answer,Safety,Ops current
    class Candidate,Context,Slices,Gate,Promote,Hold,Observe,Rollback proposed
```

Paths: `backend/scripts/run_evals.py`, `backend/api/routes/evals.py`, `evals/golden/rag.jsonl`, `shivam_plan/retrieval_experiment.md`.

## Initial SLO map — Proposed

```mermaid
flowchart LR
    Ask["Ask availability<br/>99.9% monthly"]
    Retrieval["Retrieval p95<br/>< 800 ms"]
    First["First token p95<br/>< 2.5 s"]
    Complete["Fast answer p95<br/>< 10 s"]
    Fresh["Connector freshness p95<br/>< 15 min event sources"]
    Revoke["ACL revocation p99<br/>< 60 s after observation"]
    Durable["Accepted ingestion<br/>99.99% visible terminal/ready"]
    Cite["Factual citation coverage<br/>>= 98%"]
    Leak["Cross-tenant disclosure<br/>zero tolerated"]

    Quality["Enterprise knowledge SLO"]
    Ask --> Quality
    Retrieval --> Quality
    First --> Quality
    Complete --> Quality
    Fresh --> Quality
    Revoke --> Quality
    Durable --> Quality
    Cite --> Quality
    Leak --> Quality

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Ask,Retrieval,First,Complete,Fresh,Revoke,Durable,Cite,Leak,Quality proposed
```

## Security and threat boundaries

```mermaid
flowchart TB
    Trusted["Trusted policy<br/>authenticated principal · server settings<br/>resolved scope"]
    App["Trusted reviewed application code"]

    Input["Untrusted user input"]
    Content["Untrusted source content"]
    Model["Untrusted model output"]
    External["External providers / APIs"]

    Validate["Validate · normalize · bound"]
    Authorize["Authorize before retrieval"]
    Tag["Structured source tags<br/>evidence never instructions"]
    Parse["Strict output schemas<br/>timeouts + fallback"]
    Egress["Least-data egress<br/>host/provider policy"]
    Audit["Sanitized audit + telemetry"]

    Input --> Validate --> Authorize
    Content --> Tag --> Authorize
    Model --> Parse --> Authorize
    External --> Egress --> App
    Trusted --> Authorize
    App --> Authorize --> Audit

    Threats["Threats<br/>cross-tenant IDs · prompt injection · parser exploit<br/>secret indexing · SSRF · cache confusion<br/>cost abuse · stale deletion · MCP deputy"]
    Controls["Controls<br/>composite tenant FKs · pre-filter ACL · sandbox extraction<br/>path/content secret policy · URL allowlist · quotas<br/>tombstones · read-only MCP"]
    Threats -.mitigated by.-> Controls
    Controls --> Authorize

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Trusted,App,Input,Content,Model,External,Validate,Authorize,Tag,Parse,Egress,Audit current
    class Threats,Controls proposed
```

## Kubernetes deployment — Current manifests

```mermaid
flowchart TB
    Internet["Client"]
    Ingress["Ingress<br/>TLS · 60 MB body · SSE no buffering<br/>300 s read timeout"]
    Service["ClusterIP Service"]
    HPA["HPA<br/>3–12 replicas · CPU 70%"]

    subgraph Pods["API Deployment"]
        Init["Init container<br/>alembic upgrade head"]
        API1["API pod<br/>non-root · requests/limits<br/>readiness + liveness"]
        API2["API pod"]
        API3["API pod"]
    end

    Config["ConfigMap"]
    Secret["Secret template / manager target"]
    PG[("PostgreSQL")]
    Redis[("Redis")]
    Metrics["Prometheus scrape /metrics"]

    Internet --> Ingress --> Service
    Service --> API1
    Service --> API2
    Service --> API3
    HPA --> Pods
    Init --> API1
    Config --> API1
    Secret --> API1
    API1 --> PG
    API1 --> Redis
    API1 --> Metrics

    Gap["PHASED<br/>dedicated migration Job · worker deployments<br/>object storage · network policy · PDB<br/>read-only root FS after local-file removal"]
    Gap -.extends.-> Pods

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Internet,Ingress,Service,HPA,Init,API1,API2,API3,Config,Secret,PG,Redis,Metrics current
    class Gap proposed
```

Paths: `k8s/deployment.yaml`, `k8s/service.yaml`, `k8s/ingress.yaml`, `k8s/hpa.yaml`, `k8s/configmap.yaml`, `k8s/secret.yaml`.

## Scaling planes — Proposed

```mermaid
flowchart TB
    Load["Measured load"]
    APIQ["HTTP QPS · SSE concurrency<br/>first-token wait"]
    JobQ["Queue age · throughput<br/>provider quota"]
    DBQ["Chunk count · HNSW recall/latency<br/>index memory · write amplification"]

    API["Scale stateless API replicas"]
    IO["Scale connector I/O workers"]
    Extract["Scale extraction/OCR workers"]
    Embed["Scale embedding/index workers"]
    Pool["Connection pooler + query tuning"]
    HNSW["Tune ef_search / iterative scans"]
    Partition["Partition by tenant/domain"]
    Vector["Separate vector service<br/>only after parity gate"]

    Load --> APIQ --> API
    Load --> JobQ
    JobQ --> IO
    JobQ --> Extract
    JobQ --> Embed
    Load --> DBQ --> Pool --> HNSW --> Partition --> Vector

    Gate["Vector-service parity<br/>ACL filtering · deletion · lineage<br/>backup · recall · latency · cost"]
    Vector --> Gate

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Load,APIQ,JobQ,DBQ,API,IO,Extract,Embed,Pool,HNSW,Partition,Vector,Gate proposed
```

## Failure recovery matrix

```mermaid
flowchart LR
    LLM["LLM timeout"]
    Embed["Embedding failure"]
    API["API dies after acceptance"]
    Worker["Worker dies mid-index"]
    Lease["Sync owner dies"]
    Redis["Redis unavailable"]
    PG["PostgreSQL unavailable"]
    ACL["ACL revoked mid-answer"]
    Delete["Source deleted"]
    BadModel["Bad embedding/ranker release"]

    SSE["Terminal SSE error / approved fallback"]
    Retry["Durable retry; old version remains active"]
    Outbox["Outbox recovers accepted job"]
    Inactive["Inactive staging + expired lease reclaim"]
    Expire["Lease expiry + new owner"]
    Degrade["Defined cache/rate-limit degraded policy"]
    Ready["Readiness 503 + managed failover"]
    Recheck["Policy-version recheck before emit/persist"]
    Tombstone["Deactivate + invalidate first; purge later"]
    Rollback["Switch active version / retrieval release"]

    LLM --> SSE
    Embed --> Retry
    API --> Outbox
    Worker --> Inactive
    Lease --> Expire
    Redis --> Degrade
    PG --> Ready
    ACL --> Recheck
    Delete --> Tombstone
    BadModel --> Rollback

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class LLM,Lease,Redis,PG,SSE,Expire,Ready current
    class Embed,API,Worker,ACL,Delete,BadModel,Retry,Outbox,Inactive,Degrade,Recheck,Tombstone,Rollback proposed
```

## Disaster recovery — Proposed

```mermaid
sequenceDiagram
    autonumber
    participant Ops
    participant PG as PostgreSQL PITR
    participant Obj as Versioned object storage
    participant Redis as Redis
    participant App as Isolated RAGCore
    participant Conn as Connector reconciliation
    participant Eval as Auth + retrieval gate

    Ops->>PG: restore to recovery point
    Ops->>Obj: restore/verify object versions and checksums
    Ops->>Redis: start empty
    Ops->>App: deploy pinned application + migrations
    App->>PG: schema and lineage checks
    App->>Obj: artifact sampling
    App->>Eval: auth negative matrix + golden retrieval
    Eval-->>Ops: pass/fail evidence
    Ops->>Conn: resume from durable checkpoints
    Conn->>PG: reconcile without duplicate active documents
    Ops->>Ops: record measured RPO / RTO

    Note over Ops,Eval: Recovery targets must be ratified for each product tier
```

## CI/CD — Current and phased

```mermaid
flowchart LR
    Push["Push / pull request"]
    Lint["Ruff"]
    Type["Mypy<br/>currently advisory in workflow"]
    Test["Pytest + coverage<br/>PostgreSQL/pgvector + Redis"]
    Eval["Golden eval gate"]
    Build["Backend image build"]
    Scan["Trivy high/critical scan"]
    Deploy["Current deploy placeholder<br/>main + production environment"]

    Strict["PHASED<br/>strict changed-code/full typing gate"]
    Front["PHASED<br/>frontend lint + TypeScript + production build"]
    Migration["PHASED<br/>upgrade/downgrade/upgrade disposable DB"]
    Secret["PHASED<br/>secret scan + SBOM + dependency policy"]
    Sign["PHASED<br/>signed image + provenance"]
    Canary["PHASED<br/>migration Job + canary + SLO/eval observation"]
    Rollback["PHASED<br/>automated release rollback"]

    Push --> Lint --> Type --> Test --> Eval --> Build --> Scan --> Deploy
    Push -.-> Front
    Type -.-> Strict
    Test -.-> Migration
    Build -.-> Secret -.-> Sign -.-> Canary -.-> Rollback
    Front -.-> Canary
    Migration -.-> Canary
    Eval -.-> Canary

    classDef current fill:#dbeafe,stroke:#2563eb,color:#172554
    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class Push,Lint,Type,Test,Eval,Build,Scan,Deploy current
    class Strict,Front,Migration,Secret,Sign,Canary,Rollback proposed
```

Path: `.github/workflows/backend-ci.yml`.

## Phased enterprise roadmap

```mermaid
flowchart LR
    P0["PHASE 0<br/>Baseline + contracts<br/>auth matrix · metrics · release IDs"]
    P1["PHASE 1<br/>Reliability<br/>object store · outbox · durable jobs<br/>leases · tombstones · reconcile"]
    P2["PHASE 2<br/>Enterprise permissions<br/>principals · groups · document ACLs<br/>policy-version caches"]
    P3["PHASE 3<br/>Retrieval quality<br/>contextual retrieval · HNSW tuning<br/>RRF ablation · reranker · context packing"]
    P4["PHASE 4<br/>Bounded agentic search<br/>typed QueryPlan · one follow-up<br/>claim validation"]
    P5["PHASE 5<br/>Scale + governance<br/>quotas · retention · DR · capacity<br/>compliance evidence"]

    G0{"Reproducible baseline<br/>and auth negatives pass"}
    G1{"Kill/recovery tests<br/>no silent loss"}
    G2{"Revocation SLO<br/>all surfaces pass"}
    G3{"Quality gain<br/>no safety/latency regression"}
    G4{"Multi-hop gain within<br/>cost/tool/deadline budgets"}
    G5{"Restore drill + SLOs<br/>runbooks + security review"}

    P0 --> G0 --> P1 --> G1 --> P2 --> G2 --> P3 --> G3 --> P4 --> G4 --> P5 --> G5

    classDef proposed fill:#fef3c7,stroke:#d97706,color:#451a03,stroke-dasharray: 5 5
    class P0,P1,P2,P3,P4,P5,G0,G1,G2,G3,G4,G5 proposed
```

## Enterprise definition of done

```mermaid
flowchart TB
    ACL["Authorization negatives pass<br/>on search · Ask · history · citations<br/>documents · workflows · REST · MCP · caches"]
    Durable["Accepted ingestion is crash-durable<br/>idempotent and reconcilable"]
    Revoke["Deletion and revocation SLOs proven"]
    Lineage["Every citation resolves to source<br/>version · chunk · permission version"]
    Quality["Owned eval set beats baseline<br/>without hidden slice regressions"]
    Safe["Weak/conflicting/partial evidence<br/>has explicit safe behavior"]
    Operate["Metrics · alerts · runbooks · capacity<br/>completed restore drill"]
    Govern["Secrets · provider flow · retention<br/>export · legal hold · purge documented"]
    Browser["Automated + real-browser user flows pass"]
    Docs["Code · migrations · diagrams · API docs<br/>describe the same deployed system"]
    Done["Enterprise-ready RAGCore / CVUM"]

    ACL --> Done
    Durable --> Done
    Revoke --> Done
    Lineage --> Done
    Quality --> Done
    Safe --> Done
    Operate --> Done
    Govern --> Done
    Browser --> Done
    Docs --> Done

    classDef invariant fill:#dcfce7,stroke:#16a34a,color:#052e16
    class ACL,Durable,Revoke,Lineage,Quality,Safe,Operate,Govern,Browser,Docs,Done invariant
```

## Accuracy anchors

| Diagram area | Verified implementation anchors |
|---|---|
| API composition | `backend/api/main.py:create_app`, `backend/api/deps.py` |
| Identity and scope | `backend/core/security.py`, `backend/services/auth_service.py`, `backend/repositories/projects.py:ProjectAuthorizationRepository` |
| Ingestion | `backend/services/document_service.py`, `backend/ingestion/queue.py`, `backend/ingestion/pipeline.py` |
| Hybrid retrieval | `backend/repositories/chunks.py`, `backend/retrieval/pipeline.py`, `backend/retrieval/fusion.py`, `backend/retrieval/rerankers.py`, `backend/retrieval/crag.py` |
| Chat and grounding | `backend/services/chat_service.py`, `backend/services/conversational_retriever.py`, `backend/services/response_generator.py`, `backend/chat/prompts.py` |
| Agentic evidence / MCP | `backend/services/evidence_contract.py`, `backend/services/evidence_planner.py`, `backend/services/evidence_executor.py`, `backend/services/evidence_tools.py`, `backend/scripts/run_mcp_server.py` |
| Connectors | `backend/services/confluence_service.py`, `backend/services/jira_service.py`, `backend/services/slack_service.py`, `backend/services/github_index.py` |
| Storage models | `backend/models/user.py`, `backend/models/project.py`, `backend/models/knowledge.py`, `backend/models/chat.py`, `backend/models/connector.py` |
| Cache and telemetry | `backend/services/cache.py`, `backend/embeddings/cache.py`, `backend/middleware/observability.py`, `backend/core/metrics.py` |
| Deployment and gates | `backend/Dockerfile`, `docker-compose.yml`, `k8s/`, `.github/workflows/backend-ci.yml`, `docs/TESTING.md`, `docs/EVALS.md` |
