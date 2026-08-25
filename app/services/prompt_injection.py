import re

from app.models.chat import ChatMessage

# Coarse heuristics for common prompt-injection phrasing: overriding prior
# instructions, extracting the system prompt, or switching the model into
# an unrestricted persona. This is a detection signal for audit/review, not
# a filter — real injection attempts can easily avoid these exact phrases,
# and legitimate messages can innocently contain them. Nothing is ever
# blocked based on a match; it only gets flagged in the audit log (and, for
# successful responses, an X-Prompt-Injection-Suspected response header) so
# a human can review real traffic patterns over time.
_SUSPICIOUS_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"ignore (all|any|the)?\s*(previous|prior|above)\s*instructions",
        r"disregard (all|any|the)?\s*(previous|prior|above)",
        r"new instructions\s*:",
        r"reveal (your|the)\s*(system prompt|instructions)",
        r"what (is|are) your (system prompt|instructions)",
        r"act as (if you|though)",
        r"\bjailbreak\b",
        r"\bdo anything now\b",
        r"\bdan mode\b",
    ]
]


def detect_prompt_injection_risk(messages: list[ChatMessage]) -> bool:
    return any(
        pattern.search(message.content)
        for message in messages
        for pattern in _SUSPICIOUS_PATTERNS
    )
