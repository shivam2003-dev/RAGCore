"""Stable contracts shared by planner, REST tools, chat, and MCP."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceToolName(enum.StrEnum):
    SEARCH_KNOWLEDGE = "search_knowledge"
    SEARCH_JIRA = "search_jira"
    SEARCH_CONFLUENCE = "search_confluence"
    SEARCH_SLACK = "search_slack"
    SEARCH_CODE = "search_code"
    RECENT_PRS = "recent_prs"
    WHO_KNOWS = "who_knows"


class PermissionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    organization_id: uuid.UUID
    user_id: uuid.UUID
    project_id: uuid.UUID
    knowledge_base_id: uuid.UUID | None = None
    decision: str = "authorized"


class Evidence(BaseModel):
    """One retrieval primitive result; answer generation is deliberately absent."""

    source_type: str = Field(min_length=1, max_length=40)
    source_id: str = Field(min_length=1, max_length=1000)
    source_url: str | None = Field(default=None, max_length=4000)
    project_id: uuid.UUID
    permission_context: PermissionContext
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=100_000)
    snippet: str = Field(min_length=1, max_length=2000)
    retrieval_arms: list[str] = Field(default_factory=list, max_length=10)
    rank: int = Field(ge=1, le=1000)
    score: float
    freshness: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    citation_identity: str = Field(min_length=1, max_length=2000)
    chunk_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class EvidenceToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    project_id: uuid.UUID
    limit: int = Field(default=8, ge=1, le=50)


class ToolSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: EvidenceToolName
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=50)


class EvidencePlan(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    project_id: uuid.UUID
    selections: list[ToolSelection] = Field(min_length=1, max_length=5)
    strategy: str = Field(default="deterministic", pattern="^(model|deterministic)$")
    fallback_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def bound_subqueries(self) -> "EvidencePlan":
        if len({item.query.strip().casefold() for item in self.selections}) > 3:
            raise ValueError("A plan may contain at most three distinct subqueries")
        return self


class ToolExecution(BaseModel):
    tool: EvidenceToolName
    query: str
    evidence: list[Evidence] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    failure: str | None = None
    timed_out: bool = False


class EvidenceExecutionResult(BaseModel):
    project_id: uuid.UUID
    selected_tools: list[EvidenceToolName]
    evidence: list[Evidence]
    executions: list[ToolExecution]
    total_latency_ms: int = Field(ge=0)
    partial: bool = False


class ToolInvocationResult(BaseModel):
    tool: EvidenceToolName
    project_id: uuid.UUID
    evidence: list[Evidence]
    latency_ms: int = Field(ge=0)


TOOL_CAPABILITIES: dict[EvidenceToolName, str] = {
    EvidenceToolName.SEARCH_KNOWLEDGE: "Search all authorized indexed knowledge sources.",
    EvidenceToolName.SEARCH_JIRA: "Search authorized indexed Jira issues and issue relationships.",
    EvidenceToolName.SEARCH_CONFLUENCE: "Search authorized indexed Confluence pages and runbooks.",
    EvidenceToolName.SEARCH_SLACK: "Search authorized allowlisted public Slack thread summaries.",
    EvidenceToolName.SEARCH_CODE: "Search authorized indexed GitHub code by exact symbol or text.",
    EvidenceToolName.RECENT_PRS: "List recent pull requests for authorized configured repositories.",
    EvidenceToolName.WHO_KNOWS: "Find likely experts from authorized source ownership metadata.",
}
