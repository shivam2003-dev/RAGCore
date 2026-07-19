"""Planner -> independent executor adapter for the existing grounded chat path."""

import uuid
from dataclasses import dataclass

from models import User
from retrieval.context import RetrievedChunk
from services.evidence_contract import EvidenceExecutionResult, EvidencePlan
from services.evidence_executor import EvidenceExecutor, EvidencePrincipal
from services.evidence_planner import EvidencePlanner


@dataclass(slots=True)
class EvidenceOrchestration:
    plan: EvidencePlan
    execution: EvidenceExecutionResult
    chunks: list[RetrievedChunk]


class EvidenceOrchestrator:
    def __init__(self, *, planner: EvidencePlanner, executor: EvidenceExecutor) -> None:
        self._planner = planner
        self._executor = executor

    async def retrieve(
        self,
        *,
        question: str,
        project_id: uuid.UUID,
        user: User,
    ) -> EvidenceOrchestration:
        plan = await self._planner.plan(question=question, project_id=project_id)
        execution = await self._executor.execute(
            plan=plan,
            principal=EvidencePrincipal(user_id=user.id, organization_id=user.organization_id),
        )
        return EvidenceOrchestration(
            plan=plan,
            execution=execution,
            chunks=evidence_to_chunks(execution),
        )


def evidence_to_chunks(execution: EvidenceExecutionResult) -> list[RetrievedChunk]:
    """Keep persisted source identities so existing citation FKs remain valid."""

    chunks: list[RetrievedChunk] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for item in execution.evidence:
        if item.chunk_id is None or item.document_id is None:
            continue
        identity = (item.chunk_id, item.document_id)
        if identity in seen:
            continue
        seen.add(identity)
        chunks.append(
            RetrievedChunk(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_title=item.title,
                content=item.content,
                metadata={
                    **item.metadata,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                    "source_url": item.source_url or "",
                    "citation_identity": item.citation_identity,
                    "evidence_project_id": str(item.project_id),
                },
                score=item.score,
                fusion_score=item.score,
                retrieval_arms=item.retrieval_arms,
                selected_rank=item.rank,
            )
        )
    return chunks
