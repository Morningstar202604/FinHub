"""ginlix-data implementation of MarketIntelSource."""

from __future__ import annotations

import logging
from typing import Any

from .client import GinlixDataClient
from .data_source import INTERVAL_MAP

logger = logging.getLogger(__name__)


class GinlixMarketIntelSource:
    """ginlix-data implementation of MarketIntelSource."""

    def __init__(self, client: GinlixDataClient) -> None:
        self.client = client

    async def get_options_chain(
        self, underlying: str, user_id: str | None = None, **filters: Any
    ) -> dict[str, Any]:
        return await self.client.get_options_contracts(
            underlying_ticker=underlying, user_id=user_id, **filters
        )

    async def get_options_ohlcv(
        self,
        options_ticker: str,
        from_date: str | None = None,
        to_date: str | None = None,
        interval: str = "1hour",
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if interval not in INTERVAL_MAP:
            raise ValueError(f"Unsupported interval: {interval}")
        timespan, multiplier = INTERVAL_MAP[interval]
        results, _ = await self.client.get_aggregates(
            market="option",
            symbol=options_ticker,
            timespan=timespan,
            multiplier=multiplier,
            from_date=from_date,
            to_date=to_date,
            user_id=user_id,
        )
        return results

    async def get_short_interest(
        self,
        symbol: str,
        limit: int = 500,
        sort: str = "settlement_date.asc",
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.client.get_short_interest(
            symbol, limit=limit, sort=sort, user_id=user_id,
        )

    async def get_short_volume(
        self,
        symbol: str,
        limit: int = 500,
        sort: str = "date.asc",
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.client.get_short_volume(
            symbol, limit=limit, sort=sort, user_id=user_id,
        )

    async def get_float_shares(
        self, symbol: str, user_id: str | None = None
    ) -> dict[str, Any]:
        return await self.client.get_float(symbol, user_id=user_id)

    async def get_options_snapshot(
        self,
        tickers: list[str],
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.client.get_snapshots("options", tickers, user_id=user_id)

    async def get_movers(
        self, direction: str = "gainers", user_id: str | None = None
    ) -> list[dict[str, Any]]:
        return await self.client.get_movers(direction, user_id=user_id)

    async def close(self) -> None:
        pass  # client lifecycle managed by get_ginlix_data_client singleton
