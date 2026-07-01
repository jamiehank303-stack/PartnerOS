"""
Liquidity analysis primitives for PartnerOS's setup verification engine.

Scope
-----
This module is strictly limited to *liquidity analysis*: identifying
swing points and clusters of price levels that are commonly referred to
as "liquidity" (resting stop/limit interest around equal highs/lows,
swing highs/lows, etc.) across discretionary and institutional trading
literature.

This module deliberately does NOT:
  - place, modify, or manage trades (see backend/ctrader/execution.py)
  - read or touch account, balance, margin, or risk state
  - compute PnL
  - talk to any broker API, or use any broker-specific data shape

Why only swing points + equal-level clustering
-----------------------------------------------
"Liquidity" is a widely used but not formally standardized concept --
its precise definition varies by trading methodology (ICT, Smart Money
Concepts, classical technical analysis, etc.). To avoid encoding any
one methodology's judgment calls as if they were objective market
facts, this module implements only the parts of "liquidity analysis"
that have a single, mechanical, methodology-agnostic definition:

  - swing high / swing low detection: a standard fractal definition
    used broadly across technical analysis, independent of any one
    liquidity-focused strategy.
  - clustering of same-type swing points into "equal highs" / "equal
    lows" using a tolerance that the CALLER supplies (never hardcoded
    here, since the correct tolerance is instrument- and
    strategy-specific).

Anything requiring a subjective judgment call -- what counts as a
liquidity "sweep" vs. a genuine breakout, how many touches make a
level "significant", wick-only vs. close-through penetration, higher-
timeframe vs. lower-timeframe weighting, session-based liquidity, etc.
-- is explicitly NOT implemented. See the TODO block at the bottom.
Later, explicitly-specified setup validators are expected to supply
their own rules on top of the primitives here, rather than this module
silently picking one on their behalf.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

__all__ = [
    "SwingType",
    "Bar",
    "SwingPoint",
    "LiquidityCluster",
    "find_swing_points",
    "cluster_equal_levels",
]


class SwingType(Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class Bar:
    """A single, broker-agnostic OHLC price bar.

    Deliberately independent of any exchange/broker-specific candle
    representation (e.g. cTrader's relative-price-scaled `Candle` in
    backend/ctrader/connector.py, which stores raw protocol integers
    like `low_raw` / `delta_open_raw` that must first be converted to
    real prices). Callers are responsible for converting broker data
    into this plain shape before calling into this module -- that
    conversion logic belongs with the broker integration, not here,
    so this module stays reusable across brokers and data sources.

    `index` must be the bar's position within the sequence passed to
    find_swing_points (0-based, strictly increasing) so swing
    detection can look at fixed-width neighbor windows.
    """

    index: int
    high: float
    low: float
    close: float
    timestamp: Optional[int] = None  # caller-defined epoch millis, or None


@dataclass(frozen=True)
class SwingPoint:
    bar_index: int
    price: float
    swing_type: SwingType
    timestamp: Optional[int] = None


@dataclass(frozen=True)
class LiquidityCluster:
    """A group of same-type swing points whose prices fall within a
    caller-supplied tolerance of each other -- commonly referred to as
    an "equal highs" or "equal lows" liquidity pool.
    """

    swing_type: SwingType
    price_level: float  # mean price of all members
    members: List[SwingPoint]

    @property
    def touch_count(self) -> int:
        return len(self.members)


def find_swing_points(bars: Sequence[Bar], lookback: int = 2) -> List[SwingPoint]:
    """
    Identify swing highs and swing lows using a symmetric fractal
    definition: bar `i` is a swing high if its high is strictly
    greater than the high of every other bar within `lookback` bars on
    both sides; a swing low is the mirror case using lows.

    This is a standard, methodology-agnostic definition used broadly
    in technical analysis (it does not encode any one liquidity-
    focused trading strategy), so it is implemented directly rather
    than left as a TODO.

    `lookback` must be supplied by the caller. The default of 2 is
    only a common baseline for structural clarity -- it is not a claim
    about what any particular strategy or timeframe should use, and
    callers verifying a specific setup should pass an explicit value.

    Bars within `lookback` of either end of the sequence cannot be
    evaluated (there aren't enough neighbors on one side) and are
    skipped, matching standard fractal-detection behavior.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")

    swings: List[SwingPoint] = []
    n = len(bars)

    for i in range(n):
        if i - lookback < 0 or i + lookback >= n:
            continue

        this_bar = bars[i]
        neighbors = bars[i - lookback : i] + bars[i + 1 : i + lookback + 1]

        if all(this_bar.high > other.high for other in neighbors):
            swings.append(
                SwingPoint(this_bar.index, this_bar.high, SwingType.HIGH, this_bar.timestamp)
            )

        if all(this_bar.low < other.low for other in neighbors):
            swings.append(
                SwingPoint(this_bar.index, this_bar.low, SwingType.LOW, this_bar.timestamp)
            )

    return swings


def cluster_equal_levels(
    swings: Sequence[SwingPoint],
    tolerance: float,
    swing_type: Optional[SwingType] = None,
) -> List[LiquidityCluster]:
    """
    Group swing points of the same type into clusters where every
    member's price is within `tolerance` of the cluster's running mean
    price -- commonly referred to as "equal highs" / "equal lows"
    liquidity. Clusters of size 1 (i.e. no actual "equal" match) are
    not returned.

    `tolerance` is a plain absolute price distance and is REQUIRED
    from the caller; this module never picks a tolerance on the
    caller's behalf. The correct tolerance depends on the instrument's
    price scale (see `SymbolInfo.digits` / `pip_position` returned by
    `CTraderConnector.get_symbol_info()` in backend/ctrader/connector.py)
    and on strategy-specific sensitivity, both of which are outside
    this module's scope.

    If `swing_type` is given, only swings of that type are clustered;
    otherwise highs and lows are clustered separately (a high can
    never be grouped with a low).
    """
    if tolerance <= 0:
        raise ValueError("tolerance must be > 0")

    types_to_process = (
        [swing_type] if swing_type is not None else [SwingType.HIGH, SwingType.LOW]
    )

    clusters: List[LiquidityCluster] = []

    for target_type in types_to_process:
        ordered = sorted(
            (s for s in swings if s.swing_type == target_type),
            key=lambda s: s.price,
        )

        current: List[SwingPoint] = []
        for point in ordered:
            if not current:
                current = [point]
                continue

            running_mean = sum(m.price for m in current) / len(current)
            if abs(point.price - running_mean) <= tolerance:
                current.append(point)
            else:
                if len(current) > 1:
                    clusters.append(_build_cluster(target_type, current))
                current = [point]

        if len(current) > 1:
            clusters.append(_build_cluster(target_type, current))

    return clusters


def _build_cluster(swing_type: SwingType, members: List[SwingPoint]) -> LiquidityCluster:
    mean_price = sum(m.price for m in members) / len(members)
    return LiquidityCluster(swing_type=swing_type, price_level=mean_price, members=list(members))


# ---------------------------------------------------------------------
# Deliberately NOT implemented here.
#
# TODO: liquidity "sweep" / "stop hunt" / "grab" detection. Different
# methodologies define this differently -- e.g. wick-only penetration
# past a LiquidityCluster's price_level followed by a close back
# inside, vs. requiring a confirmed lower-timeframe reversal
# structure, vs. a minimum penetration distance, vs. volume/tick-based
# confirmation. Implementing any one of these silently would encode a
# specific trading methodology as if it were objective market
# structure. A validator with an explicit, documented definition
# should build this on top of find_swing_points()/cluster_equal_levels().
#
# TODO: relative significance / weighting of a LiquidityCluster (e.g.
# higher-timeframe swing points weighted above lower-timeframe ones,
# "old" vs. "fresh" liquidity, or how touch_count should affect
# confidence). This is a strategy-specific scoring model, not a
# defined market-structure fact, and is intentionally left to callers.
#
# TODO: session- or time-of-day-based liquidity concepts (e.g. Asian
# session range, daily/weekly opening liquidity). These require an
# explicit, externally-supplied session calendar and timezone
# convention that this broker-agnostic module has no basis to assume.
# ---------------------------------------------------------------------
