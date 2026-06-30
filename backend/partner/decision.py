"""
partner/decision.py

Decision Engine and Decision Object for the Partner Engine.

The `DecisionEngine` applies the Partner Engine's pure business rules to a
validated `PartnerContext` and produces a single `Decision` -- the
authoritative structured output of the workflow. Every rule here is
deterministic price-structure logic (bias alignment, liquidity, sweep,
FTC, acceptance, premium/discount positioning); no indicators and no AI
are used anywhere in this evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

from partner.context import PartnerContext
from partner.models import (
    AcceptanceStatus,
    BiasDirection,
    ConfidenceLevel,
    EntryType,
    FTCStatus,
    LiquidityStatus,
    PriceZone,
    StopLocation,
    SweepStatus,
    TargetLocation,
    TradeDirection,
)
from partner.validator import ValidationResult


@dataclass(frozen=True, slots=True)
class Decision:
    """
    The final structured output of the Partner Engine workflow.

    Attributes:
        trade_allowed: Whether the current context supports taking a trade.
        direction: The resolved trade direction (LONG, SHORT, or NONE).
        reason: Human-readable explanation of why this decision was reached.
        entry_type: The structural justification category for the entry.
        stop_location: Structural reference point for stop placement.
        target_location: Structural reference point for target placement.
        confidence: Rule-based confidence rating (confluence count, not a
            statistical or AI-derived score).
    """

    trade_allowed: bool
    direction: TradeDirection
    reason: str
    entry_type: EntryType
    stop_location: StopLocation
    target_location: TargetLocation
    confidence: ConfidenceLevel


class DecisionEngine:
    """
    Produces a `Decision` from a validated `PartnerContext`.

    The engine evaluates two independent setup patterns:
      - A liquidity-sweep reversal: weekly/daily bias agree, a sweep has
        occurred opposite that bias, and FTC has confirmed the failure to
        continue against the bias.
      - An acceptance continuation: weekly/daily bias agree, and price has
        been accepted beyond a level in the direction of that bias while
        still favorably positioned within the dealing range.

    If neither pattern is satisfied, no trade is allowed. This module makes
    no assumption about how the input statuses were derived -- it only
    reasons over the `PartnerContext` it is given.
    """

    def decide(self, context: PartnerContext, validation: ValidationResult) -> Decision:
        """
        Evaluate `context` and produce a final `Decision`.

        Args:
            context: The `PartnerContext` to evaluate.
            validation: The `ValidationResult` produced for `context`. If
                invalid, no trade is permitted regardless of the context's
                contents.

        Returns:
            A fully populated `Decision` object.
        """
        if not validation.is_valid:
            return self._no_trade(reason=f"Context failed validation: {'; '.join(validation.errors)}")

        bias = self._resolve_aligned_bias(context.weekly_bias, context.daily_bias)
        if bias is None:
            return self._no_trade(reason="Weekly and daily bias are not aligned.")

        sweep_decision = self._evaluate_sweep_reversal(context, bias)
        if sweep_decision is not None:
            return sweep_decision

        acceptance_decision = self._evaluate_acceptance_continuation(context, bias)
        if acceptance_decision is not None:
            return acceptance_decision

        return self._no_trade(reason="No qualifying sweep-reversal or acceptance-continuation setup present.")

    # --- Setup evaluators -----------------------------------------------------

    def _evaluate_sweep_reversal(self, context: PartnerContext, bias: BiasDirection) -> Decision | None:
        """
        Evaluate the liquidity-sweep reversal pattern.

        A bullish bias looks for a sell-side sweep (downside liquidity
        grab) confirmed by FTC, with buy-side liquidity remaining as a
        target. A bearish bias is the mirror image.
        """
        if context.ftc_status != FTCStatus.CONFIRMED:
            return None

        if bias == BiasDirection.BULLISH and context.sweep_status == SweepStatus.SELL_SIDE_SWEPT:
            target = self._resolve_target(context, expected=LiquidityStatus.BUY_SIDE_AVAILABLE)
            if target is None:
                return None
            return Decision(
                trade_allowed=True,
                direction=TradeDirection.LONG,
                reason=(
                    "Weekly and daily bias bullish; sell-side liquidity swept and FTC confirmed, "
                    "with buy-side liquidity remaining as a target."
                ),
                entry_type=EntryType.LIQUIDITY_SWEEP_REVERSAL,
                stop_location=StopLocation.BEYOND_SWEEP_EXTREME,
                target_location=target,
                confidence=self._score_confidence(context, bias),
            )

        if bias == BiasDirection.BEARISH and context.sweep_status == SweepStatus.BUY_SIDE_SWEPT:
            target = self._resolve_target(context, expected=LiquidityStatus.SELL_SIDE_AVAILABLE)
            if target is None:
                return None
            return Decision(
                trade_allowed=True,
                direction=TradeDirection.SHORT,
                reason=(
                    "Weekly and daily bias bearish; buy-side liquidity swept and FTC confirmed, "
                    "with sell-side liquidity remaining as a target."
                ),
                entry_type=EntryType.LIQUIDITY_SWEEP_REVERSAL,
                stop_location=StopLocation.BEYOND_SWEEP_EXTREME,
                target_location=target,
                confidence=self._score_confidence(context, bias),
            )

        return None

    def _evaluate_acceptance_continuation(self, context: PartnerContext, bias: BiasDirection) -> Decision | None:
        """
        Evaluate the acceptance-continuation pattern.

        A bullish bias looks for acceptance above a key level while price
        still sits in discount (favorable continuation positioning). A
        bearish bias looks for acceptance below a key level while price
        still sits in premium.
        """
        if bias == BiasDirection.BULLISH:
            if (
                context.acceptance_status == AcceptanceStatus.ACCEPTED_ABOVE
                and context.premium_discount == PriceZone.DISCOUNT
            ):
                return Decision(
                    trade_allowed=True,
                    direction=TradeDirection.LONG,
                    reason="Weekly and daily bias bullish; price accepted above key level while still in discount.",
                    entry_type=EntryType.ACCEPTANCE_CONTINUATION,
                    stop_location=StopLocation.BEYOND_ACCEPTANCE_LEVEL,
                    target_location=TargetLocation.PREMIUM_ZONE,
                    confidence=self._score_confidence(context, bias),
                )
            return None

        if bias == BiasDirection.BEARISH:
            if (
                context.acceptance_status == AcceptanceStatus.ACCEPTED_BELOW
                and context.premium_discount == PriceZone.PREMIUM
            ):
                return Decision(
                    trade_allowed=True,
                    direction=TradeDirection.SHORT,
                    reason="Weekly and daily bias bearish; price accepted below key level while still in premium.",
                    entry_type=EntryType.ACCEPTANCE_CONTINUATION,
                    stop_location=StopLocation.BEYOND_ACCEPTANCE_LEVEL,
                    target_location=TargetLocation.DISCOUNT_ZONE,
                    confidence=self._score_confidence(context, bias),
                )
            return None

        return None

    # --- Helpers ----------------------------------------------------------

    @staticmethod
    def _resolve_aligned_bias(weekly: BiasDirection, daily: BiasDirection) -> BiasDirection | None:
        """Return the shared bias if weekly and daily agree and are directional, else None."""
        if weekly == daily and weekly in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            return weekly
        return None

    @staticmethod
    def _resolve_target(context: PartnerContext, expected: LiquidityStatus) -> TargetLocation | None:
        """Resolve a target location if the expected liquidity remains available."""
        if context.liquidity_status in (expected, LiquidityStatus.BOTH_AVAILABLE):
            return TargetLocation.OPPOSING_LIQUIDITY_POOL
        return None

    @staticmethod
    def _score_confidence(context: PartnerContext, bias: BiasDirection) -> ConfidenceLevel:
        """
        Rate confidence by counting confirming structural factors.

        This is a simple, transparent confluence count -- not a
        statistical or machine-learned score -- consistent with the "no
        AI, no indicators" constraint on this engine.
        """
        score = 0

        if bias in (BiasDirection.BULLISH, BiasDirection.BEARISH):
            score += 1
        if context.ftc_status == FTCStatus.CONFIRMED:
            score += 1
        if context.acceptance_status in (AcceptanceStatus.ACCEPTED_ABOVE, AcceptanceStatus.ACCEPTED_BELOW):
            score += 1
        if context.premium_discount != PriceZone.EQUILIBRIUM:
            score += 1
        if context.liquidity_status != LiquidityStatus.NONE_AVAILABLE:
            score += 1

        if score >= 4:
            return ConfidenceLevel.HIGH
        if score >= 2:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    @staticmethod
    def _no_trade(reason: str) -> Decision:
        """Construct a standard "no trade" `Decision` with the given reason."""
        return Decision(
            trade_allowed=False,
            direction=TradeDirection.NONE,
            reason=reason,
            entry_type=EntryType.NONE,
            stop_location=StopLocation.NONE,
            target_location=TargetLocation.NONE,
            confidence=ConfidenceLevel.NONE,
        )
