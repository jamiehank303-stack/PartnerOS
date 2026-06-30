"""
partner/validator.py

Input validation for the Partner Engine.

The Validator checks that a `PartnerContext` is internally consistent and
complete enough to be reasoned over by the Decision Engine. It enforces
structural business rules only (e.g. FTC cannot be CONFIRMED or PENDING if
no sweep occurred; the engine is configured for a specific execution
timeframe) -- it never determines trade direction, entries, stops,
targets, or confidence. That is strictly the Decision Engine's
responsibility, keeping validation and decision-making as independently
testable concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from partner.context import PartnerContext
from partner.models import ExecutionTimeframe, FTCStatus, SweepStatus


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """
    Outcome of validating a `PartnerContext`.

    Attributes:
        is_valid: True if the context passed every validation rule.
        errors: Human-readable descriptions of every rule that failed.
            Empty when `is_valid` is True.
    """

    is_valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)


class Validator:
    """
    Validates a `PartnerContext` for internal structural consistency.

    Each rule is implemented as its own private method returning an
    optional error string, so new rules can be added independently without
    touching existing ones.
    """

    def __init__(self, required_execution_timeframe: ExecutionTimeframe = ExecutionTimeframe.H2) -> None:
        """
        Args:
            required_execution_timeframe: The execution timeframe this
                engine instance is configured to operate on. Defaults to
                2H per the Partner Engine's workflow specification.
        """
        self.required_execution_timeframe = required_execution_timeframe

    def validate(self, context: PartnerContext) -> ValidationResult:
        """
        Run every validation rule against `context`.

        Args:
            context: The `PartnerContext` to validate.

        Returns:
            A `ValidationResult` aggregating every rule violation found.
        """
        errors: list[str] = []

        for rule in (
            self._check_execution_timeframe,
            self._check_ftc_requires_sweep,
            self._check_sweep_requires_ftc_status,
        ):
            error = rule(context)
            if error is not None:
                errors.append(error)

        return ValidationResult(is_valid=not errors, errors=tuple(errors))

    def _check_execution_timeframe(self, context: PartnerContext) -> str | None:
        """The Partner Engine is configured to operate on a single, fixed execution timeframe."""
        if context.execution_timeframe != self.required_execution_timeframe:
            return (
                f"Execution timeframe {context.execution_timeframe.value} does not match "
                f"required {self.required_execution_timeframe.value}."
            )
        return None

    @staticmethod
    def _check_ftc_requires_sweep(context: PartnerContext) -> str | None:
        """FTC cannot be CONFIRMED or PENDING if no liquidity sweep has occurred."""
        if context.sweep_status == SweepStatus.NOT_SWEPT and context.ftc_status != FTCStatus.NOT_APPLICABLE:
            return "FTC status cannot be CONFIRMED or PENDING when no sweep has occurred."
        return None

    @staticmethod
    def _check_sweep_requires_ftc_status(context: PartnerContext) -> str | None:
        """A confirmed sweep must carry an applicable FTC status (CONFIRMED or PENDING), not NOT_APPLICABLE."""
        if context.sweep_status != SweepStatus.NOT_SWEPT and context.ftc_status == FTCStatus.NOT_APPLICABLE:
            return "A sweep has occurred but FTC status was left as NOT_APPLICABLE."
        return None
