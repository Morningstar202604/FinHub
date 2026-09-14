"""Interval bijection and parity with the legacy market_hours table."""

import pytest

from src.market_protocol.enums import OHLCV_SCHEMAS
from src.market_protocol.intervals import (
    Timeframe,
    is_intraday_schema,
    legacy_for_schema,
    schema_for_legacy,
    schema_seconds,
)
from src.utils.market_hours import _INTERVAL_SECONDS, interval_seconds


def test_bijection():
    for schema in OHLCV_SCHEMAS:
        assert schema_for_legacy(legacy_for_schema(schema)) == schema


def test_parity_with_market_hours():
    """schema_seconds must agree with the legacy staleness table exactly."""
    for legacy, seconds in _INTERVAL_SECONDS.items():
        assert schema_seconds(schema_for_legacy(legacy)) == seconds
        assert schema_seconds(schema_for_legacy(legacy)) == interval_seconds(legacy)
    # And cover the same interval set — no legacy interval left unmapped.
    assert {legacy_for_schema(s) for s in OHLCV_SCHEMAS} == set(_INTERVAL_SECONDS)


def test_intraday_classification():
    assert is_intraday_schema("ohlcv-1s")
    assert is_intraday_schema("ohlcv-4h")
    assert not is_intraday_schema("ohlcv-1d")


@pytest.mark.parametrize("bad", ["1m", "ohlcv-1min", "daily", ""])
def test_unknown_legacy_raises(bad):
    with pytest.raises(ValueError):
        schema_for_legacy(bad)


def test_timeframe_is_the_chartable_subset_of_schemas():
    """`Timeframe` is every schema except 1-second bars.

    It moved here from the chart-annotation tool package because the server's
    own request models needed it — a tool must not own a type the server layer
    imports (see scripts/guard/layering_guard.py). These assertions pin the
    exact contents so the move cannot quietly change what the LLM may request.
    """
    args = set(Timeframe.__args__)
    assert args == {"1min", "5min", "15min", "30min", "1hour", "4hour", "1day"}
    # Every chartable legacy string round-trips to a real schema...
    assert {schema_for_legacy(t) for t in args} == set(OHLCV_SCHEMAS) - {"ohlcv-1s"}
    # ...and 1s is excluded on purpose: a chart is identified by SYMBOL:timeframe
    # and no chart can exist on second bars.
    assert "1s" not in args


def test_timeframe_is_the_single_shared_object():
    """The tool layer re-exports this exact object, not a second copy.

    A duplicated Literal would pass every functional test while letting the two
    definitions drift apart.
    """
    from src.tools.chart_annotation.schemas import Timeframe as ToolTimeframe

    assert ToolTimeframe is Timeframe


def test_chart_tool_json_schema_pins_the_enum():
    """The JSON schema is the contract the model actually sees.

    Moving Timeframe must not alter the enum or default the LLM is shown, even
    though no arithmetic changed.
    """
    from src.tools.chart_annotation.schemas import (
        DrawChartAnnotationArgs,
        ManageChartAnnotationsArgs,
    )

    expected = ["1min", "5min", "15min", "30min", "1hour", "4hour", "1day"]
    for model in (DrawChartAnnotationArgs, ManageChartAnnotationsArgs):
        prop = model.model_json_schema()["properties"]["timeframe"]
        assert prop["enum"] == expected, model.__name__
        assert prop["default"] == "1day", model.__name__
