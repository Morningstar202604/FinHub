"""Backward-compatible re-export — use ``data_source`` instead."""

from .data_source import FMPDataSource as FMPPriceProvider  # noqa: F401

__all__ = ["FMPPriceProvider"]
