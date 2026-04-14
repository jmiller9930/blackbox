"""
learning_ledger.py

Purpose:
Store completed RenaissanceV4 trade outcomes in memory during replay and expose summary metrics.

Usage:
Instantiated by replay logic to accumulate outcomes and compute portfolio-level learning metrics.

Version:
v1.0

Change History:
- v1.0 Initial Phase 7 implementation.
"""

from __future__ import annotations

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.core.performance_metrics import compute_summary_metrics


class LearningLedger:
    """
    In-memory outcome ledger for replay-time learning analysis.
    """

    def __init__(self) -> None:
        self.outcomes: list[OutcomeRecord] = []

    def record_outcome(self, outcome: OutcomeRecord) -> None:
        """
        Append a completed outcome record to the ledger and print a visible confirmation.
        """
        self.outcomes.append(outcome)
        print(
            f"[learning_ledger] Recorded outcome trade_id={outcome.trade_id} "
            f"pnl={outcome.pnl:.4f} exit_reason={outcome.exit_reason}"
        )

    def summary(self) -> dict:
        """
        Return current aggregate metrics across all recorded outcomes.
        """
        metrics = compute_summary_metrics(self.outcomes)
        print(f"[learning_ledger] Summary metrics: {metrics}")
        return metrics
