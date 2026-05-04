"""
FinQuant Unified Agent Lab — shared execution flow.

Used by the runner, the training cycle, and the test framework.

This is now the canonical place where:
  - the lifecycle is run with a learning store attached
  - falsification is applied to every step's pattern signature
  - new learning units are upserted on first observation
  - existing units are updated with confirmed/rejected/inconclusive verdicts
  - promotion is evaluated after each observation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def execute_case(
    *,
    case_path: str,
    config: dict[str, Any],
    output_dir: str,
    learning_store=None,
) -> dict[str, Any]:
    from case_loader import load_case
    from lifecycle_engine import LifecycleEngine
    from evaluation import evaluate_lifecycle
    from memory_store import MemoryStore
    from retrieval import retrieve_eligible
    from learning.falsification_engine import falsify_with_simulation
    from learning.promotion_engine import apply_promotion_if_needed

    case = load_case(case_path)
    store = MemoryStore(config=config, base_output_dir=output_dir)

    prior_records, retrieval_trace = retrieve_eligible(
        shared_store_path=config.get("memory_store_path"),
        case=case,
        config=config,
    )
    store.append_retrieval_trace(retrieval_trace)

    engine = LifecycleEngine(config=config, learning_store=learning_store)
    decisions = engine.run_case(case, prior_records=prior_records)
    store.append_decisions(decisions)

    evaluation = evaluate_lifecycle(case=case, decisions=decisions)
    record = store.write_learning_record(case=case, evaluation=evaluation)
    run_dir = store.get_run_dir()

    # ----------------------------------------------------------------
    # Falsify, accumulate, promote — BEFORE finalize so quality stats
    # are embedded into the record dict before it is written to JSONL.
    # ----------------------------------------------------------------

    learning_observations: list[dict[str, Any]] = []
    if learning_store is not None:
        for decision in decisions:
            sig = decision.get("pattern_signature_v1") or {}
            pattern_id = sig.get("pattern_id_v1")
            if not pattern_id:
                continue

            proposed_action = str(decision.get("action") or "NO_TRADE")
            unit = learning_store.upsert_unit(
                pattern_id=pattern_id,
                signature_components=sig.get("components_v1") or {},
                human_label=sig.get("human_label_v1", ""),
                proposed_action=proposed_action,
                hypothesis=str(decision.get("thesis_v1") or ""),
                expected_outcome=_default_expected(proposed_action),
                invalidation_condition=str(decision.get("invalidation_v1") or ""),
                scope_notes=f"case={case.get('case_id')} symbol={case.get('symbol')}",
            )

            verdict_info = falsify_with_simulation(
                proposed_action=proposed_action,
                case=case,
                horizon_bars=int(config.get("horizon_bars_v1") or 5),
            )

            updated_unit = learning_store.record_outcome(
                pattern_id=pattern_id,
                verdict=verdict_info["verdict_v1"],
                evidence_record_id=str(record.get("record_id") or ""),
                note=verdict_info["verdict_reason_v1"],
                pnl=float(verdict_info.get("pnl_v1") or 0.0),
                outcome_kind=str(verdict_info.get("outcome_kind_v1") or ""),
            )

            promo_thresholds = (
                config.get("promotion_thresholds_v1")
                or config.get("lab_promotion_thresholds_v1")
            )
            promotion = apply_promotion_if_needed(
                learning_store,
                pattern_id=pattern_id,
                recent_verdicts=updated_unit.get("recent_verdict_chain_v1"),
                thresholds=promo_thresholds,
            )

            # Embed pattern quality stats into the record dict BEFORE finalize.
            # Only update from decisions that have decided trades (wins+losses>0).
            # HOLD/EXIT decisions have 0 decided trades and would zero out win_rate
            # if we allowed them to overwrite a prior ENTER_LONG's stats.
            decided = int(updated_unit.get("wins_v1") or 0) + int(updated_unit.get("losses_v1") or 0)
            is_directional = proposed_action in ("ENTER_LONG", "ENTER_SHORT")
            prior_decided = int(record.get("pattern_win_decided_v1") or 0)
            if is_directional or decided > prior_decided:
                record["pattern_id_v1"] = pattern_id
                record["pattern_win_rate_v1"] = float(updated_unit.get("win_rate_v1") or 0.0)
                record["pattern_total_obs_v1"] = int(updated_unit.get("total_observations_v1") or 0)
                record["pattern_status_v1"] = str(updated_unit.get("status_v1") or "candidate")
                record["pattern_expectancy_v1"] = float(updated_unit.get("expectancy_v1") or 0.0)
                record["pattern_win_decided_v1"] = decided
                record["outcome_kind_v1"] = str(verdict_info.get("outcome_kind_v1") or "")
                record["pnl_v1"] = float(verdict_info.get("pnl_v1") or 0.0)
                # Regime tag — enables regime-matched retrieval in RMv2
                input_pkt = decision.get("input_packet_v1") or {}
                record["regime_v1"] = str(input_pkt.get("regime_v1") or "unknown")

            learning_observations.append({
                "pattern_id_v1": pattern_id,
                "human_label_v1": sig.get("human_label_v1"),
                "proposed_action_v1": proposed_action,
                "verdict_v1": verdict_info["verdict_v1"],
                "outcome_v1": verdict_info.get("outcome_v1"),
                "outcome_kind_v1": verdict_info.get("outcome_kind_v1"),
                "pnl_v1": verdict_info.get("pnl_v1", 0.0),
                "verdict_reason_v1": verdict_info["verdict_reason_v1"],
                "promotion_v1": promotion,
                "post_status_v1": updated_unit.get("status_v1"),
                "post_total_v1": updated_unit.get("total_observations_v1"),
                "post_wins_v1": updated_unit.get("wins_v1"),
                "post_losses_v1": updated_unit.get("losses_v1"),
                "post_no_trade_correct_v1": updated_unit.get("no_trade_correct_v1"),
                "post_no_trade_missed_v1": updated_unit.get("no_trade_missed_v1"),
                "post_win_rate_v1": updated_unit.get("win_rate_v1"),
                "post_expectancy_v1": updated_unit.get("expectancy_v1"),
                "post_cumulative_pnl_v1": updated_unit.get("cumulative_pnl_v1"),
                "post_confidence_v1": updated_unit.get("confidence_score_v1"),
            })

    # Finalize AFTER falsification so quality stats are in the record dict
    # when memory_store writes it to the shared JSONL.
    run_id = store.finalize(case=case, evaluation=evaluation)

    return {
        "case": case,
        "case_path": case_path,
        "config": dict(config),
        "decisions": decisions,
        "evaluation": evaluation,
        "learning_record": record,
        "retrieval_trace": retrieval_trace,
        "prior_records": prior_records,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "shared_store_path": str(store.get_shared_store_path()) if store.get_shared_store_path() else None,
        "learning_observations_v1": learning_observations,
    }


def _default_expected(proposed_action: str) -> str:
    return {
        "ENTER_LONG": "Price moves up after entry; case PASS.",
        "ENTER_SHORT": "Price moves down after entry; case PASS.",
        "NO_TRADE": "Standing down avoids loss; case does not penalize abstention.",
        "HOLD": "Position thesis remains valid; case PASS.",
        "EXIT": "Exit prevents further loss; case PASS.",
    }.get(proposed_action, "Outcome aligns with proposed action.")
