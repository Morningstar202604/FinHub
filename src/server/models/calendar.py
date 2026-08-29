"""Pydantic models for calendar endpoints (economic releases & earnings)."""

from typing import Optional

from pydantic import BaseModel, Field


class EconomicEvent(BaseModel):
    """Single economic data release event."""

    date: str = Field(..., description="Event datetime (e.g., 2024-03-01 03:35:00)")
    country: str = Field(..., description="Country code (e.g., US, JP, GB)")
    event: str = Field(..., description="Event name (e.g., 3-Month Bill Auction)")
    currency: str = Field(..., description="Currency code (e.g., USD, JPY)")
    previous: Optional[float] = Field(None, description="Previous value")
    estimate: Optional[float] = Field(None, description="Estimated value")
    actual: Optional[float] = Field(None, description="Actual value (null if not yet released)")
    change: Optional[float] = Field(None, description="Change from previous")
    impact: Optional[str] = Field(None, description="Impact level (Low, Medium, High)")
    changePercentage: Optional[float] = Field(None, description="Change percentage")


class EconomicCalendarResponse(BaseModel):
    """Response for economic calendar endpoint."""

    data: list[EconomicEvent] = Field(default_factory=list, description="Economic events")
    count: int = Field(0, description="Number of events returned")


class EarningsEvent(BaseModel):
    """Single earnings calendar event."""

    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)")
    date: str = Field(..., description="Earnings announcement date (YYYY-MM-DD)")
    epsActual: Optional[float] = Field(None, description="Actual EPS")
    epsEstimated: Optional[float] = Field(None, description="Estimated EPS")
    revenueActual: Optional[float] = Field(None, description="Actual revenue")
    revenueEstimated: Optional[float] = Field(None, description="Estimated revenue")
    lastUpdated: Optional[str] = Field(None, description="Last updated date")


class EarningsCalendarResponse(BaseModel):
    """Response for earnings calendar endpoint."""

    data: list[EarningsEvent] = Field(default_factory=list, description="Earnings events")
    count: int = Field(0, description="Number of events returned")
