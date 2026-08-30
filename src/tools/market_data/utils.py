"""
Utility functions for market data tools.

Provides helper functions for formatting, market session detection, and FMP client access.
"""

from typing import Optional, Tuple
from datetime import datetime
import math
import logging

from src.utils.market_hours import ET, current_market_phase

logger = logging.getLogger(__name__)

# Maps market_hours phases to the tool-facing labels used in agent output.
_SESSION_LABELS = {
    "pre": "PRE_MARKET",
    "open": "REGULAR_HOURS",
    "post": "AFTER_HOURS",
    "closed": "CLOSED",
}


def get_market_session() -> Tuple[str, datetime]:
    """
    Determine current US market session based on Eastern Time.

    Delegates phase classification to ``market_hours.current_market_phase``
    (holiday-aware: a weekday holiday reports CLOSED) and maps the phase to
    the tool-facing label. Replaces the previous hand-rolled session logic
    that only checked weekdays and re-implemented the same time boundaries.

    Returns:
        Tuple of (session_name, current_et_time)
        session_name: "PRE_MARKET", "REGULAR_HOURS", "AFTER_HOURS", or "CLOSED"
    """
    now_et = datetime.now(ET)
    return _SESSION_LABELS[current_market_phase(now_et)], now_et


def format_number(value: Optional[float], suffix: bool = True) -> str:
    """
    Format large numbers with B/M/T suffixes or as currency.

    Args:
        value: Number to format
        suffix: Whether to add B/M/T suffix for large numbers

    Returns:
        Formatted string (e.g., "$3.68T", "$247.92")
    """
    if value is None:
        return "N/A"

    if suffix and abs(value) >= 1e12:
        return f"${value / 1e12:.2f}T"
    elif suffix and abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    elif suffix and abs(value) >= 1e6:
        return f"${value / 1e6:.2f}M"
    elif suffix:
        return f"${value:,.2f}"
    else:
        return f"{value:,.2f}"


def finite_or_none(value) -> Optional[float]:
    """Return value if it's a finite number, else None (NaN/Inf/non-numeric)."""
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def format_percentage(value: Optional[float]) -> str:
    """
    Format decimal as percentage with sign.

    Args:
        value: Decimal value (e.g., 0.0523 for 5.23%)

    Returns:
        Formatted percentage string (e.g., "+5.23%", "-2.15%")
    """
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        # Non-finite (NaN/Inf) renders as "+nan%" otherwise — treat as missing.
        return f"{value:+.2f}%" if math.isfinite(value) else "N/A"
    return str(value)


def get_rating_label(score: int) -> str:
    """
    Convert numeric score to letter grade.

    Args:
        score: Numeric score (typically 0-5)

    Returns:
        Letter grade (A+, A, A-, B+, B, B-, C, D)
    """
    if score >= 4.5:
        return "A+"
    elif score >= 4:
        return "A"
    elif score >= 3.5:
        return "A-"
    elif score >= 3:
        return "B+"
    elif score >= 2.5:
        return "B"
    elif score >= 2:
        return "B-"
    elif score >= 1.5:
        return "C"
    else:
        return "D"
