"""get_sec_filing_async: the tool the model actually calls.

It validates the filing type, delegates 8-K to the listing path, and for
10-K/10-Q runs the filing fetch first (it needs the filing date) then fans
out — earnings call and recent-8-K reminder in parallel — before assembling
one markdown report. The tests pin the assembly contract: what lands in the
artifact, what happens when a side fetch fails, and what the caller gets for
each filing type.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, patch

import pytest

from src.tools.sec import tool as sec_tool
from src.tools.sec.types import DEFAULT_10K_SECTIONS, DEFAULT_10Q_SECTIONS

DATE_STR = "2026-01-28"
DATE = dt.date(2026, 1, 28)


def _ok_fetch(content="filing body", metadata=None, filing_date=DATE_STR):
    metadata = metadata or {
        "symbol": "AAPL", "filing_type": "10-K", "filing_date": filing_date,
    }
    # The real _fetch_sec_filing derives the date string from the metadata.
    return AsyncMock(return_value=(content, metadata.get("filing_date", filing_date), metadata))


def _patch_all(fetch=None, earnings=None, recent=None):
    """Patch the three async collaborators at once; each test opts in."""
    return (
        patch.object(sec_tool, "_fetch_sec_filing", fetch or _ok_fetch()),
        patch.object(
            sec_tool, "fetch_matching_earnings_call",
            earnings if isinstance(earnings, AsyncMock) else AsyncMock(return_value=earnings),
        ),
        patch.object(
            sec_tool, "find_recent_8k_filings",
            recent if isinstance(recent, AsyncMock) else AsyncMock(return_value=recent),
        ),
    )


# ---------------------------------------------------------------------------
# Validation and routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_filing_type_is_rejected_with_the_valid_choices():
    out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="S-1")
    assert "Invalid filing type" in out
    assert "10-K" in out and "10-Q" in out and "8-K" in out
    assert artifact == {}


@pytest.mark.asyncio
async def test_the_8k_branch_lists_recent_filings():
    filings = [{
        "filing_date": DATE,
        "items": ["Item 2.02"],
        "items_with_desc": [{"item": "Item 2.02", "description": "Results of Operations"}],
        "source_url": "https://sec.gov/8k.htm",
        "cik": "0000320193",
        "has_press_release": True,
        "press_release": None,
    }]
    fetch = AsyncMock(return_value=filings)
    p = patch.object(sec_tool, "fetch_8k_filings", fetch)
    with p:
        out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="8-K")

    assert "# AAPL 8-K Filings" in out
    assert artifact["filing_type"] == "8-K"
    assert artifact["filing_count"] == 1
    assert artifact["filings"][0]["items_desc"] == ["Results of Operations"]
    assert artifact["filings"][0]["has_press_release"] is True


@pytest.mark.asyncio
async def test_10k_defaults_to_the_essential_sections():
    fetch = _ok_fetch()
    p1, _p2, _p3 = _patch_all(fetch=fetch)
    with p1, _p2, _p3:
        await sec_tool.get_sec_filing_async("AAPL", filing_type="10-K")

    kwargs = fetch.await_args.kwargs
    assert kwargs["sections"] == DEFAULT_10K_SECTIONS


@pytest.mark.asyncio
async def test_10q_defaults_to_mda_and_risk_factors():
    fetch = _ok_fetch(metadata={"symbol": "AAPL", "filing_type": "10-Q", "filing_date": DATE_STR})
    p1, _p2, _p3 = _patch_all(fetch=fetch)
    with p1, _p2, _p3:
        await sec_tool.get_sec_filing_async("AAPL", filing_type="10-Q")

    assert fetch.await_args.kwargs["sections"] == DEFAULT_10Q_SECTIONS


@pytest.mark.asyncio
async def test_explicit_sections_beat_the_defaults():
    fetch = _ok_fetch()
    p1, _p2, _p3 = _patch_all(fetch=fetch)
    with p1, _p2, _p3:
        await sec_tool.get_sec_filing_async(
            "AAPL", filing_type="10-K", sections=["item_1"], use_defaults=False
        )

    assert fetch.await_args.kwargs["sections"] == ["item_1"]


# ---------------------------------------------------------------------------
# Failure of the primary fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_filing_fetch_is_reported_as_a_string():
    fetch = AsyncMock(return_value=({"error": "No 10-K found", "symbol": "AAPL"}, None, {}))
    p1, _p2, _p3 = _patch_all(fetch=fetch)
    with p1, _p2, _p3:
        out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="10-K")

    assert "No 10-K found" in out
    assert artifact == {}
    # No date means the side fetches never had an anchor — they must not run.
    _p2.new.assert_not_awaited()
    _p3.new.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unparsable_filing_date_skips_the_side_fetches():
    fetch = _ok_fetch(metadata={"filing_date": "not-a-date"})
    p1, p2, p3 = _patch_all(fetch=fetch)
    with p1, p2, p3:
        out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="10-K")

    assert out == "filing body"
    p2.new.assert_not_awaited()
    p3.new.assert_not_awaited()


# ---------------------------------------------------------------------------
# The parallel fan-out and its assembly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_earnings_call_is_appended_and_flagged():
    call_date = DATE - dt.timedelta(days=14)
    p1, p2, p3 = _patch_all(
        earnings=("transcript text", 2026, 2, call_date),
        recent=[],
    )
    with p1, p2, p3:
        out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="10-K")

    assert "Q2 FY2026" in out
    assert "transcript text" in out
    assert "filing body" in out
    assert artifact["has_earnings_call"] is True


@pytest.mark.asyncio
async def test_the_recent_8k_reminder_is_appended_and_counted():
    recent = [{
        "filing_date": DATE, "items": ["Item 7.01"],
        "source_url": "https://sec.gov/g.htm", "has_press_release": False,
    }]
    p1, p2, p3 = _patch_all(earnings=None, recent=recent)
    with p1, p2, p3:
        out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="10-K")

    assert "Recent 8-K Filings" in out
    assert artifact["recent_8k_count"] == 1
    assert "has_earnings_call" not in artifact


@pytest.mark.asyncio
async def test_opting_out_of_the_earnings_call_skips_its_task():
    p1, p2, p3 = _patch_all(earnings=None, recent=[])
    with p1, p2, p3:
        await sec_tool.get_sec_filing_async(
            "AAPL", filing_type="10-K", include_earnings_call=False
        )

    p2.new.assert_not_awaited()
    p3.new.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_failing_side_task_does_not_kill_the_filing():
    """The filing is the product; the transcript and reminder are appendices.
    One of them raising must cost only the appendix."""
    p1, p2, p3 = _patch_all(
        earnings=AsyncMock(side_effect=RuntimeError("fmp down")),
        recent=[],
    )
    with p1, p2, p3:
        out, artifact = await sec_tool.get_sec_filing_async("AAPL", filing_type="10-K")

    assert out == "filing body"
    assert "has_earnings_call" not in artifact
