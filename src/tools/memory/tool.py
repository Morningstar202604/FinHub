"""Memory tools (ROADMAP M2-E): BM25 recall over long-term memory docs.

A deterministic, provider-free keyword recall tool. The agent passes the
contents of candidate memory sources (agent.md, workspace memory.md, memo
files, prior research results) plus a query; the tool chunk + BM25-ranks
them and returns the most relevant excerpts inside a strict token budget.
No embedding provider is required, so the capability works with zero extra
credentials (the ROADMAP's "BM25 fallback" path).
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from .retrieval import DEFAULT_BUDGET_TOKENS, build_chunks, recall

__all__ = ["recall_memory"]


@tool(response_format="content_and_artifact")
async def recall_memory(
    query: str,
    config: RunnableConfig,
    documents: dict[str, str] | None = None,
    top_k: int = 3,
) -> tuple[str, dict[str, Any]]:
    """Recall the most relevant excerpts from your long-term memory documents, ranked by keyword relevance.

    Use this when an answer depends on prior context that is not already in
    the conversation: earlier research conclusions, user preferences in
    memory.md, memo files, or workspace notes. Pass the contents of the
    relevant files and this tool returns the best-matching excerpts with their
    source labels — saving you from re-reading entire files.

    Args:
        query: What you are trying to remember (keywords / a question).
        documents: Map of source name -> full text content. Example:
            {"workspace/memory.md": "...", "notes: nvda thesis": "..."}
        top_k: Max excerpts to return (default 3).
    """
    if not documents:
        return (
            "未提供任何记忆文档（documents 为空）。请先 Read 相关记忆文件后把内容传入。",
            {"hits": [], "budget_tokens": DEFAULT_BUDGET_TOKENS},
        )
    docs = build_chunks(documents.items())
    hits = recall(query, docs, top_k=top_k)
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"[{i}] 来源: {h.source}  (分数 {h.score:.2f}, {h.chars} 字符)\n{h.text}"
        )
    if not lines:
        lines.append("未在提供的记忆文档中找到与查询相关的内容。")
    content = "\n\n".join(lines)
    artifact = {
        "query": query,
        "hits": [
            {"source": h.source, "score": h.score, "chars": h.chars, "text": h.text}
            for h in hits
        ],
        "budget_tokens": DEFAULT_BUDGET_TOKENS,
    }
    return content, artifact