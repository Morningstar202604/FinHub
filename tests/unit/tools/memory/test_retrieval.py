"""BM25 memory recall (M2-E) — chunking, ranking, token budget, degradation."""

import pytest

from src.tools.memory.retrieval import (
    DEFAULT_BUDGET_TOKENS,
    build_chunks,
    chunk_text,
    recall,
    tokenize,
)


def _docs(pairs):
    return build_chunks(pairs)


class TestTokenizer:
    def test_mixed_cjk_latin(self):
        toks = tokenize("AI 数据中心与 GPU 需求")
        assert "AI" in toks
        assert "GPU" in toks
        assert "数" in toks  # CJK split per char
        assert "据" in toks

    def test_numbers_and_words(self):
        toks = tokenize("revenue 18,000 2026")
        assert "revenue" in toks
        # "18,000" is one token (latin/digit/punct run, not CJK).
        assert "18,000" in toks
        assert "2026" in toks


class TestChunking:
    def test_short_text_single_chunk(self):
        assert chunk_text("短文本") == ["短文本"]

    def test_long_text_overlapping_chunks(self):
        text = "字" * 700
        chunks = chunk_text(text, chunk_chars=300, overlap=40)
        assert len(chunks) >= 3
        # Overlap guarantees a boundary claim stays findable.
        assert sum("字" in c for c in chunks) == len(chunks)

    def test_empty(self):
        assert chunk_text("") == []

    def test_nfkc_normalization(self):
        assert chunk_text("\uff21BC") == ["ABC"]


class TestRecall:
    def test_ranks_relevant_doc_first(self):
        docs = _docs(
            [
                ("memory.md", "用户偏好：偏好成长股，重视毛利率。"),
                ("research.md", "NVDA 数据中心收入占总营收 88%。"),
            ]
        )
        hits = recall("毛利率 偏好", docs, top_k=3)
        assert hits and hits[0].source == "memory.md"

    def test_relevant_keyword_wins(self):
        docs = _docs(
            [
                ("a.md", "苹果的市盈率是 30 倍。"),
                ("b.md", "特斯拉交付量同比增长 40%。"),
                ("c.md", "AMD 数据中心收入创新高。"),
            ]
        )
        hits = recall("特斯拉 交付量", docs, top_k=1)
        assert hits and hits[0].source == "b.md"

    def test_token_budget_truncates(self):
        long = "收益翻倍" + "非常长的内容" * 2000
        docs = _docs([("long.md", long)])
        hits = recall("收益", docs, top_k=3, budget_tokens=120)
        assert hits
        total = sum(h.chars for h in hits)
        assert total <= 120 + 5  # truncation suffix slack

    def test_empty_query_or_docs_degrade(self):
        assert recall("", _docs([("a", "x")])) == []
        assert recall("q", []) == []
        assert recall("q", _docs([("a", "x")]), top_k=0) == []

    def test_dedup_chunks(self):
        text = "同一段" * 5  # repeated -> all chunks identical
        docs = _docs([("dup.md", text * 200)])
        # build_chunks dedupes; recall must not crash on near-identical corpus.
        hits = recall("同一段", docs, top_k=3)
        assert isinstance(hits, list)


class TestToolContract:
    def test_tool_importable_and_decorated(self):
        from src.tools.memory.tool import recall_memory

        # LangChain wraps the fn into a StructuredTool instance.
        assert getattr(recall_memory, "name", None) == "recall_memory"
        assert getattr(recall_memory, "args_schema", None) is not None

    def test_default_budget_constant(self):
        assert DEFAULT_BUDGET_TOKENS == 1200