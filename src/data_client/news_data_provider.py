"""Composite news data provider with sequential fallback."""

from __future__ import annotations

import logging
from typing import Any

from .base import NewsDataSource

logger = logging.getLogger(__name__)


class NewsDataProvider:
    """Tries each news source in order, falling back on failure."""

    def __init__(self, sources: list[tuple[str, NewsDataSource]]) -> None:
        self._sources = sources

    async def get_news(self, **kwargs: Any) -> dict[str, Any]:
        last_exc: Exception | None = None
        for name, source in self._sources:
            try:
                return await source.get_news(**kwargs)
            except Exception as exc:
                logger.warning("news.fallback | source=%s err=%s", name, exc)
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    async def get_news_article(
        self, article_id: str, user_id: str | None = None
    ) -> dict[str, Any] | None:
        """Try each source until one returns the article."""
        for name, source in self._sources:
            try:
                result = await source.get_news_article(article_id, user_id=user_id)
                if result is not None:
                    return result
            except Exception as exc:
                logger.warning("news.article_fallback | source=%s err=%s", name, exc)
        return None

    async def close(self) -> None:
        for name, source in self._sources:
            try:
                await source.close()
            except Exception:
                logger.warning("news.close | source=%s failed", name, exc_info=True)

    @property
    def source_names(self) -> list[str]:
        return [name for name, _ in self._sources]
