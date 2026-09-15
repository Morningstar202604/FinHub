"""8-K utilities: press-release extraction, formatting, and EDGAR fetching.

The 8-K list is how the model learns *what happened* between two periodic
filings — an Item 2.02 row is "results are out", an Item 7.01 row is
"guidance was given". The tests pin the mapping into human-readable items,
the press-release extraction (which has two API shapes to bridge), and the
fetch loop's tolerance: one corrupt filing must not cost the others.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.tools.sec import eight_k as ek

TODAY = dt.date(2026, 3, 1)


class _Filings:
    """The slice of edgartools' FilingSet the code touches."""

    def __init__(self, items):
        self._items = list(items)

    def __len__(self):
        return len(self._items)

    def get_filing_at(self, i):
        return self._items[i]


def _filing(filing_date, items=("Item 2.02",), has_pr=False, pr=None):
    obj = SimpleNamespace(items=list(items), has_press_release=has_pr)
    if pr is not None:
        obj.press_releases = [pr]
    else:
        obj.press_releases = []
    return SimpleNamespace(
        filing_date=filing_date,
        obj=lambda: obj,
        filing_url=f"https://sec.gov/archives/{filing_date.isoformat()}-x.htm",
        cik="0000320193",
    )


def _edgar(filings):
    """Patch edgar so Company(symbol).get_filings(form='8-K') returns *filings*."""
    company = MagicMock()
    company.get_filings.return_value = filings
    return (
        patch("edgar.set_identity"),
        patch("edgar.Company", return_value=company),
    )


# ---------------------------------------------------------------------------
# Press-release extraction — two API shapes, one answer
# ---------------------------------------------------------------------------


def test_no_press_release_attribute_means_none():
    obj = SimpleNamespace()  # not even the attribute
    assert ek._get_press_release_markdown(obj) is None


def test_an_explicit_false_means_none():
    obj = SimpleNamespace(has_press_release=False)
    assert ek._get_press_release_markdown(obj) is None


def test_a_true_flag_with_an_empty_list_means_none():
    obj = SimpleNamespace(has_press_release=True, press_releases=[])
    assert ek._get_press_release_markdown(obj) is None


def test_the_markdown_shape_prefers_markdown_md():
    pr = MagicMock(spec=["to_markdown"])
    md_obj = MagicMock(spec=["md"])
    md_obj.md = "# Results\n| Revenue | 1 |"
    pr.to_markdown.return_value = md_obj
    obj = SimpleNamespace(has_press_release=True, press_releases=[pr])

    assert ek._get_press_release_markdown(obj) == "# Results\n| Revenue | 1 |"


def test_the_markdown_shape_falls_back_to_str():
    pr = MagicMock(spec=["to_markdown"])
    pr.to_markdown.return_value = "plain markdown object"
    obj = SimpleNamespace(has_press_release=True, press_releases=[pr])

    assert ek._get_press_release_markdown(obj) == "plain markdown object"


def test_the_text_shape_calls_text_when_callable():
    pr = SimpleNamespace(text=lambda: "text body")
    obj = SimpleNamespace(has_press_release=True, press_releases=[pr])
    assert ek._get_press_release_markdown(obj) == "text body"


def test_the_text_shape_stringifies_when_it_is_an_attribute():
    pr = SimpleNamespace(text="attribute body")
    obj = SimpleNamespace(has_press_release=True, press_releases=[pr])
    assert ek._get_press_release_markdown(obj) == "attribute body"


def test_a_failing_extraction_degrades_to_none():
    pr = MagicMock(spec=["to_markdown"])
    pr.to_markdown.side_effect = RuntimeError("boom")
    obj = SimpleNamespace(has_press_release=True, press_releases=[pr])
    assert ek._get_press_release_markdown(obj) is None


# ---------------------------------------------------------------------------
# Fetch loop — tolerant per filing, silent on total failure
# ---------------------------------------------------------------------------


def test_filings_past_the_cutoff_stop_the_walk():
    """Filings arrive newest-first; once a date is beyond the window the rest
    are older, so the loop may stop rather than scan all 50."""
    filings = _Filings([
        _filing(TODAY - dt.timedelta(days=5)),
        _filing(TODAY - dt.timedelta(days=40)),
        _filing(TODAY - dt.timedelta(days=200)),   # beyond 90-day window
        _filing(TODAY - dt.timedelta(days=400)),   # never reached
    ])
    p1, p2 = _edgar(filings)
    with p1, p2:
        got = ek._fetch_8k_filings_blocking("AAPL", max_days=90, reference_date=TODAY)

    assert len(got) == 2
    assert [f["filing_date"] for f in got] == [
        TODAY - dt.timedelta(days=5),
        TODAY - dt.timedelta(days=40),
    ]


def test_one_corrupt_filing_does_not_cost_the_rest():
    good = _filing(TODAY - dt.timedelta(days=5))
    bad = MagicMock()
    bad.filing_date = TODAY - dt.timedelta(days=10)
    bad.obj.side_effect = RuntimeError("corrupt xbrl")
    filings = _Filings([good, bad, _filing(TODAY - dt.timedelta(days=15))])
    p1, p2 = _edgar(filings)
    with p1, p2:
        got = ek._fetch_8k_filings_blocking("AAPL", max_days=90, reference_date=TODAY)

    assert len(got) == 2


def test_items_are_mapped_to_descriptions():
    filings = _Filings([_filing(TODAY, items=("Item 2.02", "Item 9.01", "Item 99.99"))])
    p1, p2 = _edgar(filings)
    with p1, p2:
        got = ek._fetch_8k_filings_blocking("AAPL", max_days=90, reference_date=TODAY)

    by_item = {d["item"]: d["description"] for d in got[0]["items_with_desc"]}
    assert "Results of Operations" in by_item["Item 2.02"]
    assert "Financial Statements and Exhibits" in by_item["Item 9.01"]
    assert by_item["Item 99.99"] == ""  # unknown item: shown, described nowhere


def test_a_total_edgar_failure_is_an_empty_list_not_a_crash():
    p1, p2 = _edgar(_Filings([]))
    with p1, p2:
        assert ek._fetch_8k_filings_blocking("AAPL") == []


@pytest.mark.asyncio
async def test_the_async_wrapper_offloads_to_the_executor():
    """The blocking edgartools call must not run on the event loop."""
    filings = _Filings([_filing(TODAY)])
    p1, p2 = _edgar(filings)
    with p1, p2:
        got = await ek.fetch_8k_filings("AAPL", max_days=90, reference_date=TODAY)

    assert len(got) == 1


# ---------------------------------------------------------------------------
# Nearby-8-K window (legacy path used around a 10-K/10-Q date)
# ---------------------------------------------------------------------------


def test_nearby_keeps_both_sides_of_the_reference_date():
    anchor = dt.date(2026, 1, 28)
    filings = _Filings([
        _filing(anchor + dt.timedelta(days=10)),
        _filing(anchor - dt.timedelta(days=10)),
        _filing(anchor + dt.timedelta(days=31)),   # outside ±30
    ])
    p1, p2 = _edgar(filings)
    with p1, p2:
        got = ek._find_nearby_8k_filings_blocking("AAPL", anchor, max_days=30)

    assert [f["days_diff"] for f in got] == [-10, 10]


# ---------------------------------------------------------------------------
# Formatting — what the model actually reads
# ---------------------------------------------------------------------------


def test_no_filings_renders_an_empty_notice():
    out = ek.format_8k_filings("AAPL", [], max_days=90)
    assert "No 8-K filings found for AAPL" in out


def test_the_report_carries_dates_urls_and_item_descriptions():
    filings = [{
        "filing_date": TODAY,
        "items": ["Item 2.02"],
        "items_with_desc": [{"item": "Item 2.02", "description": "Results of Operations and Financial Condition"}],
        "source_url": "https://sec.gov/x.htm",
        "cik": "0000320193",
        "has_press_release": False,
        "press_release": None,
    }]
    out = ek.format_8k_filings("AAPL", filings)

    assert "# AAPL 8-K Filings" in out
    assert "https://sec.gov/x.htm" in out
    assert "**Item 2.02**: Results of Operations and Financial Condition" in out
    assert "*No press release attached to this filing.*" in out


def test_an_item_without_a_description_is_listed_bare():
    filings = [{
        "filing_date": TODAY,
        "items": ["Item 99.99"],
        "items_with_desc": [{"item": "Item 99.99", "description": ""}],
        "source_url": "u",
        "cik": "1",
        "has_press_release": False,
        "press_release": None,
    }]
    out = ek.format_8k_filings("AAPL", filings)
    assert "- **Item 99.99**\n" in out
    assert "**Item 99.99**: " not in out


def test_a_press_release_is_embedded_under_its_own_heading():
    filings = [{
        "filing_date": TODAY,
        "items": [],
        "items_with_desc": [],
        "source_url": "u",
        "cik": "1",
        "has_press_release": True,
        "press_release": "### PRESS BODY",
    }]
    out = ek.format_8k_filings("AAPL", filings)
    assert "### Press Release" in out
    assert "### PRESS BODY" in out


def test_an_empty_reminder_is_an_empty_string():
    """The reminder is appended to a 10-K/10-Q report; silence is correct
    when there is nothing recent, not a '0 filings' section."""
    assert ek.format_8k_reminder([], "10-K") == ""


def test_the_reminder_flags_press_releases_and_links():
    recent = [{
        "filing_date": TODAY,
        "items": ["Item 7.01"],
        "source_url": "https://sec.gov/g.htm",
        "has_press_release": True,
    }]
    out = ek.format_8k_reminder(recent, "10-K")

    assert "Recent 8-K Filings" in out
    assert "(has press release)" in out
    assert "**Item 7.01**: Regulation FD Disclosure" in out
    assert "https://sec.gov/g.htm" in out
