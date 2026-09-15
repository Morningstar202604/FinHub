"""Types shared by the SEC tools.

The one piece with real logic is ``FinancialMetrics.from_dict``: providers hand
back dictionaries with dozens of keys, and the model must not see fields this
codebase never reads — an unknown key here is a silent contract drift, not a
crash, so the filter is what keeps the surface honest.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.tools.sec.types import (
    DEFAULT_10K_SECTIONS,
    DEFAULT_10Q_SECTIONS,
    FORM_8K_ITEMS,
    FinancialMetrics,
    FilingType,
    SECFiling,
    SECSection,
)


# ---------------------------------------------------------------------------
# FinancialMetrics.from_dict — the filter against provider dictionaries
# ---------------------------------------------------------------------------


def test_known_fields_survive_the_filter():
    metrics = FinancialMetrics.from_dict(
        {"revenue": 1.0, "net_income": 2.0, "current_ratio": 1.5}
    )
    assert metrics.revenue == 1.0
    assert metrics.net_income == 2.0
    assert metrics.current_ratio == 1.5


def test_unknown_provider_fields_are_dropped_not_kept():
    """A renamed provider key must not leak into the model as dead data."""
    metrics = FinancialMetrics.from_dict(
        {"revenue": 1.0, "totalRevenue": 9e9, "ebitda_margin": 0.3}
    )
    assert metrics.revenue == 1.0
    assert metrics.model_extra in (None, {})


def test_an_empty_dictionary_yields_an_all_none_model():
    metrics = FinancialMetrics.from_dict({})
    assert metrics.revenue is None
    assert metrics.free_cash_flow is None


def test_none_values_are_preserved_as_none():
    """Providers emit nulls for unavailable metrics; they must stay None,
    because downstream code branches on None rather than absence."""
    metrics = FinancialMetrics.from_dict({"revenue": None, "net_income": 5.0})
    assert metrics.revenue is None
    assert metrics.net_income == 5.0


# ---------------------------------------------------------------------------
# SECSection / SECFiling
# ---------------------------------------------------------------------------


def test_a_section_records_its_own_length():
    section = SECSection.from_content("Item 1", "hello world")
    assert section.length == len("hello world")
    assert section.title == "Item 1"


def test_total_content_length_sums_sections():
    filing = SECFiling(
        symbol="AAPL",
        filing_type=FilingType.FORM_10K,
        filing_date="2026-01-15",
        sections={
            "item_1": SECSection(title="Item 1", content="a" * 10, length=10),
            "item_1a": SECSection(title="Item 1A", content="b" * 32, length=32),
        },
    )
    assert filing.total_content_length == 42


def test_a_filing_rejects_an_unknown_type():
    with pytest.raises(ValidationError):
        SECFiling(
            symbol="AAPL",
            filing_type="S-1",
            filing_date="2026-01-15",
            sections={},
        )


# ---------------------------------------------------------------------------
# The item map is financial vocabulary — errors here mislead the model
# ---------------------------------------------------------------------------


def test_the_two_money_items_have_their_descriptions():
    """Item 2.02 is how a company announces results; Item 7.01 is how it
    gives forward guidance. These two strings are the signal the model
    actually keys on when it triages a filing list."""
    assert "Results of Operations" in FORM_8K_ITEMS["Item 2.02"]
    assert "Regulation FD" in FORM_8K_ITEMS["Item 7.01"]


def test_every_item_entry_is_a_nonempty_description():
    for item, desc in FORM_8K_ITEMS.items():
        assert desc, f"{item} has an empty description"


def test_default_section_sets_exist_in_their_maps():
    from src.tools.sec.types import FORM_10K_SECTIONS, FORM_10Q_SECTIONS

    assert set(DEFAULT_10K_SECTIONS) <= set(FORM_10K_SECTIONS)
    assert set(DEFAULT_10Q_SECTIONS) <= set(FORM_10Q_SECTIONS)
