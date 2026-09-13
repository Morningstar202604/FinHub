"""Guardrails (ROADMAP M2-H) — prompt-injection detection & PII redaction.

Pure-rule, offline, zero external calls. Two surfaces:

1. ``detect_prompt_injection(text)`` — scans user-uploaded documents / skill
   bodies / memo text for classic prompt-injection patterns ("ignore previous
   instructions", "you are now", system-prompt overrides, etc.). Returns the
   matched patterns so a caller can block or quarantine the content.
2. ``redact_pii(text)`` — redacts common PII shapes (ID-card numbers, bank
   cards, phone numbers, emails, API-key-like secrets) on a best-effort,
   Chinese + international basis. Complements SecretRedactor (which guards
   known app secrets); this one is pattern-based for unknown/foreign values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Prompt-injection patterns (ordered by strength). Deliberately *not*
# exhaustive — these are the well-known archetypes; the rule layer is a cheap
# pre-filter, not a security boundary (callers still run the sandboxed
# execution + provenance gate).
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ignore_previous",
     re.compile(r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|commands)", re.I)),
    ("ignore_above",
     re.compile(r"ignore\s+everything\s+(above|before|previously)", re.I)),
    ("system_override",
     re.compile(r"(you\s+are|act\s+as|pretend\s+to\s+be)\s+(now\s+)?(an?\s+)?(unrestricted|jailbroken|developer\s+mode|root|admin|gpt)", re.I)),
    ("new_persona",
     re.compile(r"from\s+now\s+on,?\s+you\s+(are|should|must)", re.I)),
    ("reveal_prompt",
     re.compile(r"(reveal|print|output|show)\s+(your\s+)?(system\s+)?prompt", re.I)),
    ("secret_exfil",
     re.compile(r"(steal|exfiltrate|dump)\s+(all\s+)?(api\s+keys?|secrets?|tokens?|credentials?)", re.I)),
    ("delimiters_bypass",
     re.compile(r"(disregard|bypass|override)\s+(the\s+)?(rules|instructions|filters|guardrails)", re.I)),
    ("xml_escape_attempt",
     re.compile(r"<system[^>]*>|</system\s*>", re.I)),
    # --- Chinese variants (FinHub is a CN-first product) ----------------------
    ("ignore_previous_cn",
     re.compile(r"忽略(所有|以上|之前|前面的)?(指令|指示|要求|提示词?|规则)", re.I)),
    ("ignore_above_cn",
     re.compile(r"(无视|不要理会|不必遵循)(以上|下面|之前)(的)?(所有|全部)?(内容|指令|指示|要求|规则)", re.I)),
    ("system_override_cn",
     re.compile(r"你是(现在)?(无限制|越狱|开发者模式|不受约束|管理员|root)((的)?(AI|模型|助手|gpt))?", re.I)),
    ("reveal_prompt_cn",
     re.compile(r"(输出|显示|打印|泄漏|告诉我)\s*(你(的)?\s*)?((系统\s*)?提示词|系统提示|指令|system\s*prompt)", re.I)),
    ("new_persona_cn",
     re.compile(r"从现在(起|开始),?\s*你(就)?(要|是|扮演|假装|必须|应该)", re.I)),
)


@dataclass(frozen=True)
class InjectionFinding:
    pattern: str
    snippet: str


def detect_prompt_injection(text: str, max_snippets: int = 5) -> list[InjectionFinding]:
    """Return injection-pattern matches found in ``text`` (empty = clean)."""
    findings: list[InjectionFinding] = []
    for name, pattern in _INJECTION_PATTERNS:
        for m in pattern.finditer(text):
            start = max(0, m.start() - 30)
            snippet = text[start : m.end() + 30].strip()
            findings.append(InjectionFinding(pattern=name, snippet=snippet))
            if len(findings) >= max_snippets:
                return findings
    return findings


# ---------------------------------------------------------------------------
# PII redaction — pattern-based; masks with fixed-length asterisks.
# ---------------------------------------------------------------------------

# Chinese ID card: 15/18 digits with checksum letter; beware phone overlap,
# so require 17-18 chars or validate region prefix loosely.
_ID_CARD_RE = re.compile(r"(?<!\d)([1-9]\d{5}(19|20)?\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)")
# Bank card / generic 16-19 digit runs.
_BANK_CARD_RE = re.compile(r"(?<!\d)(\d{16,19})(?!\d)")
# Mobile CN: 1[3-9]\d{9}
_CN_MOBILE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
# International-ish phone with + prefix.
_INTL_PHONE_RE = re.compile(r"(?<!\w)(\+\d{1,3}[\s\-]?\d{6,12})(?!\w)")
# Email.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# API-key / token-like: 20-64 base64-ish chars after a key= flag or prominent label.
_API_KEY_RE = re.compile(
    r"(?i)((?:api[_-]?key|token|secret|password|sk-[a-z0-9]{20,})\s*[=:]\s*)([A-Za-z0-9_\-\.]{20,64})"
)


def redact_pii(text: str) -> str:
    """Mask PII shapes in ``text``; returns the redacted copy."""
    result = text
    result = _ID_CARD_RE.sub(lambda m: _mask(m.group(1)), result)
    result = _BANK_CARD_RE.sub(lambda m: _mask(m.group(1)), result)
    result = _CN_MOBILE_RE.sub(lambda m: _mask(m.group(1)), result)
    result = _INTL_PHONE_RE.sub(lambda m: _mask(m.group(1)), result)
    # Emails: mask local-part, keep the @domain readable.
    result = _EMAIL_RE.sub(lambda m: _mask_email(m.group(0)), result)
    # API keys: keep the label, mask the value.
    result = _API_KEY_RE.sub(
        lambda m: f"{m.group(1)}{_mask(m.group(2), keep_tail=4)}", result
    )
    return result


def _mask(value: str, keep_head: int = 3, keep_tail: int = 0) -> str:
    """Replace most of ``value`` with asterisks, keeping a readable head/tail."""
    if len(value) <= keep_head + keep_tail + 3:
        return "*" * len(value)
    return value[:keep_head] + "*" * (len(value) - keep_head - keep_tail) + (
        value[-keep_tail:] if keep_tail else ""
    )


def _mask_email(value: str) -> str:
    """Mask the local part of an email, keep the domain: `aa**@example.com`.

    Very short local parts (<=2 chars) would otherwise survive untouched —
    still PII, still leaks — so they get fully masked instead.
    """
    if "@" not in value:
        return _mask(value)
    local, _, domain = value.partition("@")
    if len(local) <= 2:
        return "*" * len(local) + "@" + domain
    return local[:2] + "*" * min(8, len(local) - 2) + "@" + domain