"""
partner/workflow.py

Partner Engine workflow orchestration.

`PartnerWorkflow` is the single public entry point for the Partner Engine,
wiring the steps together exactly as specified:

    Input (PartnerContext) -> Validator -> Decision Engine -> Decision

This module contains no business rules of its own -- it only sequences the
`Validator` and `DecisionEngine`, keeping orchestration separate from rule
logic so either can be modified or tested independently.
"""

from __future__ import annotations

from partner.context import PartnerContext
from partner.decision import Decision, DecisionEngine
from partner.models import ExecutionTimeframe
from partner.validator import Validator


class PartnerWorkflow:
    """
    Runs a `PartnerContext` through validation and decision-making.

    Composes a `Validator` and a `DecisionEngine` internally so callers
    only need to interact with this single, modular entry point.
    """

    def __init__(
        self,
        validator: Validator | None = None,
        decision_engine: DecisionEngine | None = None,
        required_execution_timeframe: ExecutionTimeframe = ExecutionTimeframe.H2,
    ) -> None:
        """
        Args:
            validator: Optional pre-configured `Validator`. If omitted, a
                default `Validator` is constructed using
                `required_execution_timeframe`.
            decision_engine: Optional pre-configured `DecisionEngine`. If
                omitted, a default `DecisionEngine` is constructed.
            required_execution_timeframe: Execution timeframe enforced by
                the default validator. Ignored if `validator` is provided
                explicitly.
        """
        self.validator = validator or Validator(required_execution_timeframe=required_execution_timeframe)
        self.decision_engine = decision_engine or DecisionEngine()

    def run(self, context: PartnerContext) -> Decision:
        """
        Execute the full Partner Engine workflow for a single context.

        Args:
            context: The `PartnerContext` to evaluate.

        Returns:
            The resulting `Decision` object.
        """
        validation = self.validator.validate(context)
        return self.decision_engine.decide(context, validation)
