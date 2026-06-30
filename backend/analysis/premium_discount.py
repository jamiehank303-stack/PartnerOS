"""
analysis/premium_discount.py

Premium / discount / equilibrium range classification.

Given a price range (typically bounded by a significant swing high and
swing low), this module divides it at the midpoint ("equilibrium") into a
"discount" zone (lower half) and a "premium" zone (upper half), and
classifies candle closes within that range accordingly. This is a
structural positioning concept only -- it makes no buy/sell
recommendation, leaving any such interpretation to a future, explicitly
out-of-scope strategy layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from analysis.candle import Candle


class PriceZone(str, Enum):
    """Classification of a price's position within a dealing range."""

    DISCOUNT = "DISCOUNT"
    EQUILIBRIUM = "EQUILIBRIUM"
    PREMIUM = "PREMIUM"


@dataclass(frozen=True, slots=True)
class PremiumDiscountRange:
    """
    A defined high/low dealing range and its derived zone boundaries.

    Attributes:
        range_high: Upper bound of the range.
        range_low: Lower bound of the range.
        equilibrium_tolerance: Fractional width (of the full range) around
            the exact midpoint that is classified as EQUILIBRIUM rather
            than strictly PREMIUM or DISCOUNT. E.g. `0.05` reserves the
            middle 5% of the range as an equilibrium band.
    """

    range_high: float
    range_low: float
    equilibrium_tolerance: float = 0.0

    def __post_init__(self) -> None:
        if self.range_high <= self.range_low:
            raise ValueError("range_high must be greater than range_low.")
        if not (0.0 <= self.equilibrium_tolerance < 1.0):
            raise ValueError("equilibrium_tolerance must be within [0.0, 1.0).")

    @property
    def equilibrium(self) -> float:
        """The exact midpoint price of the range."""
        return (self.range_high + self.range_low) / 2

    @property
    def range_size(self) -> float:
        """Full size of the range (range_high - range_low)."""
        return self.range_high - self.range_low

    def classify(self, price: float) -> PriceZone:
        """
        Classify a given price as PREMIUM, DISCOUNT, or EQUILIBRIUM.

        Args:
            price: The price to classify.

        Returns:
            The `PriceZone` the price falls into, relative to this range's
            equilibrium and tolerance band.
        """
        band = self.range_size * self.equilibrium_tolerance / 2
        if self.equilibrium - band <= price <= self.equilibrium + band:
            return PriceZone.EQUILIBRIUM
        return PriceZone.PREMIUM if price > self.equilibrium else PriceZone.DISCOUNT


@dataclass(frozen=True, slots=True)
class PriceZoneClassification:
    """
    The zone classification of a single candle's close within a range.

    Attributes:
        index: Index of the classified candle.
        candle: The classified candle.
        zone: The `PriceZone` its close falls into.
        dealing_range: The `PremiumDiscountRange` used for classification.
    """

    index: int
    candle: Candle
    zone: PriceZone
    dealing_range: PremiumDiscountRange


class PremiumDiscountAnalyzer:
    """
    Classifies candles within a dealing range as premium, discount, or
    equilibrium based on their close price.

    If no explicit range is supplied to `detect()`, the analyzer derives
    one automatically from the highest high and lowest low observed across
    the supplied candles.
    """

    def __init__(self, equilibrium_tolerance: float = 0.0) -> None:
        """
        Args:
            equilibrium_tolerance: Default fractional equilibrium band
                width, used when not overridden per-call. See
                `PremiumDiscountRange.equilibrium_tolerance`.
        """
        self.equilibrium_tolerance = equilibrium_tolerance

    def detect(
        self,
        candles: list[Candle],
        range_high: float | None = None,
        range_low: float | None = None,
    ) -> list[PriceZoneClassification]:
        """
        Classify every candle's close within a dealing range.

        Args:
            candles: Chronologically ordered list of candles.
            range_high: Optional explicit upper bound of the dealing range.
                If omitted, the highest high across `candles` is used.
            range_low: Optional explicit lower bound of the dealing range.
                If omitted, the lowest low across `candles` is used.

        Returns:
            A list of `PriceZoneClassification`, one per candle, in
            chronological order. Returns an empty list if `candles` is
            empty.
        """
        if not candles:
            return []

        resolved_high = range_high if range_high is not None else max(c.high for c in candles)
        resolved_low = range_low if range_low is not None else min(c.low for c in candles)

        dealing_range = PremiumDiscountRange(
            range_high=resolved_high,
            range_low=resolved_low,
            equilibrium_tolerance=self.equilibrium_tolerance,
        )

        return [
            PriceZoneClassification(
                index=i,
                candle=candle,
                zone=dealing_range.classify(candle.close),
                dealing_range=dealing_range,
            )
            for i, candle in enumerate(candles)
        ]
