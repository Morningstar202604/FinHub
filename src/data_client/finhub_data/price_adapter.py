"""Backward-compatible re-export — use ``data_source`` instead."""

from .data_source import FinHubDataSource as FinHubDataPriceProvider  # noqa: F401

__all__ = ["FinHubDataPriceProvider"]
