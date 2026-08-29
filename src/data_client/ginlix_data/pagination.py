"""Shared cursor-based pagination for ginlix-data endpoints."""

from __future__ import annotations

from typing import Any, Awaitable, Callable


async def paginate_cursor(
    fetch_page: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    params: dict[str, Any],
    limit: int,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Generic cursor-based pagination loop.

    *fetch_page* receives the current params dict and must return a response
    body dict with ``results`` (list) and optional ``next_cursor`` (str).

    The loop stops when:
    - no ``next_cursor`` in the response, or
    - ``len(collected) >= limit``, or
    - *max_pages* pages have been fetched.

    Returns the collected results truncated to *limit*.
    """
    all_results: list[dict[str, Any]] = []
    params = dict(params)  # avoid mutating caller's dict

    for _ in range(max_pages):
        body = await fetch_page(params)
        all_results.extend(body.get("results", []))
        next_cursor = body.get("next_cursor")
        if not next_cursor or len(all_results) >= limit:
            break
        params["cursor"] = next_cursor

    return all_results[:limit]
