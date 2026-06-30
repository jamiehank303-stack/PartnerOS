"""
partner/models.py

Shared domain enums for the PartnerOS Partner Engine.

These types describe the *status* of each structural input the Partner
Engine reasons over (bias, liquidity, sweep, FTC, acceptance, premium/
discount, execution timeframe). They are deliberately decoupled from any
upstream detector output types -- the Partner Engine consumes
pre-summarized status flags, not raw candle/swing/sweep objects, keeping
this layer independent and reusable regardless of how those statuses were
produced.

No indicators (RSI, MACD, EMA, or any other) and no AI/ML are used
anywhere in this package -- every type and rule here is plain,
deterministic business logic operating on price-structure concepts only.
"""

from __future__ import annotations

from enum import Enum


class BiasDirection(str, Enum):
    """Directional bias for a given timeframe (e.g. weekly, daily)."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class LiquidityStatus(str, Enum):
    """Availability of untapped resting liquidity relevant to the current setup."""

    BUY_SIDE_AVAILABLE = "BUY_SIDE_AVAILABLE"
    SELL_SIDE_AVAILABLE = "SELL_SIDE_AVAILABLE"
    BOTH_AVAILABLE = "BOTH_AVAILABLE"
    NONE_AVAILABLE = "NONE_AVAILABLE"


class SweepStatus(str, Enum):
    """Whether a liquidity sweep has occurred, and on which side."""

    BUY_SIDE_SWEPT = "BUY_SIDE_SWEPT"
    SELL_SIDE_SWEPT = "SELL_SIDE_SWEPT"
    NOT_SWEPT = "NOT_SWEPT"


class FTCStatus(str, Enum):
    """Failure-to-continue confirmation state following a sweep."""

    CONFIRMED = "CONFIRMED"
    PENDING = "PENDING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AcceptanceStatus(str, Enum):
    """Whether price has been structurally accepted beyond a key level."""

    ACCEPTED_ABOVE = "ACCEPTED_ABOVE"
    ACCEPTED_BELOW = "ACCEPTED_BELOW"
    NOT_ACCEPTED = "NOT_ACCEPTED"


class PriceZone(str, Enum):
    """Premium / discount / equilibrium positioning within the dealing range."""

    PREMIUM = "PREMIUM"
    DISCOUNT = "DISCOUNT"
    EQUILIBRIUM = "EQUILIBRIUM"


class ExecutionTimeframe(str, Enum):
    """Timeframe on which entry execution is evaluated."""

    M15 = "M15"
    H1 = "H1"
    H2 = "H2"
    H4 = "H4"
    D1 = "D1"


class TradeDirection(str, Enum):
    """Resolved trade direction produced by the Decision Engine."""

    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class EntryType(str, Enum):
    """Structural justification category for an entry."""

    LIQUIDITY_SWEEP_REVERSAL = "LIQUIDITY_SWEEP_REVERSAL"
    ACCEPTANCE_CONTINUATION = "ACCEPTANCE_CONTINUATION"
    NONE = "NONE"


class StopLocation(str, Enum):
    """Structural reference point for stop placement."""

    BEYOND_SWEEP_EXTREME = "BEYOND_SWEEP_EXTREME"
    BEYOND_ACCEPTANCE_LEVEL = "BEYOND_ACCEPTANCE_LEVEL"
    NONE = "NONE"


class TargetLocation(str, Enum):
    """Structural reference point for target placement."""

    OPPOSING_LIQUIDITY_POOL = "OPPOSING_LIQUIDITY_POOL"
    PREMIUM_ZONE = "PREMIUM_ZONE"
    DISCOUNT_ZONE = "DISCOUNT_ZONE"
    NONE = "NONE"


class ConfidenceLevel(str, Enum):
    """Rule-based confidence rating for a decision (confluence count, not a statistical score)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"
