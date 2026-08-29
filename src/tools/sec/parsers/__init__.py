"""
SEC filing parsers.

Provides parser implementations for extracting sections from SEC filings.
"""

from .base import BaseSECParser, ParserError, ParsingFailedError, SectionNotFoundError
from .edgartools_parser import EdgarToolsParser
from .regex_parser import RegexParser

__all__ = [
    # Base classes
    "BaseSECParser",
    "ParserError",
    "ParsingFailedError",
    "SectionNotFoundError",
    # Implementations
    "EdgarToolsParser",  # Primary parser (direct SEC access)
    "RegexParser",  # Fallback: regex-based extraction
]
