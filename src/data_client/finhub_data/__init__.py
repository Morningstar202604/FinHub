"""finhub-data REST client package.

Provides :class:`FinHubDataClient` for fetching aggregates from the
finhub-data market data proxy service.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from .client import FinHubDataClient
from .mcp_client import DAILY_INTERVALS, FinHubMCPClient, split_date_time

__all__ = [
    "DAILY_INTERVALS",
    "FinHubDataClient",
    "FinHubMCPClient",
    "close_finhub_data_client",
    "close_finhub_mcp_client",
    "get_finhub_data_client",
    "get_finhub_mcp_client",
    "split_date_time",
]

# -- Host-side singleton (service-token auth) --------------------------------

_client: Optional[FinHubDataClient] = None
_lock = asyncio.Lock()


async def get_finhub_data_client() -> FinHubDataClient:
    """Get or create a singleton :class:`FinHubDataClient`."""
    global _client
    async with _lock:
        if _client is None:
            from src.config.settings import FINHUB_DATA_URL

            service_token = __import__("os").getenv("INTERNAL_SERVICE_TOKEN", "")
            _client = FinHubDataClient(base_url=FINHUB_DATA_URL, service_token=service_token)
        return _client


async def close_finhub_data_client() -> None:
    """Close the singleton client (call on shutdown)."""
    global _client
    async with _lock:
        if _client is not None:
            await _client.close()
            _client = None


# -- Sandbox-side singleton (OAuth token-file auth) --------------------------

_mcp_client: Optional[FinHubMCPClient] = None


def get_finhub_mcp_client() -> FinHubMCPClient:
    """Get or create a singleton :class:`FinHubMCPClient`."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = FinHubMCPClient()
    return _mcp_client


async def close_finhub_mcp_client() -> None:
    """Close the singleton MCP client (call on shutdown)."""
    global _mcp_client
    if _mcp_client is not None:
        await _mcp_client.close()
        _mcp_client = None
