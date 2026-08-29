"""Composite provider for fundamental + market intelligence data."""

from __future__ import annotations

from .base import FinancialDataSource, MarketIntelSource


class FinancialDataProvider:
    """Bundles a :class:`FinancialDataSource` and a :class:`MarketIntelSource`.

    Either source may be ``None`` if the backing service is unavailable.
    """

    def __init__(
        self,
        financial: FinancialDataSource | None = None,
        intel: MarketIntelSource | None = None,
    ) -> None:
        self.financial = financial
        self.intel = intel

    async def close(self) -> None:
        if self.financial is not None:
            await self.financial.close()
        if self.intel is not None:
            await self.intel.close()
