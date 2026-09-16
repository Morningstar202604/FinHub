#!/usr/bin/env python3
"""Seed demo OHLCV envelopes into Redis so the Market view renders charts
offline (upstream providers are unreachable in this sandbox).

Writes v5 envelopes matching src/server/services/cache/_ohlcv_envelope.py:
    ohlcv:{SYM}.XNAS:{schema}  for schemas ohlcv-1m / ohlcv-5m / ohlcv-1d
Random-walk bars anchored to the real ET trading calendar so watermark /
data_date freshness checks pass and SWR doesn't immediately refetch.
"""
import json
import math
import os
import random
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import redis

ET = ZoneInfo("America/New_York")
R = redis.Redis(host="127.0.0.1", port=6379, password="redis", db=0, decode_responses=True)

# Anchor to the BACKEND container clock: the staleness stack (watermark /
# data_date / soft-TTL elapsed) runs on container time, and this sandbox's
# host clock drifts from it (observed ~14h). Seeding from host time makes
# every envelope look stale-on-arrival and the cache discards it.
try:
    import subprocess
    EPOCH = float(subprocess.run(
        ["docker", "exec", "finhub-backend-1", "date", "+%s.%N"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip())
except Exception:
    EPOCH = time.time()

def _now() -> datetime:
    return datetime.fromtimestamp(EPOCH, tz=timezone.utc)

def _ts() -> float:
    return EPOCH

now = _now()
now_et = now.astimezone(ET)

# data_date must equal the backend clock's current_trading_date(), which
# during pre-market (before 9:30 ET) is the PREVIOUS trading day — today's
# bars don't exist yet. _is_stale_date compares with !=, so stamping "today"
# during pre-market guarantees an instant discard.
def _prev_trading_day(dt: datetime) -> datetime:
    d = dt - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

if now_et.hour * 60 + now_et.minute < 9 * 60 + 30 or now_et.weekday() >= 5:
    trading_day = _prev_trading_day(now_et)
else:
    trading_day = now_et
today = trading_day.strftime("%Y-%m-%d")

# Phase of the US market right now (approx by ET clock, good enough for the envelope).
hm = now_et.hour * 60 + now_et.minute
if hm < 4 * 60:
    phase = "pre"
elif hm < 9 * 60 + 30:
    phase = "pre"
elif hm < 16 * 60:
    phase = "open"
elif hm < 20 * 60:
    phase = "post"
else:
    phase = "closed"

ENVELOPE_VERSION = 5

SYMBOLS = {
    "GOOGL": 175.0,
    "AAPL": 228.0,
    "MSFT": 430.0,
    "NVDA": 132.0,
    "TSLA": 248.0,
}

def trading_day_offset(d: datetime) -> bool:
    return d.weekday() < 5  # Mon-Fri (ignores holidays; fine for a demo)

def build_bars(base: float, n: int, step_seconds: int, day_mode: bool, seed: int):
    rng = random.Random(seed)
    bars = []
    price = base * (0.82 + 0.06 * rng.random())
    # Walk backwards from the most recent bar slot to build n bars.
    slots = []
    t = now
    while len(slots) < n:
        if day_mode:
            # step back one trading day at a time (skip weekends)
            t = t - timedelta(days=1)
            if not trading_day_offset(t):
                continue
            slots.append(t.replace(hour=13, minute=30, second=0, microsecond=0))
        else:
            t = t - timedelta(seconds=step_seconds)
            # only bars inside regular hours (13:30–20:00 UTC ≈ 9:30–16:00 ET)
            et = t.astimezone(ET)
            mins = et.hour * 60 + et.minute
            if et.weekday() >= 5 or mins < 570 or mins > 960:
                continue
            slots.append(t)
    slots.reverse()
    for ts in slots:
        drift = (rng.random() - 0.48) * 0.012
        openp = price
        close = max(1.0, openp * (1 + drift))
        hi = max(openp, close) * (1 + rng.random() * 0.004)
        lo = min(openp, close) * (1 - rng.random() * 0.004)
        vol = int((0.6 + rng.random()) * 4_000_000)
        ms = int(ts.timestamp() * 1000)
        bars.append({
            "time": ms, "ts_event": ms,
            "open": round(openp, 2), "high": round(hi, 2),
            "low": round(lo, 2), "close": round(close, 2), "volume": vol,
        })
        price = close
    return bars

def envelope(sym: str, schema: str, bars: list) -> dict:
    watermark = bars[-1]["time"] if bars else 0
    # stored_ttl must match the Redis ex, else the first cache HIT sees
    # elapsed >> stored_ttl, triggers an SWR delta refresh, and the refresh
    # rewrites the key with the real (short, phase-aware) product TTL —
    # the seeded envelope then expires within minutes.
    ttl = envelope_ttl(schema)
    return {
        "v": ENVELOPE_VERSION,
        "header": {
            "instrument_key": f"{sym}.XNAS",
            "schema": schema,
            "publisher": "demo-seed",
            "price_treatment": "regular",
            "tier": "delayed_15m",
            "feed_scope": "composite",
            "ts_unit": "ms",
            "latest_trading_date": today,
            "revision": 0,
            "asof": _ts(),
            "coverage": {"truncated": False},
            "fetched_at": _ts(),
            "watermark": watermark,
        },
        "records": bars,
        "market_phase": phase,
        "complete": False,
        "stored_ttl": ttl,
    }

def envelope_ttl(schema: str) -> int:
    # Match phase-aware cache TTLs: intraday short, daily long.
    if schema == "ohlcv-1d":
        return 86400
    return 3600 if phase == "open" else 14400

count = 0
for sym, base in SYMBOLS.items():
    for schema, n, step, day_mode in (
        ("ohlcv-1m", 390, 60, False),
        ("ohlcv-5m", 156, 300, False),
        ("ohlcv-1d", 260, 86400, True),
    ):
        bars = build_bars(base, n, step, day_mode, seed=hash((sym, schema)) & 0xFFFF)
        key = f"ohlcv:{sym}.XNAS:{schema}"
        R.set(key, json.dumps(envelope(sym, schema, bars)), ex=envelope_ttl(schema))
        count += 1
        print(f"seeded {key}  bars={len(bars)} last_close={bars[-1]['close']}")

    # Quote row (quote:v2:{instrument_key}) — shape mirrors SnapshotData.
    daily = json.loads(R.get(f"ohlcv:{sym}.XNAS:ohlcv-1d"))
    last = daily["records"][-1]
    prev = daily["records"][-2]
    price = last["close"]
    change = round(price - prev["close"], 2)
    quote = {
        "symbol": sym,
        "name": {"GOOGL": "Alphabet Inc.", "AAPL": "Apple Inc.", "MSFT": "Microsoft Corp.",
                 "NVDA": "NVIDIA Corp.", "TSLA": "Tesla Inc."}[sym],
        "price": price,
        "change": change,
        "change_percent": round(change / prev["close"] * 100, 2),
        "previous_close": prev["close"],
        "open": last["open"],
        "high": last["high"],
        "low": last["low"],
        "volume": last["volume"],
        "market_status": phase,
        "last_minute_close": price,
        "regular_close": price,
        "regular_trading_change": change,
        "source": "demo-seed",
    }
    R.set(f"quote:v2:{sym}.XNAS", json.dumps(quote), ex=86400)
    count += 1
    print(f"seeded quote:v2:{sym}.XNAS  price={price}")

# Major indices — instrument_key is {family}.INDEX (symbology._INDEX_FAMILIES).
# Row `symbol` must be the LEGACY spelling the client requests (GSPC, not SPX):
# quoteBatcher fans rows out by row.symbol → quoteKey(symbol), so a canonical
# family spelling in the row silently misses the card.
INDICES = {
    ("SPX",  "GSPC", "S&P 500"):                 6652.30,
    ("COMP", "IXIC", "Nasdaq Composite"):       22348.75,
    ("DJI",  "DJI",  "Dow Jones"):              46215.40,
    ("RUT",  "RUT",  "Russell 2000"):            2418.60,
    ("VIX",  "VIX",  "CBOE Volatility Index"):    16.42,
}
for (fam, legacy, name), px in INDICES.items():
    prev = round(px * (1 + 0.021 if fam == "VIX" else 1 - 0.004), 2)
    chg = round(px - prev, 2)
    row = {
        "symbol": legacy, "name": name, "price": px,
        "change": chg, "change_percent": round(chg / prev * 100, 2),
        "previous_close": prev, "open": prev, "high": round(px * 1.003, 2),
        "low": round(px * 0.997, 2), "volume": None, "market_status": phase,
        "last_minute_close": px, "regular_close": px,
        "regular_trading_change": chg, "source": "demo-seed",
    }
    R.set(f"quote:v2:{fam}.INDEX", json.dumps(row), ex=86400)
    count += 1
    print(f"seeded quote:v2:{fam}.INDEX  symbol={legacy} price={px}")

    # Index OHLCV so dashboard sparklines / index charts render offline.
    for schema, n, step, day_mode, ex in (
        ("ohlcv-1m", 390, 60, False, 3600),
        ("ohlcv-1d", 260, 86400, True, 86400),
    ):
        bars = build_bars(px, n, step, day_mode, seed=hash((fam, schema)) & 0xFFFF)
        env = envelope(f"{fam}.INDEX", schema, bars)
        env["header"]["instrument_key"] = f"{fam}.INDEX"
        key = f"ohlcv:{fam}.INDEX:{schema}"
        R.set(key, json.dumps(env), ex=ex)
        count += 1
        print(f"seeded {key}  bars={len(bars)}")

# SPY — the demo portfolio holds it (XNYS venue, not XNAS). Without a quote
# row the holdings table shows N/A for the whole SPY line.
SPY_PX = 661.85
_spy_prev = round(SPY_PX * 0.996, 2)
_spy_chg = round(SPY_PX - _spy_prev, 2)
R.set("quote:v2:SPY.XNYS", json.dumps({
    "symbol": "SPY", "name": "SPDR S&P 500 ETF", "price": SPY_PX,
    "change": _spy_chg, "change_percent": round(_spy_chg / _spy_prev * 100, 2),
    "previous_close": _spy_prev, "open": _spy_prev,
    "high": round(SPY_PX * 1.002, 2), "low": round(SPY_PX * 0.996, 2),
    "volume": 41234567, "market_status": phase,
    "last_minute_close": SPY_PX, "regular_close": SPY_PX,
    "regular_trading_change": _spy_chg, "source": "demo-seed",
}), ex=86400)
count += 1
for schema, n, step, day_mode in (("ohlcv-1m", 390, 60, False), ("ohlcv-1d", 260, 86400, True)):
    bars = build_bars(SPY_PX, n, step, day_mode, seed=hash(("SPY", schema)) & 0xFFFF)
    env = envelope("SPY.XNYS", schema, bars)
    env["header"]["instrument_key"] = "SPY.XNYS"
    R.set(f"ohlcv:SPY.XNYS:{schema}", json.dumps(env), ex=envelope_ttl(schema))
    count += 1
print(f"seeded quote:v2:SPY.XNYS + ohlcv  price={SPY_PX}")

print(f"phase={phase} today(ET)={today} total_keys={count}")
