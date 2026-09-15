"""The earnings-call matcher: pairing a filing with its call.

The whole point of this module is *not pairing the wrong quarter*. A 10-Q
filed in late January belongs to the call that happened ~3 weeks earlier; if
the 30-day window or the closest-date selection is wrong, the transcript
appended to the filing describes a different fiscal period and every number
read out of it contradicts the filing next to it. These tests pin the window,
the selection, and the junk-data guards.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from src.tools.sec import earnings_call as ec

FILING_DATE = dt.date(2026, 1, 28)


def _entry(quarter: int, year: int, call_date: str) -> tuple:
    return (quarter, year, call_date)


class _FakeClient:
    """Stands in for FMPClient: canned dates and transcripts."""

    def __init__(self, dates=None, transcripts=None, error: Exception | None = None):
        self._dates = dates or []
        self._transcripts = transcripts or {}
        self._error = error

    async def __aenter__(self):
        if self._error:
            raise self._error
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_earnings_call_dates(self, symbol):
        return self._dates

    async def get_earnings_call_transcript(self, symbol, year, quarter):
        return self._transcripts.get((year, quarter), [])


def _fetch(client: _FakeClient):
    return patch.object(ec, "FMPClient", lambda: client)


# ---------------------------------------------------------------------------
# format_earnings_call_section — pure formatting
# ---------------------------------------------------------------------------


def test_the_section_states_the_distance_between_call_and_filing():
    out = ec.format_earnings_call_section(
        "transcript body", 2026, 2,
        call_date=dt.date(2026, 1, 14),
        filing_date=dt.date(2026, 1, 28),
    )
    assert "Q2 FY2026" in out
    assert "14 days from filing" in out
    assert "transcript body" in out


def test_a_call_before_the_filing_reports_a_positive_distance():
    """The distance is absolute: an early call is 'days from filing', not a
    negative number the model might read as 'in the future'."""
    out = ec.format_earnings_call_section(
        "t", 2026, 3,
        call_date=FILING_DATE - dt.timedelta(days=21),
        filing_date=FILING_DATE,
    )
    assert "21 days from filing" in out


# ---------------------------------------------------------------------------
# fetch_matching_earnings_call — the selection logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_closest_call_within_the_window_wins():
    client = _FakeClient(
        dates=[
            _entry(2, 2025, "2025-12-10"),   # 49 days before — outside the window
            _entry(1, 2026, "2026-01-20"),   # 8 days before — closest
            _entry(1, 2025, "2025-04-15"),   # far away
        ],
        transcripts={(2026, 1): [{"content": "the right call"}]},
    )
    with _fetch(client):
        got = await ec.fetch_matching_earnings_call("AAPL", FILING_DATE)

    assert got == ("the right call", 2026, 1, dt.date(2026, 1, 20))


@pytest.mark.asyncio
async def test_a_call_more_than_30_days_out_is_ignored_entirely():
    """An out-of-window call must not be 'the closest' — the window is the
    definition of same-period, and the boundary itself is inside it."""
    client = _FakeClient(
        dates=[_entry(2, 2025, "2025-12-20")],  # 39 days before
        transcripts={(2025, 2): [{"content": "wrong period"}]},
    )
    with _fetch(client):
        assert await ec.fetch_matching_earnings_call("AAPL", FILING_DATE) is None


@pytest.mark.asyncio
async def test_the_day_30_boundary_is_inside_the_window():
    client = _FakeClient(
        dates=[_entry(2, 2025, "2025-12-29")],  # exactly 30 days before
        transcripts={(2025, 2): [{"content": "boundary call"}]},
    )
    with _fetch(client):
        got = await ec.fetch_matching_earnings_call("AAPL", FILING_DATE)

    assert got is not None
    assert got[0] == "boundary call"


@pytest.mark.asyncio
async def test_malformed_entries_are_skipped_not_fatal():
    """Providers emit junk rows; one bad row must not discard the good ones."""
    client = _FakeClient(
        dates=[
            ("only-one-field",),                 # too short
            _entry(1, 2026, "not-a-date"),       # unparsable date
            _entry(1, 2026, "2026-01-20"),       # the real one
        ],
        transcripts={(2026, 1): [{"content": "ok"}]},
    )
    with _fetch(client):
        got = await ec.fetch_matching_earnings_call("AAPL", FILING_DATE)

    assert got is not None
    assert got[0] == "ok"


@pytest.mark.asyncio
async def test_no_transcript_body_means_no_match():
    """A date hit with an empty transcript list is not a match."""
    client = _FakeClient(
        dates=[_entry(1, 2026, "2026-01-20")],
        transcripts={},  # nothing fetched
    )
    with _fetch(client):
        assert await ec.fetch_matching_earnings_call("AAPL", FILING_DATE) is None


@pytest.mark.asyncio
async def test_a_placeholder_transcript_is_rejected():
    """FMP returns the string 'No data available' instead of a 404; handing
    that to the model would put a fake transcript into a filing report."""
    client = _FakeClient(
        dates=[_entry(1, 2026, "2026-01-20")],
        transcripts={(2026, 1): [{"content": "No data available"}]},
    )
    with _fetch(client):
        assert await ec.fetch_matching_earnings_call("AAPL", FILING_DATE) is None


@pytest.mark.asyncio
async def test_an_empty_date_list_is_no_match():
    with _fetch(_FakeClient(dates=[])):
        assert await ec.fetch_matching_earnings_call("AAPL", FILING_DATE) is None


@pytest.mark.asyncio
async def test_a_client_failure_is_swallowed_as_no_match():
    """The transcript is a nice-to-have appendix on a filing report; an FMP
    outage must degrade to 'no transcript', never to a failed filing fetch."""
    with _fetch(_FakeClient(error=RuntimeError("fmp down"))):
        assert await ec.fetch_matching_earnings_call("AAPL", FILING_DATE) is None
