"""
analysis/structure.py

Market structure (trend) detection via Break of Structure (BOS) and
Change of Character (CHoCH).

This module determines the prevailing directional bias of price purely
from the sequence of swing highs/lows and subsequent closes that break
them:

  - A BOS (Break of Structure) is a close beyond the most recent relevant
    swing point in the direction of the *current* bias -- confirming trend
    continuation.
  - A CHoCH (Change of Character) is a close beyond the most recent
    relevant swing point *against* the current bias -- signaling a
    potential reversal, after which bias flips.

No indicators are used. This module only labels structure; it does not
generate trade signals or strategy decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from analysis.candle import Candle
from analysis.swing import SwingDetector, SwingPoint, SwingType


class StructureBias(str, Enum):
    """Prevailing directional bias implied by confirmed market structure."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class StructureEventType(str, Enum):
    """Classification of a structural break event."""

    BOS = "BOS"      # Break of Structure -- continuation of current bias.
    CHOCH = "CHOCH"  # Change of Character -- reversal of current bias.


@dataclass(frozen=True, slots=True)
class StructureEvent:
    """
    A single confirmed structural break (BOS or CHoCH).

    Attributes:
        event_type: Whether this break was a continuation (BOS) or a
            reversal (CHOCH).
        bias_after: The prevailing `StructureBias` immediately after this
            event is confirmed.
        index: Index of the candle whose close confirmed the break.
        candle: The confirming candle itself.
        broken_swing: The `SwingPoint` whose price was broken.
    """

    event_type: StructureEventType
    bias_after: StructureBias
    index: int
    candle: Candle
    broken_swing: SwingPoint


class StructureEngine:
    """
    Derives a chronological sequence of BOS / CHoCH structure events from a
    candle series.

    Internally composes a `SwingDetector` to obtain swing points, reduces
    them to an alternating high/low sequence, then walks the candles
    looking for closes that break the most recent relevant swing -- exactly
    as a discretionary structure-based analyst would mark up a chart.
    """

    def __init__(self, swing_strength: int = 2) -> None:
        """
        Args:
            swing_strength: Passed through to the internal `SwingDetector`.
        """
        self._swing_detector = SwingDetector(strength=swing_strength)

    def detect(self, candles: list[Candle]) -> list[StructureEvent]:
        """
        Identify the full chronological sequence of structure events.

        Args:
            candles: Chronologically ordered list of candles.

        Returns:
            A list of `StructureEvent` objects in chronological order.
        """
        swings = self._swing_detector.detect(candles)
        alternating = self._alternate(swings)

        events: list[StructureEvent] = []
        bias = StructureBias.NEUTRAL

        last_high: SwingPoint | None = None
        last_low: SwingPoint | None = None
        swing_cursor = 0  # Index into `alternating` of the next swing to register.

        for i, candle in enumerate(candles):
            # Register any swing points confirmed at or before this candle.
            while swing_cursor < len(alternating) and alternating[swing_cursor].index <= i:
                swing = alternating[swing_cursor]
                if swing.swing_type == SwingType.HIGH:
                    last_high = swing
                else:
                    last_low = swing
                swing_cursor += 1

            if last_high is not None and candle.close > last_high.price:
                event_type = StructureEventType.BOS if bias == StructureBias.BULLISH else StructureEventType.CHOCH
                bias = StructureBias.BULLISH
                events.append(
                    StructureEvent(
                        event_type=event_type,
                        bias_after=bias,
                        index=i,
                        candle=candle,
                        broken_swing=last_high,
                    )
                )
                # The broken high is consumed; a new one must form to break again.
                last_high = None

            elif last_low is not None and candle.close < last_low.price:
                event_type = StructureEventType.BOS if bias == StructureBias.BEARISH else StructureEventType.CHOCH
                bias = StructureBias.BEARISH
                events.append(
                    StructureEvent(
                        event_type=event_type,
                        bias_after=bias,
                        index=i,
                        candle=candle,
                        broken_swing=last_low,
                    )
                )
                last_low = None

        return events

    @staticmethod
    def _alternate(swings: list[SwingPoint]) -> list[SwingPoint]:
        """
        Reduce a raw chronological swing list to a strictly alternating
        HIGH/LOW sequence.

        Raw fractal detection can produce consecutive swing highs (or
        lows) without an intervening opposite swing. When that happens,
        only the most extreme of the consecutive run is structurally
        relevant (e.g. of two consecutive swing highs, only the higher one
        matters for breakout purposes), so weaker intermediate swings are
        discarded.
        """
        if not swings:
            return []

        ordered = sorted(swings, key=lambda s: s.index)
        result: list[SwingPoint] = [ordered[0]]

        for swing in ordered[1:]:
            last = result[-1]
            if swing.swing_type == last.swing_type:
                # Consecutive same-type swing: keep whichever is more extreme.
                if swing.swing_type == SwingType.HIGH and swing.price > last.price:
                    result[-1] = swing
                elif swing.swing_type == SwingType.LOW and swing.price < last.price:
                    result[-1] = swing
                # Otherwise the existing one remains more extreme; discard `swing`.
            else:
                result.append(swing)

        return result
