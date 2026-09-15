"""Route-handler tests for the market-data proxy router (market_data.py).

Complements the pure-helper suites (test_market_data_boundary.py,
test_market_data_rate_limit.py) with the 13 route handlers: contract shaping,
boundary mapping at the HTTP edge, error mapping (rate-limit → 503 +
Retry-After, everything else → 500 sanitized) and cache round trips.
Cache services, the raw cache client and data providers are all stubbed —
the router's job is shaping, not fetching.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.data_client.base import MarketDataRateLimited
from src.server.services.cache.daily_cache_service import DailyFetchResult
from src.server.services.cache.intraday_cache_service import IntradayFetchResult
from tests.conftest import create_test_app

pytestmark = pytest.mark.asyncio

_MS = 1_750_000_000_000  # neutral placeholder anchor (Unix ms)


def _bar(t: int, close: float = 10.0) -> dict:
    return {"time": t, "open": close, "high": close, "low": close, "close": close, "volume": 100}


def _intraday_result(bars, *, symbol="AAPL", interval="1min", error=None) -> IntradayFetchResult:
    return IntradayFetchResult(
        symbol=symbol, interval=interval, data=bars, cached=True, ttl_remaining=60,
        background_refresh_triggered=False, cache_key="ohlcv:AAPL.XNAS:ohlcv-1m",
        watermark=(bars[-1]["time"] if bars else 0), complete=False,
        market_phase="open", truncated=False, header=None, error=error,
    )


def _daily_result(bars, *, symbol="AAPL", error=None) -> DailyFetchResult:
    return DailyFetchResult(
        symbol=symbol, data=bars, cached=True, ttl_remaining=60,
        background_refresh_triggered=False, cache_key="ohlcv:AAPL.XNAS:ohlcv-1d",
        watermark=(bars[-1]["time"] if bars else 0), complete=True,
        market_phase="closed", truncated=False, header=None, error=error,
    )


@contextmanager
def _stub_intraday(intraday_result=None, *, daily_result=None):
    intraday = MagicMock()
    intraday.get_stock_intraday = AsyncMock(return_value=intraday_result)
    intraday.get_index_intraday = AsyncMock(return_value=intraday_result)
    intraday.get_batch_stocks = AsyncMock(return_value=({}, {}, {"total_requests": 0}))
    intraday.get_batch_indexes = AsyncMock(return_value=({}, {}, {"total_requests": 0}))
    daily = MagicMock()
    daily.get_stock_daily = AsyncMock(return_value=daily_result)
    with (
        patch("src.server.app.market_data.IntradayCacheService.get_instance", return_value=intraday),
        patch("src.server.app.market_data.DailyCacheService.get_instance", return_value=daily),
    ):
        yield intraday, daily


def _cache(cached=None):
    c = MagicMock()
    c.get = AsyncMock(return_value=cached)
    c.set = AsyncMock()
    return c


@contextmanager
def _stub_cache_client(cache):
    with patch("src.utils.cache.redis_cache.get_cache_client", return_value=cache):
        yield cache


def _financial(search=None, price_targets=None):
    f = MagicMock()
    if search is not None:
        f.search_stocks = AsyncMock(return_value=search)
    if price_targets is not None:
        f.get_analyst_price_targets = AsyncMock(return_value=price_targets)
    return f


@contextmanager
def _stub_financial_provider(provider):
    with patch("src.data_client.get_financial_data_provider", new=AsyncMock(return_value=provider)):
        yield provider


@contextmanager
def _stub_market_provider(provider):
    with patch("src.data_client.get_market_data_provider", new=AsyncMock(return_value=provider)):
        yield


def _provider_with(financial):
    """Provider mock whose .financial attribute is the given client mock."""
    provider = MagicMock()
    provider.financial = financial
    return provider


@contextmanager
def _stub_quotes(raw):
    svc = MagicMock()
    svc.get_quotes = AsyncMock(return_value=raw)
    with patch("src.server.app.market_data.QuoteCacheService.get_instance", return_value=svc):
        yield svc


@pytest_asyncio.fixture
async def client():
    from src.server.app.market_data import router

    app = create_test_app(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Single stock intraday
# ---------------------------------------------------------------------------


class TestStockIntraday:
    async def test_happy_path_shape(self, client):
        with _stub_intraday(_intraday_result([_bar(_MS)])) as (intraday, _):
            resp = await client.get("/api/v1/market-data/intraday/stocks/aapl")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "AAPL" and body["interval"] == "1min"
        assert body["count"] == 1 and body["data"][0]["close"] == 10.0
        assert body["cache"]["cached"] is True and body["cache"]["ttl_remaining"] == 60
        # lowercase inbound spelling collapsed before the service sees it
        assert intraday.get_stock_intraday.await_args.kwargs["symbol"] == "AAPL"

    async def test_invalid_interval_is_422(self, client):
        with _stub_intraday(_intraday_result([_bar(_MS)])) as (intraday, _):
            resp = await client.get("/api/v1/market-data/intraday/stocks/AAPL?interval=2min")
        assert resp.status_code == 422
        assert "2min" in resp.json()["detail"] and "Supported" in resp.json()["detail"]
        intraday.get_stock_intraday.assert_not_awaited()

    async def test_equity_hint_keeps_colliding_ticker(self, client):
        # Bare COMP auto-detects as the Nasdaq Composite index; the stock
        # endpoint must pin it to the equity so HCom isn't served index data.
        with _stub_intraday(_intraday_result([_bar(_MS)], symbol="COMP")) as (intraday, _):
            resp = await client.get("/api/v1/market-data/intraday/stocks/COMP")
        assert resp.status_code == 200
        assert intraday.get_stock_intraday.await_args.kwargs["symbol"] == "COMP"

    async def test_result_error_rate_limit_maps_503(self, client):
        result = _intraday_result([], error=MarketDataRateLimited("HTTP 429"))
        with _stub_intraday(result):
            resp = await client.get("/api/v1/market-data/intraday/stocks/AAPL")
        assert resp.status_code == 503
        assert resp.headers["retry-after"] == "60"

    async def test_unexpected_exception_maps_through_error_helper(self, client):
        with _stub_intraday(_intraday_result([_bar(_MS)])) as (intraday, _):
            intraday.get_stock_intraday = AsyncMock(
                side_effect=RuntimeError("upstream exploded: HTTP 429"))
            resp = await client.get("/api/v1/market-data/intraday/stocks/AAPL")
        assert resp.status_code == 503  # rate-limit marker in the message, not a raw 500


# ---------------------------------------------------------------------------
# Daily (stocks + indexes, shared _get_daily path)
# ---------------------------------------------------------------------------


class TestDaily:
    async def test_stock_happy_path(self, client):
        with _stub_intraday(daily_result=_daily_result([_bar(_MS)])) as (_, daily):
            resp = await client.get("/api/v1/market-data/daily/stocks/AAPL")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "AAPL" and body["count"] == 1
        assert body["cache"]["complete"] is True
        kwargs = daily.get_stock_daily.await_args.kwargs
        assert kwargs["symbol"] == "AAPL" and kwargs["is_index"] is False

    async def test_index_route_pins_is_index_and_collapses_spelling(self, client):
        with _stub_intraday(daily_result=_daily_result([_bar(_MS)], symbol="GSPC")) as (_, daily):
            resp = await client.get("/api/v1/market-data/daily/indexes/%5EGSPC")
        assert resp.status_code == 200
        assert resp.json()["symbol"] == "GSPC"
        kwargs = daily.get_stock_daily.await_args.kwargs
        assert kwargs["symbol"] == "GSPC" and kwargs["is_index"] is True

    async def test_result_error_rate_limit_maps_503_with_retry_after(self, client):
        result = _daily_result([], error="upstream says: too many requests")
        with _stub_intraday(daily_result=result):
            resp = await client.get("/api/v1/market-data/daily/stocks/AAPL")
        assert resp.status_code == 503
        assert resp.headers["retry-after"] == "60"
        # The 503 is the _market_data_error mapping, not the raw string
        assert "too many requests" not in resp.json()["detail"]

    async def test_result_error_generic_keeps_sanitized_detail(self, client):
        result = _daily_result([], error="conn to postgres://u:hunter2@db:5432/fin failed")
        with _stub_intraday(daily_result=result):
            resp = await client.get("/api/v1/market-data/daily/stocks/AAPL")
        assert resp.status_code == 500
        assert "hunter2" not in resp.json()["detail"]

    async def test_service_exception_is_500_sanitized(self, client):
        with _stub_intraday(daily_result=_daily_result([_bar(_MS)])) as (_, daily):
            daily.get_stock_daily = AsyncMock(
                side_effect=RuntimeError("conn to redis://u:sekret@cache:6379 failed"))
            resp = await client.get("/api/v1/market-data/daily/stocks/AAPL")
        assert resp.status_code == 500
        assert "sekret" not in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Batch intraday (stocks + indexes)
# ---------------------------------------------------------------------------


class TestBatchIntraday:
    async def test_stocks_boundary_maps_and_dedupes(self, client):
        intraday = MagicMock()
        intraday.get_batch_stocks = AsyncMock(
            return_value=({"AAPL": [_bar(_MS)]}, {"MSFT": "not found"},
                          {"total_requests": 2, "cache_hits": 1, "cache_misses": 1,
                           "background_refreshes": 0}))
        with _stub_intraday() as (svc, _):
            svc.get_batch_stocks = intraday.get_batch_stocks
            resp = await client.post(
                "/api/v1/market-data/intraday/stocks",
                json={"symbols": ["aapl", "AAPL.US", "MSFT"], "interval": "5min"},
            )
        assert resp.status_code == 200
        body = resp.json()
        # three spellings collapse to one before the service call
        assert svc.get_batch_stocks.await_args.kwargs["symbols"] == ["AAPL", "MSFT"]
        assert body["results"]["AAPL"][0]["time"] == _MS
        assert body["errors"] == {"MSFT": "not found"}
        assert body["cache_stats"]["cache_hits"] == 1

    async def test_stocks_invalid_interval_is_422(self, client):
        with _stub_intraday() as (svc, _):
            resp = await client.post(
                "/api/v1/market-data/intraday/stocks",
                json={"symbols": ["AAPL"], "interval": "3min"},
            )
        assert resp.status_code == 422
        svc.get_batch_stocks.assert_not_awaited()

    async def test_indexes_boundary_pins_index_class(self, client):
        with _stub_intraday() as (svc, _):
            resp = await client.post(
                "/api/v1/market-data/intraday/indexes",
                json={"symbols": ["^GSPC", "I:SPX", "IXIC"], "interval": "1hour"},
            )
        assert resp.status_code == 200
        # both S&P 500 spellings collapse; caret marker dropped in legacy form
        assert svc.get_batch_indexes.await_args.kwargs["symbols"] == ["GSPC", "IXIC"]

    async def test_empty_symbols_rejected_by_schema(self, client):
        with _stub_intraday() as (svc, _):
            resp = await client.post(
                "/api/v1/market-data/intraday/stocks", json={"symbols": []},
            )
        assert resp.status_code == 422
        svc.get_batch_stocks.assert_not_awaited()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_cache_hit_short_circuits_provider_and_filters_exchange(self, client):
        cached = {"results": [
            {"symbol": "AAPL", "name": "Apple Inc.", "exchangeShortName": "NASDAQ"},
            {"symbol": "T", "name": "AT&T Inc.", "exchangeShortName": "NYSE"},
        ]}
        cache = _cache(cached)
        financial = MagicMock()
        financial.search_stocks = AsyncMock()
        with _stub_cache_client(cache), _stub_financial_provider(_provider_with(financial)):
            resp = await client.get("/api/v1/market-data/search/stocks?query=apple&exchange=nyse")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1 and body["results"][0]["symbol"] == "T"
        cache.set.assert_not_awaited()          # hit path never re-writes
        financial.search_stocks.assert_not_awaited()

    async def test_miss_fetches_caches_then_returns(self, client):
        cache = _cache(cached=None)
        raw = [{"symbol": "AAPL", "name": "Apple Inc.", "currency": "USD",
                "stockExchange": "NASDAQ Global Select", "exchangeShortName": "NASDAQ"}]
        with _stub_cache_client(cache), _stub_financial_provider(_provider_with(_financial(search=raw))):
            resp = await client.get("/api/v1/market-data/search/stocks?query=Apple&limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "Apple" and body["count"] == 1
        assert body["results"][0]["exchangeShortName"] == "NASDAQ"
        cache.set.assert_awaited_once()
        assert cache.set.await_args.kwargs["ttl"] == 300
        # cache key is derived from the stripped, lowercased query + limit
        assert cache.set.await_args.args[0] == "search:apple:10"

    async def test_no_provider_is_503(self, client):
        with _stub_cache_client(_cache(None)), _stub_financial_provider(MagicMock(financial=None)):
            resp = await client.get("/api/v1/market-data/search/stocks?query=AAPL")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "No financial data provider available"

    async def test_provider_failure_is_generic_500(self, client):
        financial = MagicMock()
        financial.search_stocks = AsyncMock(side_effect=RuntimeError("hunter2 leak"))
        with _stub_cache_client(_cache(None)), _stub_financial_provider(MagicMock(financial=financial)):
            resp = await client.get("/api/v1/market-data/search/stocks?query=AAPL")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to search stocks"
        assert "hunter2" not in resp.json()["detail"]

    async def test_whitespace_query_is_422(self, client):
        with _stub_cache_client(_cache(None)):
            resp = await client.get("/api/v1/market-data/search/stocks?query=%20%20")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Company overview
# ---------------------------------------------------------------------------


class TestCompanyOverview:
    async def test_cache_hit_skips_fetch(self, client):
        cached = {"symbol": "AAPL", "name": "Apple Inc.", "quote": {"price": 250.0}}
        cache = _cache(cached)
        with _stub_cache_client(cache):
            with patch("src.tools.market_data.company.fetch_company_overview_data",
                       new=AsyncMock()) as fetch:
                resp = await client.get("/api/v1/market-data/stocks/aapl/overview")
        assert resp.status_code == 200
        assert resp.json()["quote"]["price"] == 250.0
        fetch.assert_not_awaited()
        # cache key uses the uppercased symbol
        assert cache.get.await_args.args[0] == "overview:AAPL"

    async def test_miss_fetches_maps_and_caches(self, client):
        artifact = {"symbol": "AAPL", "name": "Apple Inc.", "quote": {"price": 250.0},
                    "revenueByProduct": {"iPhone": 1.0}}
        cache = _cache(None)
        with _stub_cache_client(cache):
            with patch("src.tools.market_data.company.fetch_company_overview_data",
                       new=AsyncMock(return_value=artifact)) as fetch:
                resp = await client.get("/api/v1/market-data/stocks/AAPL/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "AAPL" and body["revenueByProduct"] == {"iPhone": 1.0}
        fetch.assert_awaited_once_with("AAPL")
        assert cache.set.await_args.kwargs["ttl"] == 300

    async def test_fetch_failure_is_generic_500(self, client):
        with _stub_cache_client(_cache(None)):
            with patch("src.tools.market_data.company.fetch_company_overview_data",
                       new=AsyncMock(side_effect=RuntimeError("secret-token abc123"))):
                resp = await client.get("/api/v1/market-data/stocks/AAPL/overview")
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Failed to fetch company overview"
        assert "abc123" not in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Analyst data
# ---------------------------------------------------------------------------


class TestAnalystData:
    async def test_cache_hit(self, client):
        cached = {"symbol": "AAPL", "priceTargets": {"targetConsensus": 240.0}, "grades": []}
        cache = _cache(cached)
        financial = MagicMock()
        financial.get_analyst_price_targets = AsyncMock()
        with _stub_cache_client(cache), _stub_financial_provider(_provider_with(financial)):
            resp = await client.get("/api/v1/market-data/stocks/AAPL/analyst-data")
        assert resp.status_code == 200
        assert resp.json()["priceTargets"]["targetConsensus"] == 240.0
        financial.get_analyst_price_targets.assert_not_awaited()

    async def test_miss_assembles_targets_and_grades(self, client):
        cache = _cache(None)
        financial = _financial(price_targets=[
            {"targetHigh": 250.0, "targetLow": 180.0, "targetConsensus": 220.0,
             "targetMedian": 225.0}])
        fmp = MagicMock()
        fmp.get_stock_grades = AsyncMock(return_value=[
            {"date": "2026-06-01", "gradingCompany": "Morgan Stanley",
             "previousGrade": "Equal-Weight", "newGrade": "Overweight", "action": "upgrade"}])
        fmp.close = AsyncMock()
        with (_stub_cache_client(cache), _stub_financial_provider(_provider_with(financial)),
              patch("src.data_client.fmp.fmp_client.FMPClient", return_value=fmp)):
            resp = await client.get("/api/v1/market-data/stocks/AAPL/analyst-data?grade_limit=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["priceTargets"]["targetConsensus"] == 220.0
        assert body["grades"][0]["company"] == "Morgan Stanley"
        assert body["grades"][0]["newGrade"] == "Overweight"
        fmp.close.assert_awaited_once()
        assert cache.set.await_args.kwargs["ttl"] == 900

    async def test_price_target_failure_degrades_to_none(self, client):
        cache = _cache(None)
        financial = MagicMock()
        financial.get_analyst_price_targets = AsyncMock(side_effect=RuntimeError("boom"))
        fmp = MagicMock()
        fmp.get_stock_grades = AsyncMock(return_value=[])
        fmp.close = AsyncMock()
        with (_stub_cache_client(cache), _stub_financial_provider(_provider_with(financial)),
              patch("src.data_client.fmp.fmp_client.FMPClient", return_value=fmp)):
            resp = await client.get("/api/v1/market-data/stocks/AAPL/analyst-data")
        assert resp.status_code == 200
        assert resp.json()["priceTargets"] is None

    async def test_no_provider_is_503(self, client):
        with _stub_cache_client(_cache(None)), _stub_financial_provider(MagicMock(financial=None)):
            resp = await client.get("/api/v1/market-data/stocks/AAPL/analyst-data")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


class TestSnapshots:
    async def test_batch_happy_path(self, client):
        raw = [{"symbol": "AAPL", "price": 250.0, "change_percent": 1.2},
               {"symbol": "MSFT", "price": 500.0}]
        with _stub_quotes(raw) as svc:
            resp = await client.get("/api/v1/market-data/snapshots/stocks?symbols=AAPL,MSFT")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2 and body["snapshots"][0]["symbol"] == "AAPL"
        assert svc.get_quotes.await_args.args[0] == ["AAPL", "MSFT"]
        assert svc.get_quotes.await_args.kwargs["asset_type"] == "stocks"

    async def test_batch_dedupes_and_uppercases(self, client):
        with _stub_quotes([]) as svc:
            await client.get("/api/v1/market-data/snapshots/stocks?symbols=aapl,AAPL,msft")
        assert svc.get_quotes.await_args.args[0] == ["AAPL", "MSFT"]

    async def test_blank_symbols_is_422(self, client):
        with _stub_quotes([]) as svc:
            resp = await client.get("/api/v1/market-data/snapshots/stocks?symbols=%20,%20")
        assert resp.status_code == 422
        assert "At least one symbol" in resp.json()["detail"]
        svc.get_quotes.assert_not_awaited()

    async def test_over_cap_is_422(self, client):
        symbols = ",".join(f"ZZQ{i}" for i in range(251))
        with _stub_quotes([]) as svc:
            resp = await client.get(f"/api/v1/market-data/snapshots/stocks?symbols={symbols}")
        assert resp.status_code == 422
        assert "max 250" in resp.json()["detail"]
        svc.get_quotes.assert_not_awaited()

    async def test_index_route_uses_indices_asset_type(self, client):
        with _stub_quotes([{"symbol": "GSPC", "price": 6000.0}]) as svc:
            resp = await client.get("/api/v1/market-data/snapshots/indexes?symbols=%5EGSPC")
        assert resp.status_code == 200
        kwargs = svc.get_quotes.await_args.kwargs
        assert kwargs["asset_type"] == "indices"
        assert svc.get_quotes.await_args.args[0] == ["GSPC"]

    async def test_single_snapshot_empty_is_404(self, client):
        with _stub_quotes([]):
            resp = await client.get("/api/v1/market-data/snapshots/stocks/AAPL")
        assert resp.status_code == 404
        assert "No snapshot data" in resp.json()["detail"]

    async def test_single_snapshot_rate_limit_is_503(self, client):
        with _stub_quotes([]) as svc:
            svc.get_quotes = AsyncMock(side_effect=MarketDataRateLimited("HTTP 429"))
            resp = await client.get("/api/v1/market-data/snapshots/stocks/AAPL")
        assert resp.status_code == 503
        assert resp.headers["retry-after"] == "60"


# ---------------------------------------------------------------------------
# Market status (+ alias)
# ---------------------------------------------------------------------------


class TestMarketStatus:
    async def test_cache_hit(self, client):
        cached = {"market": "open", "afterHours": False, "earlyHours": False,
                  "serverTime": "2026-06-30T15:00:00Z", "exchanges": {}, "providers": ["fmp"]}
        with _stub_cache_client(_cache(cached)):
            resp = await client.get("/api/v1/market-data/market-status")
        assert resp.status_code == 200
        assert resp.json()["market"] == "open"

    async def test_miss_fetches_caches_with_short_ttl(self, client):
        cache = _cache(None)
        provider = MagicMock()
        provider.get_market_status = AsyncMock(return_value={
            "market": "closed", "afterHours": True, "earlyHours": False,
            "serverTime": "2026-06-30T20:00:00Z", "exchanges": {"nasdaq": "closed"}})
        provider.source_names = ["fmp", "yfinance"]
        with _stub_cache_client(cache), _stub_market_provider(provider):
            resp = await client.get("/api/v1/market-data/market-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["market"] == "closed" and body["providers"] == ["fmp", "yfinance"]
        cache.set.assert_awaited_once()
        assert cache.set.await_args.args[0] == "market:status"
        assert cache.set.await_args.kwargs["ttl"] == 30  # _MARKET_STATUS_CACHE_TTL
        provider.get_market_status.assert_awaited_once_with(user_id="test-user-123")

    async def test_provider_failure_is_sanitized_500(self, client):
        provider = MagicMock()
        provider.get_market_status = AsyncMock(
            side_effect=RuntimeError("conn to postgres://u:hunter2@db:5432/fin failed"))
        with _stub_cache_client(_cache(None)), _stub_market_provider(provider):
            resp = await client.get("/api/v1/market-data/market-status")
        assert resp.status_code == 500
        assert "hunter2" not in resp.json()["detail"]

    async def test_alias_route_matches_market_status(self, client):
        cached = {"market": "open", "providers": ["fmp"]}
        with _stub_cache_client(_cache(cached)):
            alias = await client.get("/api/v1/market-data/status")
            main = await client.get("/api/v1/market-data/market-status")
        assert alias.status_code == main.status_code == 200
        assert alias.json() == main.json()
