"""
Deterministic first approved paper-loop orchestration (CANONICAL #031).

Traverses integration gates → approval validity → ``submit_paper_adapter`` → persistence validation.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from modules.execution_adapter.coinbase_sandbox import (
    CoinbaseSandboxSubmitResult,
    CoinbaseSandboxVenueScenario,
    submit_coinbase_sandbox_adapter,
)
from modules.execution_adapter.chris_coinbase_paper import (
    CoinbasePaperStatusV1,
    ChrisCoinbasePaperSubmitResult,
    submit_chris_coinbase_paper_adapter,
)
from modules.execution_adapter.models import ExecutionAdapterOutcomeV1, ExecutionAdapterRequestV1
from modules.execution_adapter.paper import PaperSubmitResult, PaperVenueScenario, submit_paper_adapter
from modules.execution_adapter.validation import EXA_VENUE_006, EXA_VENUE_007, AdapterValidationResult
from modules.execution_artifacts.models import ExecutionIntentV1, SignalArtifactV1
from modules.paper_loop.models import PaperLoopExecutionIntentLinkV1, PaperLoopOutcomePersistenceLinkV1, PaperLoopSignalApprovalLinkV1
from modules.paper_loop.outcome_store_sqlite import write_paper_loop_outcome
from modules.paper_loop.validation import (
    LOOP_APPROVAL_004,
    LOOP_HASH_003,
    LOOP_LINK_001,
    LOOP_PAPER_005,
    LOOP_REPLAY_008,
    LOOP_SCOPE_002,
    build_persistence_link_from_adapter_outcome,
    map_adapter_failure_to_loop_paper_reason,
    validate_approval_validity,
    validate_loop_replay_stability,
    validate_outcome_persistence_link_integrity,
    validate_pre_paper_integration,
)


@dataclass(frozen=True)
class PaperLoopOrchestrationResult:
    ok: bool
    loop_reason_code: str
    reason: str
    adapter_reason_code: str
    adapter_outcome: ExecutionAdapterOutcomeV1 | None
    persistence_link: PaperLoopOutcomePersistenceLinkV1 | None


def _adapter_fail_to_loop(ar: AdapterValidationResult) -> tuple[str, str]:
    if ar.reason_code == "EXA-REPLAY-008":
        return LOOP_REPLAY_008, ar.reason
    if ar.reason_code in (EXA_VENUE_006, EXA_VENUE_007):
        return LOOP_PAPER_005, ar.reason
    if ar.reason_code == "EXA-EXP-002":
        return LOOP_APPROVAL_004, ar.reason
    if ar.reason_code == "EXA-HASH-004":
        return LOOP_HASH_003, ar.reason
    if ar.reason_code == "EXA-SCOPE-003":
        return LOOP_SCOPE_002, ar.reason
    if ar.reason_code in ("EXA-BIND-001", "EXA-IDEMP-005"):
        return LOOP_LINK_001, ar.reason
    return ar.reason_code, ar.reason


def run_first_approved_paper_loop(
    approval: PaperLoopSignalApprovalLinkV1,
    intent_link: PaperLoopExecutionIntentLinkV1,
    intent: ExecutionIntentV1,
    adapter_req: ExecutionAdapterRequestV1,
    *,
    market_snapshot_id: str,
    signal: SignalArtifactV1 | None,
    now_utc: datetime,
    venue_name: str,
    idempotency_registry: dict[tuple[str, str, str], str],
    execution_id: str,
    paper_scenario: PaperVenueScenario,
    outcome_id: str,
    venue_order_id: str,
    submitted_at_utc: str,
    metric_event_id: str,
    failure_event_id: Optional[str],
    audit_event_id: str,
    adapter_lane: str = "paper",
    coinbase_scenario: CoinbaseSandboxVenueScenario | None = None,
    fill_mapping: Callable[[ExecutionAdapterOutcomeV1, ExecutionAdapterRequestV1, ExecutionIntentV1], tuple[str, str, str]]
    | None = None,
    outcome_store_conn: sqlite3.Connection | None = None,
    chris_coinbase_status: CoinbasePaperStatusV1 | None = None,
) -> PaperLoopOrchestrationResult:
    """
    Single deterministic path: integration gates → approval window → paper adapter → persistence + replay.

    ``fill_mapping`` returns (filled_quantity, avg_fill_price, fees_total) for persistence; default uses intent quantity and limit price.

    If ``outcome_store_conn`` is set, a successful persistence link is written to the durable SQLite
    store (CANONICAL #032); a store rejection fails the loop with the store's reason code.

    ``adapter_lane``:
    - ``paper`` — ``submit_paper_adapter`` with ``venue_name`` (default).
    - ``coinbase_sandbox`` — Billy-scoped ``submit_coinbase_sandbox_adapter``; ``coinbase_scenario`` defaults to ACCEPT.
    - ``chris_coinbase_paper_v1`` — Chris-scoped ``submit_chris_coinbase_paper_adapter``.
    """
    ig = validate_pre_paper_integration(
        approval,
        intent_link,
        intent,
        adapter_req,
        market_snapshot_id=market_snapshot_id,
        signal=signal,
    )
    if not ig.ok:
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=ig.reason_code,
            reason=ig.reason,
            adapter_reason_code="",
            adapter_outcome=None,
            persistence_link=None,
        )

    ag = validate_approval_validity(approval, now_utc=now_utc)
    if not ag.ok:
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=LOOP_APPROVAL_004,
            reason=ag.reason,
            adapter_reason_code="",
            adapter_outcome=None,
            persistence_link=None,
        )

    if adapter_lane == "coinbase_sandbox":
        cs = coinbase_scenario if coinbase_scenario is not None else CoinbaseSandboxVenueScenario.ACCEPT
        ps: PaperSubmitResult | CoinbaseSandboxSubmitResult | ChrisCoinbasePaperSubmitResult = submit_coinbase_sandbox_adapter(
            adapter_req,
            intent,
            now_utc=now_utc,
            idempotency_registry=idempotency_registry,
            scenario=cs,
            outcome_id=outcome_id,
            venue_order_id=venue_order_id,
            submitted_at_utc=submitted_at_utc,
        )
    elif adapter_lane == "paper":
        ps = submit_paper_adapter(
            adapter_req,
            intent,
            now_utc=now_utc,
            venue_name=venue_name,
            idempotency_registry=idempotency_registry,
            scenario=paper_scenario,
            outcome_id=outcome_id,
            venue_order_id=venue_order_id,
            submitted_at_utc=submitted_at_utc,
        )
    elif adapter_lane == "chris_coinbase_paper_v1":
        ps = submit_chris_coinbase_paper_adapter(
            adapter_req,
            intent,
            now_utc=now_utc,
            idempotency_registry=idempotency_registry,
            scenario=paper_scenario,
            outcome_id=outcome_id,
            venue_order_id=venue_order_id,
            submitted_at_utc=submitted_at_utc,
            coinbase_status=chris_coinbase_status,
        )
    else:
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=LOOP_LINK_001,
            reason=f"unknown adapter_lane {adapter_lane!r}",
            adapter_reason_code="",
            adapter_outcome=None,
            persistence_link=None,
        )

    if not ps.result.ok or ps.outcome is None:
        if map_adapter_failure_to_loop_paper_reason(ps.result.reason_code):
            return PaperLoopOrchestrationResult(
                ok=False,
                loop_reason_code=LOOP_PAPER_005,
                reason=ps.result.reason,
                adapter_reason_code=ps.result.reason_code,
                adapter_outcome=None,
                persistence_link=None,
            )
        lr, msg = _adapter_fail_to_loop(ps.result)
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=lr,
            reason=msg,
            adapter_reason_code=ps.result.reason_code,
            adapter_outcome=None,
            persistence_link=None,
        )

    out = ps.outcome
    # Deterministic adapter failure paths are structurally valid but not an accepted loop completion.
    if out.failure_code or out.venue_status in ("venue_unavailable", "venue_reject"):
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=LOOP_PAPER_005,
            reason=out.failure_reason or "paper adapter failure path",
            adapter_reason_code=out.failure_code or "",
            adapter_outcome=out,
            persistence_link=None,
        )

    def _default_fill(
        o: ExecutionAdapterOutcomeV1, rq: ExecutionAdapterRequestV1, it: ExecutionIntentV1
    ) -> tuple[str, str, str]:
        if o.failure_code:
            return "0", "0", "0"
        return it.quantity.strip(), rq.limit_price.strip() if rq.limit_price else "0", "0"

    fm = fill_mapping if fill_mapping is not None else _default_fill
    fq, ap, fee = fm(out, adapter_req, intent)

    persist = build_persistence_link_from_adapter_outcome(
        out,
        execution_id=execution_id,
        wallet_context=intent.wallet_context,
        interaction_path=intent.interaction_path,
        filled_quantity=fq,
        avg_fill_price=ap,
        fees_total=fee,
        metric_event_id=metric_event_id,
        failure_event_id=failure_event_id if out.failure_code else None,
        audit_event_id=audit_event_id,
    )

    pv = validate_outcome_persistence_link_integrity(persist, adapter_out=out, approval=approval, intent=intent)
    if not pv.ok:
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=pv.reason_code,
            reason=pv.reason,
            adapter_reason_code="",
            adapter_outcome=out,
            persistence_link=None,
        )

    rv = validate_loop_replay_stability(persist)
    if not rv.ok:
        return PaperLoopOrchestrationResult(
            ok=False,
            loop_reason_code=LOOP_REPLAY_008,
            reason=rv.reason,
            adapter_reason_code="",
            adapter_outcome=out,
            persistence_link=None,
        )

    if outcome_store_conn is not None:
        wr = write_paper_loop_outcome(outcome_store_conn, persist)
        if not wr.ok:
            return PaperLoopOrchestrationResult(
                ok=False,
                loop_reason_code=wr.reason_code,
                reason=wr.reason,
                adapter_reason_code="",
                adapter_outcome=out,
                persistence_link=None,
            )

    return PaperLoopOrchestrationResult(
        ok=True,
        loop_reason_code="",
        reason="",
        adapter_reason_code="",
        adapter_outcome=out,
        persistence_link=persist,
    )
