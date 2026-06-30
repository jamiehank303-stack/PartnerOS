"""
analysis/acceptance.py

Price acceptance detection.

"Acceptance" describes the market structurally committing to trade beyond
a given price level, as evidenced by a run of consecutive candle closes on
one side of that level -- as opposed to a single wick that merely pierces
it before reverting (see `analysis/sweep.py` for that distinct case).
Acceptance is a property of closes only and is evaluated against an
arbitrary, caller-supplied level; it has no dependency on swings,
liquidity pools, or any other detector in this package, keeping it fully
independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from analysis.candle import Candle


class AcceptanceDirection(str, Enum):
    """Side of a level on which acceptance is being evaluated."""

    ABOVE = "ABOVE"
    BELOW = "BELOW"


@dataclass(frozen=True, slots=True)
class AcceptanceEvent:
    """
    A confirmed acceptance of price beyond a level.

    Attributes:
        level: The price level acceptance is measured against.
        direction: Whether acceptance occurred above or below `level`.
        start_index: Index of the first candle in the confirming run of
            closes.
        confirmation_index: Index of the candle at which the required
            number of consecutive closes was reached (i.e. acceptance
            became confirmed).
        candles: The consecutive candles forming the confirming run.
    """

    level: float
    direction: AcceptanceDirection
    start_index: int
    confirmation_index: int
    candles: tuple[Candle, ...]


class AcceptanceDetector:
    """
    Detects acceptance of price above or below an arbitrary level.

    Acceptance is confirmed by a run of `min_consecutive_closes` candles
    whose closes all fall on the same side of `level`. The level can come
    from anywhere (a swing point, a liquidity pool's price, a manually
    chosen reference price) -- this module has no dependency on any other
    detector in the package.
    """

    def __init__(self, min_consecutive_closes: int = 2) -> None:
        """
        Args:
            min_consecutive_closes: Minimum number of consecutive closes
                required on one side of the level to confirm acceptance.

        Raises:
            ValueError: If `min_consecutive_closes` is less than 1.
        """
        if min_consecutive_closes < 1:
            raise ValueError("min_consecutive_closes must be at least 1.")
        self.min_consecutive_closes = min_consecutive_closes

    def detect(
        self,
        candles: list[Candle],
        level: float,
        direction: AcceptanceDirection,
    ) -> list[AcceptanceEvent]:
        """
        Identify every confirmed acceptance event for the given level and
        direction.

        Args:
            candles: Chronologically ordered list of candles.
            level: The reference price level.
            direction: Whether to look for acceptance ABOVE or BELOW `level`.

        Returns:
            A list of `AcceptanceEvent` objects, one per confirmed run. A
            new run begins after price closes back on the opposite side of
            the level, allowing repeated acceptance events to be detected
            across the series.
        """
        events: list[AcceptanceEvent] = []
        run_start: int | None = None

        for i, candle in enumerate(candles):
            on_side = self._is_on_side(candle.close, level, direction)

            if on_side:
                if run_start is None:
                    run_start = i
                run_length = i - run_start + 1
                if run_length == self.min_consecutive_closes:
                    events.append(
                        AcceptanceEvent(
                            level=level,
                            direction=direction,
                            start_index=run_start,
                            confirmation_index=i,
                            candles=tuple(candles[run_start : i + 1]),
                        )
                    )
            else:
                run_start = None

        return events

    @staticmethod
    def _is_on_side(close_price: float, level: float, direction: AcceptanceDirection) -> bool:
        """True if `close_price` is on the requested `direction` side of `level`."""
        if direction == AcceptanceDirection.ABOVE:
            return close_price > level
        return close_price < level
