"""
analysis/liquidity.py

Liquidity pool detection.

In price-structure terms, a "liquidity pool" is a price level where resting
orders are assumed to cluster -- above swing highs (buy-side liquidity) and
below swing lows (sell-side liquidity). When multiple swing points form at
nearly the same price (equal highs / equal lows), the resulting pool is
considered structurally stronger because more resting orders are assumed
to sit there.

This module only identifies where such pools sit. Whether a pool has since
been swept is the responsibility of `analysis/sweep.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from analysis.candle import Candle
from analysis.swing import SwingDetector, SwingPoint, SwingType


class LiquidityType(str, Enum):
    """Side of the market on which resting liquidity is assumed to sit."""

    BUY_SIDE = "BUY_SIDE"    # Above swing highs.
    SELL_SIDE = "SELL_SIDE"  # Below swing lows.


@dataclass(frozen=True, slots=True)
class LiquidityPool:
    """
    A single liquidity pool formed by one or more swing points.

    Attributes:
        price: The representative price level of the pool (the average of
            its contributing swing points' prices).
        liquidity_type: BUY_SIDE (above price, formed by swing highs) or
            SELL_SIDE (below price, formed by swing lows).
        swing_points: The swing point(s) that formed this pool. A pool
            formed by more than one swing point represents "equal highs"
            or "equal lows" -- a structurally stronger liquidity cluster.
    """

    price: float
    liquidity_type: LiquidityType
    swing_points: tuple[SwingPoint, ...] = field(default_factory=tuple)

    @property
    def is_equal_level(self) -> bool:
        """True if this pool was formed by clustering more than one swing point."""
        return len(self.swing_points) > 1


class LiquidityDetector:
    """
    Detects buy-side and sell-side liquidity pools from a candle series.

    Internally composes a `SwingDetector` to first identify swing points,
    then clusters swing highs/lows that fall within `equal_tolerance` of
    each other into single pools (representing "equal highs" / "equal
    lows"), leaving isolated swing points as single-swing pools.
    """

    def __init__(self, swing_strength: int = 2, equal_tolerance: float = 0.0005) -> None:
        """
        Args:
            swing_strength: Lookback/lookforward window passed to the
                internal `SwingDetector`.
            equal_tolerance: Maximum relative price difference (as a
                fraction of price, e.g. `0.0005` = 0.05%) for two swing
                points to be considered part of the same "equal" liquidity
                cluster.

        Raises:
            ValueError: If `equal_tolerance` is negative.
        """
        if equal_tolerance < 0:
            raise ValueError("equal_tolerance must be non-negative.")
        self._swing_detector = SwingDetector(strength=swing_strength)
        self.equal_tolerance = equal_tolerance

    def detect(self, candles: list[Candle]) -> list[LiquidityPool]:
        """
        Identify all buy-side and sell-side liquidity pools.

        Args:
            candles: Chronologically ordered list of candles.

        Returns:
            A list of `LiquidityPool` objects: buy-side pools followed by
            sell-side pools, each group ordered by ascending price.
        """
        swings = self._swing_detector.detect(candles)
        highs = [s for s in swings if s.swing_type == SwingType.HIGH]
        lows = [s for s in swings if s.swing_type == SwingType.LOW]

        buy_side_pools = self._cluster(highs, LiquidityType.BUY_SIDE)
        sell_side_pools = self._cluster(lows, LiquidityType.SELL_SIDE)

        return buy_side_pools + sell_side_pools

    def _cluster(self, swing_points: list[SwingPoint], liquidity_type: LiquidityType) -> list[LiquidityPool]:
        """
        Group swing points whose prices fall within tolerance of one
        another into single `LiquidityPool` instances.

        Uses a simple greedy clustering approach: swing points are sorted
        by price, then walked in order, starting a new cluster whenever the
        next point falls outside tolerance of the current cluster's
        running average price.
        """
        if not swing_points:
            return []

        ordered = sorted(swing_points, key=lambda s: s.price)
        clusters: list[list[SwingPoint]] = [[ordered[0]]]

        for point in ordered[1:]:
            current_cluster = clusters[-1]
            cluster_avg = sum(p.price for p in current_cluster) / len(current_cluster)
            relative_diff = abs(point.price - cluster_avg) / cluster_avg if cluster_avg else float("inf")

            if relative_diff <= self.equal_tolerance:
                current_cluster.append(point)
            else:
                clusters.append([point])

        pools: list[LiquidityPool] = []
        for cluster in clusters:
            avg_price = sum(p.price for p in cluster) / len(cluster)
            pools.append(
                LiquidityPool(
                    price=avg_price,
                    liquidity_type=liquidity_type,
                    swing_points=tuple(cluster),
                )
            )
        return pools
