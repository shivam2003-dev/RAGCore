"""Concurrent evidence execution with one independent resource context per tool."""

import asyncio
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from services.evidence_contract import (
    Evidence,
    EvidenceExecutionResult,
    EvidencePlan,
    EvidenceToolRequest,
    ToolExecution,
    ToolSelection,
)


@dataclass(slots=True, frozen=True)
class EvidencePrincipal:
    user_id: uuid.UUID
    organization_id: uuid.UUID


class EvidenceToolRunner(Protocol):
    async def invoke_for_principal(
        self,
        *,
        selection: ToolSelection,
        request: EvidenceToolRequest,
        principal: EvidencePrincipal,
    ) -> list[Evidence]: ...


ToolContextFactory = Callable[[], AbstractAsyncContextManager[EvidenceToolRunner]]


class EvidenceExecutor:
    def __init__(
        self,
        *,
        tool_context_factory: ToolContextFactory,
        per_tool_timeout_seconds: float = 4.0,
        overall_timeout_seconds: float = 8.0,
        max_tools: int = 5,
    ) -> None:
        self._tool_context_factory = tool_context_factory
        self._per_tool_timeout = max(0.01, per_tool_timeout_seconds)
        self._overall_timeout = max(self._per_tool_timeout, overall_timeout_seconds)
        self._max_tools = max(1, min(max_tools, 5))

    async def execute(
        self,
        *,
        plan: EvidencePlan,
        principal: EvidencePrincipal,
    ) -> EvidenceExecutionResult:
        started = time.perf_counter()
        selections = plan.selections[: self._max_tools]
        tasks = [asyncio.create_task(self._run(selection, plan.project_id, principal)) for selection in selections]
        done, pending = await asyncio.wait(tasks, timeout=self._overall_timeout)
        executions = [task.result() for task in done]
        for task, selection in zip(tasks, selections, strict=True):
            if task not in pending:
                continue
            task.cancel()
            executions.append(
                ToolExecution(
                    tool=selection.tool,
                    query=selection.query,
                    latency_ms=int(self._overall_timeout * 1000),
                    failure="overall deadline exceeded",
                    timed_out=True,
                )
            )
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        order = {(item.tool, item.query): index for index, item in enumerate(selections)}
        executions.sort(key=lambda item: order[(item.tool, item.query)])
        evidence = [item for execution in executions for item in execution.evidence]
        evidence.sort(key=lambda item: (-item.score, item.citation_identity))
        return EvidenceExecutionResult(
            project_id=plan.project_id,
            selected_tools=[item.tool for item in selections],
            evidence=evidence,
            executions=executions,
            total_latency_ms=int((time.perf_counter() - started) * 1000),
            partial=any(item.failure is not None for item in executions),
        )

    async def _run(
        self,
        selection: ToolSelection,
        project_id: uuid.UUID,
        principal: EvidencePrincipal,
    ) -> ToolExecution:
        started = time.perf_counter()
        try:
            async with self._tool_context_factory() as runner:
                evidence = await asyncio.wait_for(
                    runner.invoke_for_principal(
                        selection=selection,
                        request=EvidenceToolRequest(
                            query=selection.query,
                            project_id=project_id,
                            limit=selection.limit,
                        ),
                        principal=principal,
                    ),
                    timeout=self._per_tool_timeout,
                )
            return ToolExecution(
                tool=selection.tool,
                query=selection.query,
                evidence=evidence,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except TimeoutError:
            return ToolExecution(
                tool=selection.tool,
                query=selection.query,
                latency_ms=int((time.perf_counter() - started) * 1000),
                failure="tool timeout exceeded",
                timed_out=True,
            )
        except Exception as exc:
            return ToolExecution(
                tool=selection.tool,
                query=selection.query,
                latency_ms=int((time.perf_counter() - started) * 1000),
                failure=f"{type(exc).__name__}: {str(exc)[:300]}",
            )
