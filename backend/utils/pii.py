"""Best-effort PII redaction applied to every log line.

Regex-based on purpose: cheap, dependency-free, and runs on the hot logging path.
Not a substitute for upstream data hygiene.
"""

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<email>"),
    (re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){9,12}\d\b"), "<phone>"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "<card>"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "<ssn>"),
    (re.compile(r"(?i)\b(bearer|token|key|password|secret)\s*[:=]\s*\S+"), r"\1=<redacted>"),
]


def redact_pii(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
