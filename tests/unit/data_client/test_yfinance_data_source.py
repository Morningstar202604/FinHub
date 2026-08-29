"""Unit tests for the yfinance data source — no network."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from yfinance.exceptions import YFRateLimitError

from src.data_client.base import MarketDataRateLimited
from src.data_client.yfinance.data_source import (
    YFinanceDataSource,
    _fetch_history,
    _fetch_single_snapshot,
)


def _history_kwargs(**call_kwargs) -> dict:
    """Run _fetch_history with a stubbed Ticker; return the kwargs it passed."""
    ticker = MagicMock()
    ticker.history.return_value = None  # empty result — we only care about kwargs
    with patch("src.data_client.yfinance.data_source.yf.Ticker", return_value=ticker):
        _fetch_history("0700.HK", "1m", **call_kwargs)
    return ticker.history.call_args.kwargs


def test_fetch_history_end_date_is_inclusive():
    """to_date is inclusive per the provider contract, but yfinance's ``end``
    is an exclusive exchange-local midnight. Without the +1-day shift, a window
    ending on the current venue date silently drops today's live session —
    non-US charts froze on the prior session (frozen 0700.HK chart bug).
    """
    kwargs = _history_kwargs(start="2026-07-03", end="2026-07-06")
    assert kwargs["start"] == "2026-07-03"
    assert kwargs["end"] == "2026-07-07"


def test_fetch_history_open_ended_window_has_no_end_bound():
    kwargs = _history_kwargs(start="2026-07-03", end=None)
    assert kwargs["start"] == "2026-07-03"
    assert "end" not in kwargs


def test_fetch_history_unparseable_end_passes_through():
    kwargs = _history_kwargs(start=None, end="garbage")
    assert kwargs["end"] == "garbage"


def test_fetch_history_rate_limit_raises_market_data_rate_limited():
    """A yfinance YFRateLimitError must surface as the typed MarketDataRateLimited
    so the API layer answers 503 instead of a 500 with the raw message."""
    ticker = MagicMock()
    ticker.history.side_effect = YFRateLimitError()
    with (
        patch("src.data_client.yfinance.data_source.yf.Ticker", return_value=ticker),
        pytest.raises(MarketDataRateLimited) as excinfo,
    ):
        _fetch_history("AAPL", "1m", None, None)
    assert "rate limited" in str(excinfo.value).lower()
    assert excinfo.value.retry_after_s > 0


def test_fetch_history_generic_error_not_classified_as_rate_limit():
    """Only YFRateLimitError maps to MarketDataRateLimited; unrelated failures
    propagate untouched so the provider chain can fall back to another source."""
    ticker = MagicMock()
    ticker.history.side_effect = ValueError("boom")
    with (
        patch("src.data_client.yfinance.data_source.yf.Ticker", return_value=ticker),
        pytest.raises(ValueError, match="boom"),
    ):
        _fetch_history("AAPL", "1m", None, None)


def test_fetch_single_snapshot_rate_limit_raises_market_data_rate_limited():
    class _RateLimitedTicker:
        @property
        def fast_info(self):
            raise YFRateLimitError()

    with (
        patch(
            "src.data_client.yfinance.data_source.yf.Ticker",
            return_value=_RateLimitedTicker(),
        ),
        pytest.raises(MarketDataRateLimited),
    ):
        _fetch_single_snapshot("AAPL")


@pytest.mark.asyncio
async def test_get_snapshots_returns_bare_index_symbol():
    """Indices are queried from Yahoo with a caret ("^GSPC"), but the snapshot
    must echo back the bare requested symbol ("GSPC") so the provider chain
    matches it instead of dropping it as unrequested. Regression for #287.
    """
    def fake_fetch(sym: str) -> dict:
        # Mirrors the real fetch: echoes whatever symbol it was queried with.
        return {"symbol": sym, "price": 5000.0}

    with patch(
        "src.data_client.yfinance.data_source._fetch_single_snapshot",
        side_effect=fake_fetch,
    ):
        result = await YFinanceDataSource().get_snapshots(
            ["GSPC"], asset_type="indices"
        )

    assert result == [{"symbol": "GSPC", "price": 5000.0}]


@pytest.mark.asyncio
async def test_get_snapshots_preserves_order_and_drops_failures():
    """Symbol restoration stays aligned when a fetch returns None."""
    def fake_fetch(sym: str) -> dict | None:
        return None if sym == "^IXIC" else {"symbol": sym, "price": 1.0}

    with patch(
        "src.data_client.yfinance.data_source._fetch_single_snapshot",
        side_effect=fake_fetch,
    ):
        result = await YFinanceDataSource().get_snapshots(
            ["GSPC", "IXIC", "DJI"], asset_type="indices"
        )

    assert [r["symbol"] for r in result] == ["GSPC", "DJI"]


@pytest.mark.asyncio
async def test_get_snapshots_stocks_pass_symbol_through_unchanged():
    """Stocks aren't caret-prefixed; the symbol is returned as requested."""
    def fake_fetch(sym: str) -> dict:
        return {"symbol": sym, "price": 190.0}

    with patch(
        "src.data_client.yfinance.data_source._fetch_single_snapshot",
        side_effect=fake_fetch,
    ):
        result = await YFinanceDataSource().get_snapshots(["AAPL"])

    assert result == [{"symbol": "AAPL", "price": 190.0}]
