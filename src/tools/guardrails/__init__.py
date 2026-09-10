"""Guardrails utilities (ROADMAP M2-H)."""

from contextvars import ContextVar
from typing import Any, Dict

from .pii import InjectionFinding, detect_prompt_injection, redact_pii

# Per-request constraint-layer verdict, set by the chat request prep layer
# (normalize_request_messages) and read by the SSE producer so the guardrails
# outcome (PII redactions + injection hits) can be streamed and persisted.
# Lives here — the lowest tier either side may import — rather than in the
# request-prep or SSE modules, to keep the app → handlers → services → database
# layer contract intact (services must not import handlers).
guardrails_ctx: ContextVar[Dict[str, Any]] = ContextVar("guardrails_ctx", default={})

__all__ = [
    "InjectionFinding",
    "detect_prompt_injection",
    "guardrails_ctx",
    "redact_pii",
]