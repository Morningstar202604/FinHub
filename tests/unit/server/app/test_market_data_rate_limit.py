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
        # A real defect the feed can't explain — NOT a throttle, NOT an outage.
        # "Connection reset by peer" used to sit here, but a reset transport is
        # an unreachable upstream and is deliberately reclassified as a
        # retryable 503 now (see test_market_data_api.test_upstream_outage_*).
        http = _market_data_error("No data source supports get_snapshots")
        assert isinstance(http, HTTPException)
        assert http.status_code == 500
        assert http.detail == "No data source supports get_snapshots"

    def test_unreachable_upstream_is_503_not_500(self):
        """A dead feed is an outage, not our bug.

        Reported as 500 it reads as "FinHub broke", and — worse — it lands
        inside the client's retry budget, so the browser re-requests three
        times something that cannot succeed until the vendor recovers. The
        transport-level spellings below are the ones real vendors emit:
        a TLS-dropping proxy surfaces as the BoringSSL line, and an SDK that
        wraps requests-to surfaces "Max retries exceeded".
        """
        for text in (
            "Connection reset by peer",
            "Connection refused",
            "Read timed out",
            "Failed to perform, curl: (35) BoringSSL SSL_connect: Connection closed "
            "abruptly (SSL_ERROR_SYSCALL; error queue empty)",
            "HTTPSConnectionPool(host='query1.finance.yahoo.com', port=443): Max retries "
            "exceeded with url: /v8/finance/chart/AAPL",
            "502 Bad Gateway",
        ):
            http = _market_data_error(text)
            assert http.status_code == 503, f"{text!r} should be a retryable outage"
            assert http.headers.get("Retry-After") == "30"
