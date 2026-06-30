"""
partner/context.py

Partner Engine input context.

`PartnerContext` is the single, immutable bundle of pre-computed status
inputs the Partner Engine workflow consumes, exactly as laid out in the
workflow specification: weekly bias, daily bias, liquidity status, sweep
status, FTC status, acceptance status, premium/discount positioning, and
the execution timeframe. This module has no knowledge of how these
statuses were derived -- it only models the shape of the data the
Validator and Decision Engine operate on, keeping the Partner Engine fully
decoupled from any upstream data source.
"""

from __future__ import annotations

from dataclasses import dataclass

from partner.models import (
    AcceptanceStatus,
    BiasDirection,
    ExecutionTimeframe,
    FTCStatus,
    LiquidityStatus,
    PriceZone,
    SweepStatus,
)


@dataclass(frozen=True, slots=True)
class PartnerContext:
    """
    Immutable snapshot of all structural inputs for a single decision pass.

    Attributes:
        weekly_bias: Directional bias derived from weekly structure.
        daily_bias: Directional bias derived from daily structure.
        liquidity_status: Which side(s) of resting liquidity remain untapped.
        sweep_status: Whether a liquidity sweep has occurred, and where.
        ftc_status: Failure-to-continue confirmation state following a sweep.
        acceptance_status: Whether price has been accepted beyond a key level.
        premium_discount: Current price's position within the dealing range.
        execution_timeframe: The timeframe entry execution is evaluated on.
    """

    weekly_bias: BiasDirection
    daily_bias: BiasDirection
    liquidity_status: LiquidityStatus
    sweep_status: SweepStatus
    ftc_status: FTCStatus
    acceptance_status: AcceptanceStatus
    premium_discount: PriceZone
    execution_timeframe: ExecutionTimeframe
