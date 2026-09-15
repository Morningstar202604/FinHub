"""EdgarToolsParser: the primary SEC extraction path.

Two API shapes live side by side here and the tests keep them straight:

- **10-K** exposes *properties* (``tenk.business``, ``tenk.risk_factors``);
- **10-Q** is *indexed* (``tenq["Part I, Item 2"]``) and raises KeyError for
  anything missing, with the raw filing text as fallback.

Also pinned: amendments are excluded from the latest-filing lookup (a 10-K/A
restates figures but the tooling wants the original's XBRL), and the markdown
renderer converts raw dollar figures to a ``$x.xxB`` summary table.
"""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.tools.sec.parsers.base import ParsingFailedError
from src.tools.sec.parsers.edgartools_parser import (
    SUBTOTAL_PATTERNS,
    TOTAL_PATTERNS,
    EdgarToolsParser,
)
from src.tools.sec.types import FilingType


def _parser() -> EdgarToolsParser:
    with patch("edgar.set_identity"):
        return EdgarToolsParser()


def _stmt(md: str):
    return SimpleNamespace(render=lambda: SimpleNamespace(to_markdown=lambda: md))


def _financials(metrics: dict | None = None):
    return SimpleNamespace(
        balance_sheet=lambda: _stmt("| Total assets | 1 |"),
        income_statement=lambda: _stmt("| Revenue | 2 |"),
        cashflow_statement=lambda: _stmt("| Operating | 3 |"),
        get_financial_metrics=lambda: (metrics or {}),
    )


def _filing(obj=None, filing_date=dt.date(2026, 1, 15), text: str | None = None):
    return SimpleNamespace(
        filing_date=filing_date,
        period_of_report="2025-12-31",
        cik="0000320193",
        filing_url="https://sec.gov/aapl-10k.htm",
        obj=lambda: obj,
        text=lambda: text,
        markdown=lambda: "# full md",
    )


class _Filings:
    def __init__(self, items, latest=None):
        self._items = list(items)
        self._latest = latest if latest is not None else (items[0] if items else None)

    def __len__(self):
        return len(self._items)

    def get_filing_at(self, i):
        return self._items[i]

    def latest(self):
        if self._latest is None:
            raise IndexError("no filings")
        return self._latest


# ---------------------------------------------------------------------------
# Surface behaviour
# ---------------------------------------------------------------------------


def test_it_supports_the_periodic_filings_only():
    p = _parser()
    assert p.name == "edgartools"
    assert p.supports_filing_type(FilingType.FORM_10K)
    assert p.supports_filing_type(FilingType.FORM_10Q)
    assert not p.supports_filing_type(FilingType.FORM_8K), (
        "8-K has its own module (eight_k.py); the parser must not claim it"
    )


def test_parse_is_deliberately_unsupported():
    p = _parser()
    with pytest.raises(NotImplementedError, match="parse_filing"):
        p.parse("<html/>", FilingType.FORM_10K)


def test_a_missing_edgartools_library_leaves_the_parser_uninitialized():
    with patch.dict("sys.modules", {"edgar": None}):
        p = EdgarToolsParser()
    assert p._initialized is False


# ---------------------------------------------------------------------------
# get_latest_filing — the amendment exclusion
# ---------------------------------------------------------------------------


def test_amendments_are_excluded_from_the_lookup():
    """A 10-K/A restates figures but carries no full XBRL; the original is
    what this tooling is built to parse."""
    company = MagicMock()
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        _parser().get_latest_filing("AAPL", FilingType.FORM_10K)

    company.get_filings.assert_called_once_with(form="10-K", amendments=False)


def test_no_filings_means_none():
    company = MagicMock()
    company.get_filings.return_value = _Filings([])
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        assert _parser().get_latest_filing("AAPL", FilingType.FORM_10K) is None


def test_an_edgar_failure_means_none_not_a_crash():
    company = MagicMock()
    company.get_filings.side_effect = RuntimeError("edgar down")
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        assert _parser().get_latest_filing("AAPL", FilingType.FORM_10K) is None


def test_an_uninitialized_parser_refuses_to_query():
    p = _parser()
    p._initialized = False
    with pytest.raises(ParsingFailedError, match="not initialized"):
        p.get_latest_filing("AAPL", FilingType.FORM_10K)


# ---------------------------------------------------------------------------
# 10-K extraction — property access
# ---------------------------------------------------------------------------


def _tenk():
    return SimpleNamespace(
        business="what the company does",
        risk_factors=None,  # absent in this fake: must be skipped
        management_discussion="the md&a body",
        directors_officers_and_governance="board stuff",
    )


def test_10k_sections_come_from_properties():
    got = _parser()._extract_10k_sections(_tenk())

    assert set(got) == {"item_1", "item_7", "item_10"}
    assert got["item_1"]["title"] == "Item 1 - Business"
    assert got["item_1"]["length"] == len("what the company does")


def test_10k_extraction_honours_the_requested_subset():
    got = _parser()._extract_10k_sections(_tenk(), sections=["item_7"])
    assert set(got) == {"item_7"}


def test_a_none_section_is_skipped_silently():
    got = _parser()._extract_10k_sections(_tenk())
    assert "item_1a" not in got


# ---------------------------------------------------------------------------
# 10-Q extraction — indexed access with full-text fallback
# ---------------------------------------------------------------------------


def _tenq() -> dict:
    return {
        "Part I, Item 2": "quarterly md&a",
        "Part II, Item 1A": "quarterly risks",
    }


def test_10q_sections_come_from_indexed_access():
    got = _parser()._extract_10q_sections(_filing(), _tenq())

    assert set(got) == {"part1_item2", "part2_item1a"}
    assert got["part1_item2"]["title"] == "Part I Item 2 - MD&A"


def test_10q_defaults_to_mda_and_risk_factors():
    tenq = dict(_tenq())
    tenq["Part I, Item 1"] = "statements"
    got = _parser()._extract_10q_sections(_filing(), tenq)

    assert set(got) == {"part1_item2", "part2_item1a"}, (
        "unrequested sections must not ride along by default"
    )


def test_a_missing_10q_key_falls_back_to_full_text():
    """An empty extraction means the index keys did not match; the raw filing
    text is the fallback, not a silent empty report."""
    got = _parser()._extract_10q_sections(_filing(text="the raw filing"), {})

    assert got["full_text"]["content"] == "the raw filing"
    assert got["full_text"]["length"] == len("the raw filing")


def test_full_text_is_not_appended_when_sections_were_found():
    got = _parser()._extract_10q_sections(_filing(text="raw"), _tenq())
    assert "full_text" not in got


def test_full_text_can_be_requested_explicitly():
    got = _parser()._extract_10q_sections(
        _filing(text="raw"), _tenq(), sections=["full_text"]
    )
    assert "full_text" in got


def test_a_failing_full_text_fallback_stays_quiet():
    filing = _filing()
    filing.text = lambda: (_ for _ in ()).throw(RuntimeError("no text"))
    got = _parser()._extract_10q_sections(filing, {})
    assert got == {}


# ---------------------------------------------------------------------------
# Financial statements and metrics
# ---------------------------------------------------------------------------


def test_all_three_statements_are_extracted_as_markdown():
    got = _parser()._extract_financial_statements(
        SimpleNamespace(financials=_financials())
    )
    assert got == {
        "balance_sheet": "| Total assets | 1 |",
        "income_statement": "| Revenue | 2 |",
        "cash_flow_statement": "| Operating | 3 |",
    }


def test_a_missing_financials_object_yields_nothing():
    assert _parser()._extract_financial_statements(SimpleNamespace()) == {}


def test_a_statement_method_blowing_up_does_not_kill_the_others():
    financials = SimpleNamespace(
        balance_sheet=lambda: (_ for _ in ()).throw(RuntimeError("xbrl blew up")),
        income_statement=lambda: _stmt("| Revenue | 2 |"),
    )
    got = _parser()._extract_financial_statements(SimpleNamespace(financials=financials))
    assert got == {"income_statement": "| Revenue | 2 |"}


def test_metrics_come_from_the_financials_helper():
    got = _parser()._extract_financial_metrics(
        SimpleNamespace(financials=_financials({"revenue": 1.0}))
    )
    assert got == {"revenue": 1.0}


# ---------------------------------------------------------------------------
# parse_filing — the assembled product
# ---------------------------------------------------------------------------


def test_parse_filing_without_any_filing_is_a_domain_error():
    company = MagicMock()
    company.get_filings.return_value = _Filings([])
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        with pytest.raises(ParsingFailedError, match="No 10-K found for AAPL"):
            _parser().parse_filing("AAPL", FilingType.FORM_10K)


def test_parse_filing_as_dict_carries_metadata_and_sections():
    obj = SimpleNamespace(
        financials=None,
        **{k: v for k, v in {
            "business": "b",
            "risk_factors": None,
            "management_discussion": "m",
            "directors_officers_and_governance": None,
        }.items()},
    )
    company = MagicMock()
    company.get_filings.return_value = _Filings([_filing(obj=obj)])
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        result = _parser().parse_filing("AAPL", FilingType.FORM_10K, output_format="dict")

    assert result["symbol"] == "AAPL"
    assert result["filing_type"] == "10-K"
    assert result["filing_date"] == "2026-01-15"
    assert result["cik"] == "0000320193"
    assert result["source_url"] == "https://sec.gov/aapl-10k.htm"
    assert set(result["sections"]) == {"item_1", "item_7"}
    assert result["sections_extracted"] == 2
    assert result["total_content_length"] > 0


def test_parse_filing_as_markdown_embeds_the_metrics_table():
    obj = SimpleNamespace(financials=_financials())
    filing = _filing(obj=obj)
    filing.period_of_report = None  # 10-Q-ish: period may be absent
    company = MagicMock()
    company.get_filings.return_value = _Filings([filing])
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        out = _parser().parse_filing(
            "aapl",
            FilingType.FORM_10K,
            include_financials=True,
            output_format="markdown",
        )

    assert set(out) == {"content", "metadata"}
    assert out["metadata"]["symbol"] == "AAPL"
    assert "# AAPL 10-K Filing" in out["content"]
    assert "https://sec.gov/aapl-10k.htm" in out["content"]


def test_a_parsing_failure_is_wrapped_as_parsing_failed():
    obj = SimpleNamespace(financials=_financials())
    filing = _filing(obj=obj)
    filing.obj = lambda: (_ for _ in ()).throw(RuntimeError("obj exploded"))
    company = MagicMock()
    company.get_filings.return_value = _Filings([filing])
    with patch("edgar.set_identity"), patch("edgar.Company", return_value=company):
        with pytest.raises(ParsingFailedError, match="obj exploded"):
            _parser().parse_filing("AAPL", FilingType.FORM_10K)


# ---------------------------------------------------------------------------
# Markdown rendering — the numbers the model quotes
# ---------------------------------------------------------------------------


def test_metric_billions_are_rendered_with_two_decimals():
    result = {
        "symbol": "AAPL",
        "filing_type": "10-K",
        "filing_date": "2026-01-15",
        "period_end": "2025-12-31",
        "cik": "1",
        "source_url": "u",
        "sections": {
            "item_7": {"title": "MD&A", "content": "body", "length": 4},
        },
        "financial_statements": {},
        "financial_metrics": {"revenue": 4.1e9, "net_income": 9.93e8, "current_ratio": 0.87},
    }
    md = _parser()._format_as_markdown(result)

    assert "| Revenue | $4.10B |" in md
    assert "| Net Income | $0.99B |" in md
    assert "| Current Ratio | 0.87 |" in md
    assert "*Length: 4 characters*" in md


def test_a_zero_metric_is_omitted_not_rendered_as_zero_dollars():
    """A falsy metric means 'unknown' here; printing $0.00B would be a lie."""
    result = {
        "symbol": "AAPL", "filing_type": "10-K", "filing_date": "d",
        "period_end": None, "cik": "1", "source_url": "u",
        "sections": {}, "financial_statements": {},
        "financial_metrics": {"revenue": 0, "current_ratio": None},
    }
    md = _parser()._format_as_markdown(result)
    assert "Revenue" not in md
    assert "Current Ratio" not in md


# ---------------------------------------------------------------------------
# The row-classification regexes (module-level contract)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["Total assets", "Net income", "Net sales", "Total liabilities and equity"])
def test_total_pattern_matches_the_labels_providers_emit(label: str):
    import re
    assert any(re.search(p, label, re.IGNORECASE) for p in TOTAL_PATTERNS), label


@pytest.mark.parametrize("label", ["Total current assets", "Total non-current liabilities"])
def test_subtotal_pattern_matches_the_subtotals(label: str):
    import re
    assert any(re.search(p, label, re.IGNORECASE) for p in SUBTOTAL_PATTERNS), label


@pytest.mark.parametrize("label", ["Revenue from contracts", "Cost of goods sold"])
def test_operating_lines_are_not_totals(label: str):
    import re
    assert not any(re.search(p, label, re.IGNORECASE) for p in TOTAL_PATTERNS), label
