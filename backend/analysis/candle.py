"""
analysis/candle.py

Core price-bar data structure for the PartnerOS Market Structure Engine.

`Candle` is the single atomic unit every other detector in this package
operates on. It is intentionally minimal and indicator-free -- it carries
only the raw OHLC price data (plus timestamp and optional volume) that
market-structure analysis is derived from. No moving averages, oscillators,
volume profile, or order-flow state belongs here or anywhere else in this
package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CandleDirection(str, Enum):
    """Directional classification of a single candle based on close vs open."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    DOJI = "DOJI"


@dataclass(frozen=True, slots=True)
class Candle:
    """
    A single immutable OHLC price bar.

    Attributes:
        timestamp: The time the candle opened (or closed, per data source
            convention -- the engine only requires internal consistency
            across the series).
        open: Opening price.
        high: Highest traded price during the candle.
        low: Lowest traded price during the candle.
        close: Closing price.
        volume: Optional traded volume. Not consumed by any detector in
            this package (no volume-profile or order-flow analysis is
            performed here) but retained on the data model for
            completeness and potential future, explicitly-requested use.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise ValueError(f"Candle high ({self.high}) cannot be less than low ({self.low}).")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"Candle open ({self.open}) must lie within [low, high].")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"Candle close ({self.close}) must lie within [low, high].")

    @property
    def direction(self) -> CandleDirection:
        """Classify the candle as bullish, bearish, or doji (open == close)."""
        if self.close > self.open:
            return CandleDirection.BULLISH
        if self.close < self.open:
            return CandleDirection.BEARISH
        return CandleDirection.DOJI

    @property
    def body_size(self) -> float:
        """Absolute size of the candle body (|close - open|)."""
        return abs(self.close - self.open)

    @property
    def range_size(self) -> float:
        """Full high-to-low range of the candle."""
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        """Size of the upper wick (high down to the top of the body)."""
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        """Size of the lower wick (bottom of the body down to the low)."""
        return min(self.open, self.close) - self.low

    @property
    def midpoint(self) -> float:
        """Midpoint price of the candle's full high/low range."""
        return (self.high + self.low) / 2


@dataclass(frozen=True, slots=True)
class IndexedCandle:
    """
    A `Candle` paired with its position in a series.

    Several detectors need to refer back to "where" a candle sits within
    the original sequence (e.g. to express a swing point or sweep in terms
    of its index), so this lightweight wrapper avoids every downstream
    dataclass having to carry both a candle and a raw `int` separately.
    """

    index: int
    candle: Candle
