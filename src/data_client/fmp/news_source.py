"""News data source backed by FMP (Financial Modeling Prep)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from .fmp_client import FMPClient

logger = logging.getLogger(__name__)


def _article_id(article: dict[str, Any]) -> str:
    """Derive a stable ID from the article URL (FMP doesn't provide one)."""
    url = article.get("url") or article.get("link") or ""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _normalize_article(raw: dict[str, Any]) -> dict[str, Any]:
    """Map FMP article schema → common NewsArticle dict."""
    return {
        "id": _article_id(raw),
        "title": raw.get("title", ""),
        "author": None,
        "description": raw.get("text", raw.get("content", "")),
        "published_at": raw.get("publishedDate", raw.get("date", "")),
        "article_url": raw.get("url", raw.get("link", "")),
        "image_url": raw.get("image"),
        "source": {
            "name": raw.get("site", raw.get("publisher", raw.get("source", ""))),
            "logo_url": None,
            "homepage_url": None,
            "favicon_url": None,
        },
        "tickers": [raw["symbol"]] if raw.get("symbol") else [],
        "keywords": [],
        "sentiments": None,
    }


class FMPNewsSource:
    """Fetches news from FMP as a fallback provider."""

    async def get_news(
        self,
        tickers: list[str] | None = None,
        limit: int = 20,
        published_after: str | None = None,
        published_before: str | None = None,
        cursor: str | None = None,
        order: str | None = None,
        sort: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        async with FMPClient() as client:
            if tickers:
                raw = await client.get_stock_news(
                    tickers=",".join(tickers),
                    limit=limit,
                )
            else:
                raw = await client.get_general_news(limit=limit)

        articles = raw if isinstance(raw, list) else []
        results = [_normalize_article(a) for a in articles]

        return {
            "results": results,
            "count": len(results),
            "next_cursor": None,  # FMP uses page-based; no cursor support
        }

    async def get_news_article(
        self, article_id: str, user_id: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch recent articles and return the one matching *article_id*."""
        try:
            async with FMPClient() as client:
                raw = await client.get_general_news(limit=50)
            articles = raw if isinstance(raw, list) else []
            for a in articles:
                normalized = _normalize_article(a)
                if normalized["id"] == article_id:
                    return normalized
        except Exception:
            logger.warning("news.fmp.article_lookup_failed", exc_info=True)
        return None

    async def close(self) -> None:
        pass  # FMPClient is used as context manager per-request
