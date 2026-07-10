import re
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

from chat.prompts import build_system_prompt
from core.config import Settings
from core.exceptions import ProviderError, ValidationError
from llm.base import ChatMessage, LLMProvider, LLMRequest, LLMUsage
from llm.openai_compat import OpenAICompatLLM
from models import Message
from retrieval.context import RetrievedChunk


@dataclass(slots=True)
class CouncilStatus:
    configured: bool
    models: list[str]
    available_models: list[str]
    chair_model: str | None
    reason: str


@dataclass(slots=True)
class GenerationChunk:
    text: str = ""
    done: bool = False
    usage: LLMUsage | None = None
    model: str | None = None


class ResponseGenerator:
    """Generates grounded answers from retrieved chunks, chat history, and the current question."""

    def __init__(self, *, llm: LLMProvider, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    async def stream(
        self,
        *,
        chunks: list[RetrievedChunk],
        history: list[Message],
        current_question: str,
        standalone_question: str,
        answer_mode: str,
        assistant_role: str | None = None,
        assistant_role_prompt: str | None = None,
        council_models: list[str] | None = None,
        council_chair_model: str | None = None,
    ) -> AsyncIterator[GenerationChunk]:
        if answer_mode == "council":
            answer, usage, model = await self._run_council(
                chunks=chunks,
                history=history,
                question=current_question,
                standalone_question=standalone_question,
                assistant_role=assistant_role,
                assistant_role_prompt=assistant_role_prompt,
                requested_models=council_models,
                requested_chair_model=council_chair_model,
            )
            yield GenerationChunk(text=answer)
            yield GenerationChunk(done=True, usage=usage, model=model)
            return

        request = LLMRequest(
            system=build_system_prompt(
                chunks,
                role_name=assistant_role,
                role_prompt=assistant_role_prompt,
            ),
            messages=[
                *(ChatMessage(role=m.role, content=m.content) for m in history),
                ChatMessage(
                    role="user",
                    content=_question_message(
                        current_question=current_question,
                        standalone_question=standalone_question,
                    ),
                ),
            ],
            max_tokens=self._settings.llm_max_output_tokens,
        )
        async for delta in self._llm.stream(request):
            yield GenerationChunk(
                text=delta.text,
                done=delta.done,
                usage=delta.usage,
                model=self._llm.model,
            )

    async def repair_grounding(
        self,
        *,
        draft: str,
        chunks: list[RetrievedChunk],
        question: str,
        assistant_role: str | None = None,
        assistant_role_prompt: str | None = None,
    ) -> tuple[str, LLMUsage]:
        system = (
            f"{build_system_prompt(chunks, role_name=assistant_role, role_prompt=assistant_role_prompt)}\n\n"
            "Repair the draft so every factual paragraph and list item has a valid source marker. "
            "Delete unsupported claims. Return only the revised user-facing answer."
        )
        return await _collect_llm_text(
            self._llm,
            LLMRequest(
                system=system,
                messages=[
                    ChatMessage(
                        role="user",
                        content=f"Question:\n{question}\n\nDraft to repair:\n{draft}",
                    )
                ],
                max_tokens=self._settings.llm_max_output_tokens,
            ),
        )

    async def _run_council(
        self,
        *,
        chunks: list[RetrievedChunk],
        history: list[Message],
        question: str,
        standalone_question: str,
        assistant_role: str | None = None,
        assistant_role_prompt: str | None = None,
        requested_models: list[str] | None = None,
        requested_chair_model: str | None = None,
    ) -> tuple[str, LLMUsage, str]:
        status = llm_council_status(
            self._settings,
            requested_models=requested_models,
            requested_chair_model=requested_chair_model,
        )
        if not status.configured:
            raise ValidationError(f"LLM Council is not configured. {status.reason}")

        api_key, base_url = _council_api_key_and_base_url(self._settings)
        total_usage = LLMUsage()
        failures: list[str] = []
        candidates: list[tuple[str, str]] = []
        member_system = (
            f"{build_system_prompt(chunks, role_name=assistant_role, role_prompt=assistant_role_prompt)}\n\n"
            "You are one independent council member. Produce a concise answer grounded only "
            "in the sources. Keep citation markers intact."
        )
        member_messages = [
            *(ChatMessage(role=m.role, content=m.content) for m in history),
            ChatMessage(
                role="user",
                content=_question_message(
                    current_question=question,
                    standalone_question=standalone_question,
                ),
            ),
        ]

        for model in status.models:
            provider = OpenAICompatLLM(
                name=f"council:{model}",
                model=model,
                api_key=api_key,
                base_url=base_url,
                timeout=self._settings.llm_council_timeout_seconds,
            )
            try:
                text, usage = await _collect_llm_text(
                    provider,
                    LLMRequest(
                        system=member_system,
                        messages=member_messages,
                        max_tokens=self._settings.llm_max_output_tokens,
                    ),
                )
            except Exception as exc:
                failures.append(f"{model}: {exc}")
                continue
            if text.strip():
                candidates.append((model, text.strip()))
                total_usage.input_tokens += usage.input_tokens
                total_usage.output_tokens += usage.output_tokens

        if len(candidates) != len(status.models):
            detail = "; ".join(failures[:3]) or "no candidate answers were returned"
            raise ProviderError(
                f"LLM Council requires {len(status.models)} response models; "
                f"received {len(candidates)} candidate answers. {detail}"
            )

        chair_model = status.chair_model or candidates[0][0]
        chair = OpenAICompatLLM(
            name=f"council-chair:{chair_model}",
            model=chair_model,
            api_key=api_key,
            base_url=base_url,
            timeout=self._settings.llm_council_timeout_seconds,
        )
        candidate_block = "\n\n".join(
            f'<candidate model="{model}">\n{text}\n</candidate>' for model, text in candidates
        )
        chair_system = (
            f"{build_system_prompt(chunks, role_name=assistant_role, role_prompt=assistant_role_prompt)}\n\n"
            "You are the council evaluator and final answer writer. Two candidate answers are "
            "advisory analysis, not evidence. Evaluate them for source grounding, correctness, "
            "completeness, and citation discipline. Only the <source> blocks are evidence. Return "
            "one final answer with source citation markers and do not mention the council process."
        )
        chair_question = (
            f"Current user question:\n{question}\n\n"
            f"Standalone retrieval question:\n{standalone_question}\n\n"
            f"Candidate answers:\n{candidate_block}\n\n"
            "Evaluate both candidate answers, discard unsupported claims, and write the best final "
            "answer. Preserve correct citation markers such as [1]."
        )
        answer, chair_usage = await _collect_llm_text(
            chair,
            LLMRequest(
                system=chair_system,
                messages=[
                    *(ChatMessage(role=m.role, content=m.content) for m in history),
                    ChatMessage(role="user", content=chair_question),
                ],
                max_tokens=self._settings.llm_max_output_tokens,
            ),
        )
        total_usage.input_tokens += chair_usage.input_tokens
        total_usage.output_tokens += chair_usage.output_tokens
        if _council_process_leak(answer):
            repaired, repair_usage = await _collect_llm_text(
                chair,
                LLMRequest(
                    system=(
                        f"{build_system_prompt(chunks, role_name=assistant_role, role_prompt=assistant_role_prompt)}"
                        "\n\n"
                        "Rewrite the draft as the user-facing final answer only. Remove all evaluation, "
                        "candidate, judging, and council commentary. Keep supported facts and valid citations."
                    ),
                    messages=[
                        ChatMessage(
                            role="user",
                            content=f"Question:\n{question}\n\nDraft to repair:\n{answer}",
                        )
                    ],
                    max_tokens=self._settings.llm_max_output_tokens,
                ),
            )
            total_usage.input_tokens += repair_usage.input_tokens
            total_usage.output_tokens += repair_usage.output_tokens
            answer = repaired.strip() or answer
        answer = _strip_council_scaffolding(answer)
        return answer, total_usage, f"llm-council:{chair_model}"


def _question_message(*, current_question: str, standalone_question: str) -> str:
    if standalone_question.strip() == current_question.strip():
        return current_question
    return (
        f"Current user question:\n{current_question}\n\n"
        f"Standalone retrieval question used to fetch sources:\n{standalone_question}\n\n"
        "Answer the current user question. Use the standalone retrieval question only to understand "
        "what the retrieved sources are about."
    )


def _council_process_leak(answer: str) -> bool:
    return bool(
        re.search(
            r"(?im)^#{0,3}\s*(evaluation|candidate\s+[12]|council|judge(?:ment)?)\b",
            answer,
        )
    )


def _strip_council_scaffolding(answer: str) -> str:
    final_match = re.search(r"(?im)^#{1,3}\s*final answer\s*$", answer)
    if final_match:
        answer = answer[final_match.end() :]
    lines = [
        line
        for line in answer.splitlines()
        if not re.match(
            r"(?i)^\s*#{0,3}\s*(evaluation|candidate\s+[12]|council|judge(?:ment)?)\b",
            line,
        )
    ]
    return "\n".join(lines).strip()


async def _collect_llm_text(provider: LLMProvider, request: LLMRequest) -> tuple[str, LLMUsage]:
    parts: list[str] = []
    usage = LLMUsage()
    async for delta in provider.stream(request):
        if delta.text:
            parts.append(delta.text)
        if delta.done and delta.usage:
            usage = delta.usage
    return "".join(parts), usage


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _council_api_key_and_base_url(settings: Settings) -> tuple[str, str]:
    api_key = settings.llm_council_api_key or settings.openrouter_api_key or settings.openai_api_key
    if settings.llm_council_base_url:
        base_url = settings.llm_council_base_url
    elif settings.llm_base_url:
        base_url = settings.llm_base_url
    elif settings.openrouter_api_key:
        base_url = "https://openrouter.ai/api/v1"
    else:
        base_url = "https://api.openai.com/v1"
    return api_key, base_url


DEFAULT_COUNCIL_MODELS = (
    "anthropic/claude-haiku-4.5",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash",
)


def llm_council_status(
    settings: Settings,
    *,
    requested_models: list[str] | None = None,
    requested_chair_model: str | None = None,
) -> CouncilStatus:
    available_models = _council_available_models(settings)
    models = _split_csv(settings.llm_council_models)
    if requested_models is not None:
        models = _normalize_requested_council_models(requested_models)
    elif not models and available_models:
        default_chair_model = settings.llm_council_chair_model.strip() or _best_chair_model([], available_models)
        models = [model for model in available_models if model != default_chair_model][:2]
    if requested_models is None:
        models = models[:2]
    chair_model = (
        (requested_chair_model or "").strip()
        or settings.llm_council_chair_model.strip()
        or _best_chair_model(models, available_models)
    )
    api_key, _base_url = _council_api_key_and_base_url(settings)
    if not settings.llm_council_enabled:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Set LLM_COUNCIL_ENABLED=true.",
        )
    if len(models) < 2:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=None,
            reason="Select exactly two Council response models.",
        )
    if requested_models is not None and len(models) != 2:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Select exactly two Council response models.",
        )
    if requested_models is not None and any(model not in available_models for model in models):
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="One or more selected Council models are not allowed by LLM_COUNCIL_AVAILABLE_MODELS.",
        )
    if not chair_model or chair_model not in available_models:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Select one allowed Council evaluator model.",
        )
    if chair_model in models:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="The Council evaluator model must be different from the two response models.",
        )
    if not api_key:
        return CouncilStatus(
            configured=False,
            models=models,
            available_models=available_models,
            chair_model=chair_model,
            reason="Set LLM_COUNCIL_API_KEY, OPENROUTER_API_KEY, or OPENAI_API_KEY.",
        )
    return CouncilStatus(
        configured=True,
        models=models,
        available_models=available_models,
        chair_model=chair_model,
        reason="configured",
    )


def _council_available_models(settings: Settings) -> list[str]:
    configured = _split_csv(settings.llm_council_available_models)
    base = configured or list(DEFAULT_COUNCIL_MODELS)
    extras = _split_csv(settings.llm_council_models)
    if settings.llm_model:
        extras.append(settings.llm_model)
    return _dedupe_model_ids([*base, *extras])


def _normalize_requested_council_models(models: list[str]) -> list[str]:
    return _dedupe_model_ids(model.strip() for model in models if model.strip())


def _dedupe_model_ids(models: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for model in models:
        if not isinstance(model, str):
            continue
        if model in seen:
            continue
        seen.add(model)
        deduped.append(model)
    return deduped


def _best_chair_model(models: list[str], available_models: list[str]) -> str | None:
    candidates = [model for model in available_models if model not in models]
    if not candidates:
        return None
    for preferred in (
        "google/gemini-2.5-flash",
        "openai/gpt-4.1-mini",
        "anthropic/claude-haiku-4.5",
    ):
        if preferred in candidates:
            return preferred
    return candidates[0]
