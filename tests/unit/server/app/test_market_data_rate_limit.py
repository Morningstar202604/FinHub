"""Rate-limit graceful degradation on the market-data router.

When the only upstream provider is throttled (e.g. yfinance YFRateLimitError),
the API layer must answer 503 Service Unavailable with a friendly, retryable
message and a Retry-After hint — never a 500 that leaks the raw upstream
error verbatim.
"""

from fastapi import HTTPException

from src.data_client.base import MarketDataRateLimited
from src.server.app.market_data import _market_data_error, _rate_limited


class TestRateLimited:
    def test_matches_typed_exception(self):
        exc = MarketDataRateLimited("Market data provider (yfinance) is rate limited")
        assert _rate_limited(str(exc))

    def test_matches_yfinance_message_string(self):
        # Cache services stringify the exception before the router sees it.
        assert _rate_limited("Too Many Requests. Rate limited. Try after a while.")

    def test_matches_http_429_marker(self):
        assert _rate_limited("HTTP 429 Too Many Requests")

    def test_does_not_match_generic_errors(self):
        assert not _rate_limited("Connection reset by peer")
        assert not _rate_limited("No data source supports get_snapshots")
        assert not _rate_limited("")


class TestMarketDataError:
    def test_rate_limited_returns_503_with_retry_after(self):
        http = _market_data_error("Too Many Requests. Rate limited.")
        assert isinstance(http, HTTPException)
        assert http.status_code == 503
        assert "rate limited" in http.detail.lower()
        assert http.headers.get("Retry-After") == "60"

    def test_typed_rate_limited_returns_503(self):
        http = _market_data_error(MarketDataRateLimited())
        assert http.status_code == 503

    def test_generic_error_stays_500_with_detail(self):
        http = _market_data_error("Connection reset by peer")
        assert isinstance(http, HTTPException)
        assert http.status_code == 500
        assert http.detail == "Connection reset by peer"
