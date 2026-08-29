"""Backward-compatible re-export — use ``data_source`` instead."""

from .data_source import GinlixDataSource as GinlixDataPriceProvider  # noqa: F401

__all__ = ["GinlixDataPriceProvider"]
