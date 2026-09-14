"""Canonical schema ids ⇄ legacy interval strings ⇄ bar period seconds.

The legacy strings ("1min", "1hour", …) are the FMP-style spellings used by
today's REST API, cache keys, and provider interfaces. They remain the wire
format of the legacy endpoints indefinitely; protocol endpoints speak schema
ids only.
"""

from __future__ import annotations

from typing import Literal

from .enums import OHLCV_SCHEMAS

_LEGACY_BY_SCHEMA: dict[str, str] = {
    "ohlcv-1s": "1s",
    "ohlcv-1m": "1min",
    "ohlcv-5m": "5min",
    "ohlcv-15m": "15min",
    "ohlcv-30m": "30min",
    "ohlcv-1h": "1hour",
    "ohlcv-4h": "4hour",
    "ohlcv-1d": "1day",
}

_SCHEMA_BY_LEGACY: dict[str, str] = {v: k for k, v in _LEGACY_BY_SCHEMA.items()}

# Keep in sync with src/utils/market_hours._INTERVAL_SECONDS (parity-tested).
_SECONDS_BY_SCHEMA: dict[str, int] = {
    "ohlcv-1s": 1,
    "ohlcv-1m": 60,
    "ohlcv-5m": 300,
    "ohlcv-15m": 900,
    "ohlcv-30m": 1800,
    "ohlcv-1h": 3600,
    "ohlcv-4h": 14400,
    "ohlcv-1d": 86400,
}

if set(_LEGACY_BY_SCHEMA) != set(OHLCV_SCHEMAS):
    raise RuntimeError("intervals: _LEGACY_BY_SCHEMA drifted from OHLCV_SCHEMAS")
if set(_SECONDS_BY_SCHEMA) != set(OHLCV_SCHEMAS):
    raise RuntimeError("intervals: _SECONDS_BY_SCHEMA drifted from OHLCV_SCHEMAS")

# The legacy interval spellings as a Literal type, for use in Pydantic models
# and FastAPI Query params.
#
# This lives here rather than in the chart-annotation tool package because it is
# market vocabulary, not tool vocabulary: the server's own request models and
# query params need it too, and a tool must not be the home of a type the server
# layer depends on (that inversion is tracked by the [tool.importlinter] contract
# in pyproject.toml).
#
# Deliberately NOT the full OHLCV_SCHEMAS set: 1-second bars ("1s" / ohlcv-1s)
# are real data but not a chartable timeframe — no chart instance can exist on
# them (chart_id is SYMBOL:timeframe) and the market-data API never serves them
# to the chart card. So this is "schema ids that can appear in a chart request",
# a strict subset. The guard below asserts the subset relationship rather than
# equality, so adding a new schema to OHLCV_SCHEMAS does not silently widen the
# set of timeframes the LLM may ask a chart for.
_CHARTABLE_SCHEMAS: tuple[str, ...] = tuple(
    s for s in OHLCV_SCHEMAS if s != "ohlcv-1s"
)
Timeframe = Literal[
    "1min", "5min", "15min", "30min", "1hour", "4hour", "1day"
]

if set(Timeframe.__args__) != {_LEGACY_BY_SCHEMA[s] for s in _CHARTABLE_SCHEMAS}:
    raise RuntimeError("intervals: Timeframe drifted from _CHARTABLE_SCHEMAS")
if not set(_CHARTABLE_SCHEMAS) <= set(OHLCV_SCHEMAS):
    raise RuntimeError("intervals: _CHARTABLE_SCHEMAS is not a subset of OHLCV_SCHEMAS")


def schema_for_legacy(interval: str) -> str:
    """Map a legacy interval string ("1min") to its schema id ("ohlcv-1m")."""
    try:
        return _SCHEMA_BY_LEGACY[interval]
    except KeyError:
        raise ValueError(f"Unknown legacy interval: {interval!r}") from None


def legacy_for_schema(schema: str) -> str:
    """Map a schema id ("ohlcv-1m") to its legacy interval string ("1min")."""
    try:
        return _LEGACY_BY_SCHEMA[schema]
    except KeyError:
        raise ValueError(f"Unknown ohlcv schema: {schema!r}") from None


def schema_seconds(schema: str) -> int:
    """Bar period in seconds for a schema id."""
    try:
        return _SECONDS_BY_SCHEMA[schema]
    except KeyError:
        raise ValueError(f"Unknown ohlcv schema: {schema!r}") from None


def is_intraday_schema(schema: str) -> bool:
    """True for sub-daily schemas."""
    return schema_seconds(schema) < 86400
