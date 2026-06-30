"""
analysis/sweep.py

Liquidity sweep detection.

A "sweep" occurs when price trades through a previously identified
liquidity pool (taking out the resting orders assumed to sit there) and
then closes back on the opposite side of that level within the same
candle -- a classic stop-hunt / liquidity-grab signature. This module only
detects that this price event happened; it makes no assumption about what
happens afterward (see `analysis/ftc.py` for follow-through analysis).

If a pool level is instead pierced WITHOUT the close returning back inside
(i.e. a genuine breakout rather than a sweep), the pool's liquidity is
still considered consumed at that point -- it is simply not recorded as a
`LiquiditySweep`, since acceptance-style breaks are the concern of
`analysis/acceptance.py`, not this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.candle import Candle
from analysis.liquidity import LiquidityDetector, LiquidityPool, LiquidityType


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    """
    A single confirmed liquidity sweep event.

    Attributes:
        pool: The `LiquidityPool` that was swept.
        index: Index of the candle that performed the sweep.
        candle: The sweeping candle itself.
        extreme_price: The furthest price reached beyond the pool level
            (the candle's high for a buy-side sweep, low for a sell-side
            sweep).
    """

    pool: LiquidityPool
    index: int
    candle: Candle
    extreme_price: float


class SweepDetector:
    """
    Detects liquidity sweeps of buy-side and sell-side pools.

    Internally composes a `LiquidityDetector` to locate pools, then scans
    candles occurring after each pool's most recent contributing swing
    point for the first candle that pierces the pool level. If that
    candle's close also returns to the opposite side of the level, a
    `LiquiditySweep` is recorded. Either way, scanning for that pool stops
    at first touch -- once pierced, a level's resting liquidity is
    considered consumed.
    """

    def __init__(self, swing_strength: int = 2, equal_tolerance: float = 0.0005) -> None:
        """
        Args:
            swing_strength: Passed through to the internal `LiquidityDetector`.
            equal_tolerance: Passed through to the internal `LiquidityDetector`.
        """
        self._liquidity_detector = LiquidityDetector(
            swing_strength=swing_strength,
            equal_tolerance=equal_tolerance,
        )

    def detect(self, candles: list[Candle]) -> list[LiquiditySweep]:
        """
        Identify all liquidity sweeps in the candle series.

        Args:
            candles: Chronologically ordered list of candles.

        Returns:
            A list of `LiquiditySweep` events in chronological order of the
            sweeping candle.
        """
        pools = self._liquidity_detector.detect(candles)
        sweeps: list[LiquiditySweep] = []

        for pool in pools:
            pool_formed_index = max(sp.index for sp in pool.swing_points)

            for i in range(pool_formed_index + 1, len(candles)):
                candle = candles[i]
                pierced, closed_back_inside, extreme_price = self._evaluate(pool, candle)

                if not pierced:
                    continue

                if closed_back_inside:
                    sweeps.append(
                        LiquiditySweep(
                            pool=pool,
                            index=i,
                            candle=candle,
                            extreme_price=extreme_price,
                        )
                    )
                # First touch consumes the pool's liquidity either way.
                break

        sweeps.sort(key=lambda s: s.index)
        return sweeps

    @staticmethod
    def _evaluate(pool: LiquidityPool, candle: Candle) -> tuple[bool, bool, float]:
        """
        Evaluate a single candle against a pool level.

        Returns:
            A tuple of `(pierced, closed_back_inside, extreme_price)`.
        """
        if pool.liquidity_type == LiquidityType.BUY_SIDE:
            pierced = candle.high > pool.price
            closed_back_inside = candle.close < pool.price
            extreme_price = candle.high
        else:  # SELL_SIDE
            pierced = candle.low < pool.price
            closed_back_inside = candle.close > pool.price
            extreme_price = candle.low

        return pierced, closed_back_inside, extreme_price
