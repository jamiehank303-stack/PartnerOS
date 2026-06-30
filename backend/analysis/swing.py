"""
analysis/swing.py

Swing high / swing low detection.

A swing point is a structural pivot: a candle whose high (or low) is more
extreme than a fixed number of candles on either side of it. Swing points
are the foundational building block for the higher-level structure
concepts elsewhere in this package (liquidity pools, sweeps, BOS/CHoCH,
etc.), but this module only detects them -- it has no opinion about trend,
bias, or trading strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from analysis.candle import Candle


class SwingType(str, Enum):
    """Classification of a swing point."""

    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """
    A single confirmed swing high or swing low.

    Attributes:
        index: Position of the pivot candle within the original candle list.
        candle: The pivot candle itself.
        swing_type: Whether this is a swing HIGH or swing LOW.
        price: The pivot price (the candle's high for SwingType.HIGH, the
            candle's low for SwingType.LOW).
        strength: The lookback/lookforward window (number of candles on
            each side) used to confirm this pivot.
    """

    index: int
    candle: Candle
    swing_type: SwingType
    price: float
    strength: int


class SwingDetector:
    """
    Detects fractal-style swing highs and swing lows in a candle series.

    A candle at index `i` is confirmed as a swing high if its high is
    strictly greater than the highs of `strength` candles immediately
    preceding and following it (and symmetrically for swing lows). This is
    pure price-structure logic -- no indicators are involved.
    """

    def __init__(self, strength: int = 2) -> None:
        """
        Args:
            strength: Number of candles required on both sides of a
                candidate pivot for it to be confirmed. Higher values
                produce fewer, more significant swing points.

        Raises:
            ValueError: If `strength` is less than 1.
        """
        if strength < 1:
            raise ValueError("strength must be at least 1.")
        self.strength = strength

    def detect(self, candles: list[Candle]) -> list[SwingPoint]:
        """
        Identify all confirmed swing highs and swing lows in `candles`.

        Args:
            candles: Chronologically ordered list of candles.

        Returns:
            A list of `SwingPoint` objects in chronological order. The
            first and last `strength` candles can never be confirmed as
            swing points (insufficient candles on one side) and are
            therefore excluded.
        """
        swings: list[SwingPoint] = []
        n = len(candles)

        for i in range(self.strength, n - self.strength):
            window_left = candles[i - self.strength : i]
            window_right = candles[i + 1 : i + 1 + self.strength]
            candidate = candles[i]

            if self._is_swing_high(candidate, window_left, window_right):
                swings.append(
                    SwingPoint(
                        index=i,
                        candle=candidate,
                        swing_type=SwingType.HIGH,
                        price=candidate.high,
                        strength=self.strength,
                    )
                )
            elif self._is_swing_low(candidate, window_left, window_right):
                swings.append(
                    SwingPoint(
                        index=i,
                        candle=candidate,
                        swing_type=SwingType.LOW,
                        price=candidate.low,
                        strength=self.strength,
                    )
                )

        return swings

    @staticmethod
    def _is_swing_high(candidate: Candle, left: list[Candle], right: list[Candle]) -> bool:
        """True if `candidate.high` strictly exceeds all highs in both windows."""
        return all(candidate.high > c.high for c in left) and all(candidate.high > c.high for c in right)

    @staticmethod
    def _is_swing_low(candidate: Candle, left: list[Candle], right: list[Candle]) -> bool:
        """True if `candidate.low` strictly subceeds all lows in both windows."""
        return all(candidate.low < c.low for c in left) and all(candidate.low < c.low for c in right)
