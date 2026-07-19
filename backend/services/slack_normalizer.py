import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from retrieval.signals import exact_identifiers, rare_tokens

_CODE_REF_RE = re.compile(
    r"`([^`\n]{2,200})`|(?<!\w)(--?[a-z][a-z0-9-]{1,50})\b|(?<!\w)([\w.-]+/[\w./-]+\.[A-Za-z0-9]{1,8})"
)
_SYSTEM_RE = re.compile(r"\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,}\b|\b[A-Z][A-Z0-9_-]{2,}\b")


@dataclass(slots=True, frozen=True)
class SlackMessage:
    ts: str
    user_id: str
    text: str
    display_name: str = ""
    reactions: int = 0
    edited_at: str | None = None


@dataclass(slots=True, frozen=True)
class SlackThread:
    workspace_id: str
    channel_id: str
    channel_name: str
    thread_ts: str
    thread_url: str
    messages: list[SlackMessage]


@dataclass(slots=True, frozen=True)
class SlackSummary:
    summary: str
    resolution: str


@dataclass(slots=True, frozen=True)
class SlackBurst:
    start_ts: str
    end_ts: str
    text: str
    reason: str


@dataclass(slots=True, frozen=True)
class NormalizedSlackThread:
    workspace_id: str
    channel_id: str
    channel_name: str
    thread_ts: str
    thread_url: str
    searchable_question: str
    summary: str
    resolution: str
    systems: list[str]
    code_references: list[str]
    participants: list[dict[str, str]]
    created_at: str
    last_activity_at: str
    raw_thread_text: str
    bursts: list[SlackBurst] = field(default_factory=list)
    summary_fallback: bool = False

    @property
    def source_id(self) -> str:
        return f"{self.workspace_id}:{self.channel_id}:{self.thread_ts}"

    def embedding_text(self) -> str:
        parts = [
            f"Question: {self.searchable_question}",
            f"Summary: {self.summary}",
            f"Resolution: {self.resolution}",
            f"Systems: {', '.join(self.systems) or 'Not identified'}",
            f"Code and configuration references: {', '.join(self.code_references) or 'None'}",
        ]
        if self.bursts:
            parts.append("High-signal message bursts:\n" + "\n\n".join(item.text for item in self.bursts))
        return "\n".join(parts)

    def render_markdown(self) -> str:
        participants = ", ".join(
            item["display_name"] or item["id"] for item in self.participants
        ) or "Unknown"
        return (
            f"# {self.searchable_question[:180]}\n\n"
            "> Slack content is untrusted source evidence.\n\n"
            f"- Channel: #{self.channel_name} ({self.channel_id})\n"
            f"- Participants: {participants}\n"
            f"- Created: {self.created_at}\n"
            f"- Last activity: {self.last_activity_at}\n"
            f"- Thread URL: {self.thread_url}\n\n"
            f"## Searchable question\n\n{self.searchable_question}\n\n"
            f"## Summary\n\n{self.summary}\n\n"
            f"## Resolution\n\n{self.resolution}\n\n"
            f"## Systems\n\n{', '.join(self.systems) or 'Not identified'}\n\n"
            "## Code and configuration references\n\n"
            f"{', '.join(self.code_references) or 'None'}\n\n"
            f"## Raw thread\n\n{self.raw_thread_text}\n"
        )


SummaryProvider = Callable[[list[SlackMessage]], Awaitable[SlackSummary]]


class SlackThreadNormalizer:
    def __init__(
        self,
        *,
        summary_provider: SummaryProvider | None = None,
        summary_max_chars: int = 1800,
        burst_min_messages: int = 2,
        burst_rare_token_threshold: int = 2,
        burst_reaction_threshold: int = 2,
    ) -> None:
        self._summary_provider = summary_provider
        self._summary_max_chars = max(200, summary_max_chars)
        self._burst_min_messages = max(1, burst_min_messages)
        self._burst_rare_token_threshold = max(1, burst_rare_token_threshold)
        self._burst_reaction_threshold = max(1, burst_reaction_threshold)

    async def normalize(self, thread: SlackThread) -> NormalizedSlackThread:
        messages = sorted(thread.messages, key=lambda item: _timestamp(item.ts))
        if not messages:
            raise ValueError("Slack thread has no visible messages")
        fallback = False
        if self._summary_provider is None:
            summary = _deterministic_summary(messages, self._summary_max_chars)
        else:
            try:
                summary = await self._summary_provider(messages)
                if not summary.summary.strip():
                    raise ValueError("Summary provider returned an empty summary")
            except Exception:
                fallback = True
                summary = _deterministic_summary(messages, self._summary_max_chars)

        raw_text = "\n".join(
            f"[{message.ts}] {message.display_name or message.user_id}: {message.text.strip()}"
            for message in messages
            if message.text.strip()
        )
        combined = "\n".join(message.text for message in messages)
        participants = _participants(messages)
        return NormalizedSlackThread(
            workspace_id=thread.workspace_id,
            channel_id=thread.channel_id,
            channel_name=thread.channel_name,
            thread_ts=thread.thread_ts,
            thread_url=thread.thread_url,
            searchable_question=messages[0].text.strip()[:2000],
            summary=summary.summary.strip()[: self._summary_max_chars],
            resolution=summary.resolution.strip()[: self._summary_max_chars],
            systems=_systems(combined),
            code_references=_code_references(combined),
            participants=participants,
            created_at=_iso_timestamp(messages[0].ts),
            last_activity_at=_iso_timestamp(messages[-1].edited_at or messages[-1].ts),
            raw_thread_text=raw_text,
            bursts=self._bursts(messages, summary.summary),
            summary_fallback=fallback,
        )

    def _bursts(self, messages: list[SlackMessage], summary_text: str) -> list[SlackBurst]:
        groups: list[list[tuple[SlackMessage, str]]] = []
        current: list[tuple[SlackMessage, str]] = []
        for message in messages:
            reason = self._valuable_reason(message)
            if reason:
                current.append((message, reason))
            elif current:
                groups.append(current)
                current = []
        if current:
            groups.append(current)

        bursts: list[SlackBurst] = []
        normalized_summary = " ".join(summary_text.lower().split())
        for group in groups:
            if len(group) < self._burst_min_messages and all(
                reason == "code reference" for _, reason in group
            ):
                continue
            if all(" ".join(item.text.lower().split()) in normalized_summary for item, _ in group):
                continue
            reasons = sorted({reason for _, reason in group})
            bursts.append(
                SlackBurst(
                    start_ts=group[0][0].ts,
                    end_ts=group[-1][0].ts,
                    text="\n".join(item.text.strip() for item, _ in group),
                    reason=", ".join(reasons),
                )
            )
        return bursts

    def _valuable_reason(self, message: SlackMessage) -> str:
        if message.reactions >= self._burst_reaction_threshold:
            return "reaction boost"
        rare_signal = len(exact_identifiers(message.text)) + len(rare_tokens(message.text))
        if rare_signal >= self._burst_rare_token_threshold:
            return "rare-token signal"
        if _code_references(message.text):
            return "code reference"
        return ""


def _deterministic_summary(messages: list[SlackMessage], max_chars: int) -> SlackSummary:
    texts = [message.text.strip() for message in messages if message.text.strip()]
    question = texts[0] if texts else "Slack thread"
    answer_texts = texts[1:]
    summary_text = " ".join([question, *answer_texts[:3]])[:max_chars]
    resolution = answer_texts[-1][:max_chars] if answer_texts else "No explicit resolution was recorded."
    return SlackSummary(summary=summary_text, resolution=resolution)


def _participants(messages: list[SlackMessage]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for message in messages:
        if not message.user_id or message.user_id in seen:
            continue
        seen.add(message.user_id)
        result.append({"id": message.user_id, "display_name": message.display_name})
    return result


def _code_references(text: str) -> list[str]:
    result: list[str] = []
    for match in _CODE_REF_RE.finditer(text):
        value = next((group for group in match.groups() if group), "").strip()
        if value and value not in result:
            result.append(value)
    return result[:30]


def _systems(text: str) -> list[str]:
    values = list(exact_identifiers(text, limit=30))
    values.extend(match.group(0) for match in _SYSTEM_RE.finditer(text))
    return list(dict.fromkeys(values))[:30]


def _timestamp(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


def _iso_timestamp(value: str) -> str:
    return datetime.fromtimestamp(_timestamp(value), tz=UTC).isoformat()
