"""
analysis/ftc.py

Failure-to-continue (FTC) detection.

After a liquidity sweep, price is expected -- per liquidity-driven market
structure theory -- to reverse rather than continue in the direction of
the sweep. An FTC event confirms that expectation: following a buy-side
sweep (price swept above a prior high), FTC is confirmed when a later
candle closes back below the sweeping candle's low, demonstrating that the
upside move failed to continue. The sell-side case is the mirror image.

This module depends only on `LiquiditySweep` objects produced by
`analysis/sweep.py` -- it does not recompute sweeps itself, keeping sweep
detection and follow-through detection as separate, independently
testable concerns.
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.candle import Candle
from analysis.liquidity import LiquidityType
from analysis.sweep import LiquiditySweep, SweepDetector


@dataclass(frozen=True, slots=True)
class FailureToContinue:
    """
    A confirmed failure-to-continue event following a liquidity sweep.

    Attributes:
        sweep: The `LiquiditySweep` this FTC follows from.
        confirmation_index: Index of the candle whose close confirmed the
            failure to continue.
        confirmation_candle: The confirming candle itself.
    """

    sweep: LiquiditySweep
    confirmation_index: int
    confirmation_candle: Candle


class FTCDetector:
    """
    Detects failure-to-continue events following liquidity sweeps.

    Internally composes a `SweepDetector` to locate sweeps, then scans
    forward from each sweep (within `max_lookahead` candles, if specified)
    for the first candle whose close breaches the sweeping candle's
    opposite extreme -- confirming that the swept direction failed to
    continue.
    """

    def __init__(
        self,
        swing_strength: int = 2,
        equal_tolerance: float = 0.0005,
        max_lookahead: int | None = None,
    ) -> None:
        """
        Args:
            swing_strength: Passed through to the internal `SweepDetector`.
            equal_tolerance: Passed through to the internal `SweepDetector`.
            max_lookahead: Optional maximum number of candles after a sweep
                to search for confirmation. `None` means search to the end
                of the series.

        Raises:
            ValueError: If `max_lookahead` is provided and is not positive.
        """
        if max_lookahead is not None and max_lookahead < 1:
            raise ValueError("max_lookahead must be positive when provided.")
        self._sweep_detector = SweepDetector(swing_strength=swing_strength, equal_tolerance=equal_tolerance)
        self.max_lookahead = max_lookahead

    def detect(self, candles: list[Candle]) -> list[FailureToContinue]:
        """
        Identify all failure-to-continue events in the candle series.

        Args:
            candles: Chronologically ordered list of candles.

        Returns:
            A list of `FailureToContinue` events in chronological order of
            their confirmation candle.
        """
        sweeps = self._sweep_detector.detect(candles)
        events: list[FailureToContinue] = []

        for sweep in sweeps:
            confirmation = self._find_confirmation(sweep, candles)
            if confirmation is not None:
                events.append(confirmation)

        events.sort(key=lambda e: e.confirmation_index)
        return events

    def _find_confirmation(self, sweep: LiquiditySweep, candles: list[Candle]) -> FailureToContinue | None:
        """Search forward from `sweep` for the first confirming candle."""
        start = sweep.index + 1
        end = len(candles) if self.max_lookahead is None else min(len(candles), start + self.max_lookahead)

        for i in range(start, end):
            candle = candles[i]
            if sweep.pool.liquidity_type == LiquidityType.BUY_SIDE:
                # Buy-side sweep expects failure: close below sweeping candle's low.
                if candle.close < sweep.candle.low:
                    return FailureToContinue(sweep=sweep, confirmation_index=i, confirmation_candle=candle)
            else:
                # Sell-side sweep expects failure: close above sweeping candle's high.
                if candle.close > sweep.candle.high:
                    return FailureToContinue(sweep=sweep, confirmation_index=i, confirmation_candle=candle)

        return None
