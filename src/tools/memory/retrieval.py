"""BM25 retrieval over filtered long-term memory (ROADMAP M2-E).

Pure keyword BM25 fallback — no embedding provider required. The ranking is
delegated to the ``rank_bm25`` library (BM25Okapi); this module only handles
what a memory recall needs on top: deterministic text chunking (CJK-aware),
a token budget so recall never floods the context window, and stable
top-k ordering with source metadata.

Designed to be provider-agnostic: callers supply the document strings (e.g.
the contents of ``agent.md``, workspace ``memory.md``, memo files, or prior
research results read from the workspace), this module scores and returns
the most relevant excerpts.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from rank_bm25 import BM25Plus

# Rough CJK-token budget guard: one CJK char ≈ 1 token on most providers, so a
# char-count cap is a safe local proxy for the injection budget from the
# ROADMAP (≤1200 tokens).
DEFAULT_BUDGET_TOKENS = 1200
_CHUNK_CHARS = 300
_CHUNK_OVERLAP = 40

# Tokenizer: CJK text is split per character (with a small overlap window);
# latin/digit runs become single tokens. This is intentionally simple — a full
# segmentation library (jieba) is overkill for a keyword fallback.
_CJK = re.compile(r"[\u3000-\u9fff\uf900-\ufaff]")

_ASCII_TOKEN = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class RecallHit:
    """One recall result: the excerpt plus where it came from."""

    text: str
    source: str = ""
    score: float = 0.0
    chars: int = 0


@dataclass
class _Doc:
    id: str
    title: str
    chunks: list[str] = field(default_factory=list)


def tokenize(text: str) -> list[str]:
    """Tokenize mixed CJK + latin text for BM25.

    CJK characters are emitted individually so short multi-char queries still
    match; latin words/numbers are kept whole. This keeps the fallback
    dependency-free while ranking sensibly for finance research notes.
    """
    tokens: list[str] = []
    for piece in re.split(r"\s+", text):
        seg = _cjk_segments(piece)
        tokens.extend(seg)
    return tokens


def _cjk_segments(piece: str) -> list[str]:
    out: list[str] = []
    buffer: list[str] = []
    for ch in piece:
        if _CJK.match(ch):
            if buffer:
                out.append("".join(buffer))
                buffer = []
            out.append(ch)
        else:
            buffer.append(ch)
    if buffer:
        out.append("".join(buffer))
    return out


def _truncate(text: str, budget: int) -> str:
    """Cut at a sentence/newline boundary when under ``budget`` chars of room."""
    if len(text) <= budget:
        return text
    head = text[:budget]
    cut = max(head.rfind("\n"), head.rfind("。"), head.rfind(". "))
    if cut <= 0:
        cut = budget
    return text[:cut].rstrip() + "…"


def chunk_text(text: str, chunk_chars: int = _CHUNK_CHARS, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split a long document into overlapping CJK-aware chunks.

    Uses rare-character-free character windows (300 chars, 40 overlap per the
    ROADMAP) so long reports become several searchable units while a claim
    crossing a boundary stays findable.
    """
    text = unicodedata.normalize("NFKC", text or "")
    if len(text) <= chunk_chars:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_chars])
        start += chunk_chars - overlap
        if len(chunks) > 500:
            break  # defensive cap for pathological inputs
    return chunks


def build_chunks(docs: Iterable[tuple[str, str]]) -> list[_Doc]:
    """Build chunked docs from (id, content) pairs."""
    result: list[_Doc] = []
    for doc_id, content in docs:
        chunks = chunk_text(content)
        if not chunks:
            continue
        title = chunks[0].splitlines()[0][:80] if chunks[0].splitlines() else ""
        # Repeated chunks are wasted BM25 corpus; dedupe.
        seen: set[str] = set()
        unique: list[str] = []
        for c in chunks:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        result.append(_Doc(id=doc_id, title=title or doc_id, chunks=unique))
    return result


def recall(
    query: str,
    docs: Sequence[_Doc],
    top_k: int = 3,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
) -> list[RecallHit]:
    """BM25 top-k recall over pre-chunked docs, within a token budget.

    Empty queries, an empty corpus, or a query scoring below a tiny floor
    return [] (graceful degradation for memoryless workspaces).
    """
    if not query or not docs:
        return []
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    corpus: list[list[str]] = []
    lookup: list[tuple[_Doc, int]] = []
    for doc in docs:
        for idx, chunk in enumerate(doc.chunks):
            corpus.append(tokenize(chunk))
            lookup.append((doc, idx))

    try:
        # BM25Plus (not Okapi): its idf carries a +1 delta, so tiny corpora
        # (a handful of memory chunks) don't collapse to zero scores the way
        # Okapi's log(doc_count/df) does when a term matches ~half the docs.
        bm25 = BM25Plus(corpus)
        scores = bm25.get_scores(query_tokens)
    except ValueError:
        return []  # empty/identical corpus edge cases

    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    hits: list[RecallHit] = []
    used = 0
    for i in order:
        if scores[i] <= 0:
            continue
        doc, chunk_idx = lookup[i]
        text = doc.chunks[chunk_idx]
        remaining = budget_tokens - used
        if remaining <= 0:
            break
        excerpt = _truncate(text, remaining)
        hits.append(
            RecallHit(
                text=excerpt,
                source=doc.id,
                score=float(scores[i]),
                chars=len(excerpt),
            )
        )
        used += len(excerpt)
        if len(hits) >= top_k:
            break
    return hits