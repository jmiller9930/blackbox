"""
Chris-scoped execution handoff for Coinbase paper lane (CANONICAL #137 draft).
"""

from __future__ import annotations

from modules.execution_adapter.models import ExecutionAdapterRequestV1
from modules.execution_adapter.validation import EXA_SCOPE_003, AdapterValidationResult, _ok
from modules.execution_artifacts.models import ExecutionIntentV1

# Locked lane token for Chris-owned Coinbase paper adapter path.
CHRIS_COINBASE_PAPER_LANE = "chris_coinbase_paper_v1"


def validate_chris_coinbase_paper_handoff(
    req: ExecutionAdapterRequestV1,
    intent: ExecutionIntentV1,
) -> AdapterValidationResult:
    """
    Fail closed unless request+intent are both pinned to Chris Coinbase paper lane token.
    """
    if req.interaction_path != CHRIS_COINBASE_PAPER_LANE:
        return AdapterValidationResult(
            ok=False,
            reason_code=EXA_SCOPE_003,
            reason="ExecutionAdapterRequestV1.interaction_path must be chris_coinbase_paper_v1 for Chris paper lane",
        )
    if intent.interaction_path != CHRIS_COINBASE_PAPER_LANE:
        return AdapterValidationResult(
            ok=False,
            reason_code=EXA_SCOPE_003,
            reason="ExecutionIntentV1.interaction_path must be chris_coinbase_paper_v1 for Chris paper lane",
        )
    if req.interaction_path != intent.interaction_path:
        return AdapterValidationResult(
            ok=False,
            reason_code=EXA_SCOPE_003,
            reason="interaction_path mismatch between request and intent for Chris paper lane",
        )
    return _ok()

