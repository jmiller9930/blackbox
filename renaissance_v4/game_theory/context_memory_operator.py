"""
Operator-facing contextual memory loop — persist harness winners to JSONL (no Groundhog).

See ``append_context_memory_record`` in :mod:`renaissance_v4.game_theory.context_signature_memory`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.context_signature_memory import (
    append_context_memory_record,
    default_memory_path,
)
from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST


def _outcome_from_winner_metrics(wm: dict[str, Any]) -> dict[str, Any]:
    return {
        "expectancy": float(wm.get("expectancy") or 0.0),
        "max_drawdown": float(wm.get("max_drawdown") or 0.0),
        "win_rate": float(wm.get("win_rate") or 0.0),
        "total_trades": int(wm.get("trade_count") or 0),
        "cumulative_pnl": float(wm.get("pnl") or 0.0),
    }


def maybe_persist_harness_winner_context_memory_v1(
    *,
    context_signature_memory_mode: str,
    learning_run_classification: str | None,
    selected_candidate_id: str | None,
    control_replay: dict[str, Any],
    winner_apply_effective: dict[str, Any] | None,
    winner_metrics: dict[str, Any] | None,
    test_run_id: str,
    manifest_path: Path | str,
    proof_reason_codes: list[str],
    memory_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Append one JSONL record when mode is read_write, run is learning (not execution-only),
    and a candidate winner exists. Returns ``context_memory_operator_panel_v1`` fields.
    """
    mode = (context_signature_memory_mode or "off").strip().lower()
    if mode not in ("off", "read", "read_write"):
        mode = "off"

    mem_p = Path(memory_path or default_memory_path()).expanduser().resolve()
    ra = control_replay.get("replay_attempt_aggregates_v1") or {}
    dcr = control_replay.get("decision_context_recall_stats") or {}
    mem_loaded = max(
        int(ra.get("memory_records_loaded_count") or 0),
        int(dcr.get("memory_records_loaded_count") or 0),
    )
    recall_matches = int(ra.get("recall_match_windows_total") or 0)
    bias_applied = int(ra.get("recall_bias_applied_total") or 0)

    mode_label = "OFF" if mode == "off" else ("READ" if mode == "read" else "READ+WRITE")

    saved = False
    record_id: str | None = None
    err: str | None = None

    should_persist = (
        mode == "read_write"
        and (learning_run_classification or "") == "learning_engaged"
        and bool(selected_candidate_id)
        and isinstance(winner_metrics, dict)
    )

    if should_persist:
        pc = control_replay.get("pattern_context_v1")
        if not isinstance(pc, dict) or pc.get("schema") != "pattern_context_v1":
            err = "missing_or_invalid_pattern_context_v1"
        else:
            eff = {k: v for k, v in (winner_apply_effective or {}).items() if k in BUNDLE_APPLY_WHITELIST}
            try:
                rec = append_context_memory_record(
                    pattern_context_v1=pc,
                    source_run_id=str(test_run_id),
                    source_artifact_paths=[
                        str(Path(manifest_path).resolve()),
                        "context_memory_operator_v1:harness_winner",
                    ],
                    effective_apply=eff,
                    outcome_summary=_outcome_from_winner_metrics(winner_metrics),
                    optimizer_reason_codes=list(proof_reason_codes or [])
                    + ["CTX_MEM_V1_PERSISTED_FROM_HARNESS_WINNER"],
                    memory_path=mem_p,
                )
                saved = True
                record_id = str(rec.get("record_id") or "")
            except Exception as e:  # noqa: BLE001 — operator audit: surface cause
                err = f"{type(e).__name__}: {e}"

    if mode == "off":
        narrative = (
            "Contextual memory is off for this run — no recall file reads and no automatic saves."
        )
    elif saved:
        narrative = (
            "This run found a winning pattern, saved it as contextual memory, "
            "and (where matches occur) prior memory can steer fusion thresholds on future runs."
        )
    elif mode == "read_write" and bool(selected_candidate_id) and err:
        narrative = f"This run selected a winner but contextual memory was not saved ({err})."
    elif mode == "read_write" and not selected_candidate_id:
        narrative = (
            "This run completed learning search with no strict winner over control — "
            "nothing was written to contextual memory."
        )
    elif mem_loaded > 0 and recall_matches > 0 and bias_applied > 0:
        narrative = (
            "This run loaded prior contextual memory, matched similar market conditions, "
            "and applied bounded fusion bias."
        )
    elif mem_loaded > 0 and recall_matches > 0:
        narrative = (
            "This run loaded prior contextual memory and matched similar conditions; "
            "no fusion bias rows fired on this tape window."
        )
    elif mem_loaded > 0:
        narrative = (
            "This run loaded contextual memory records, but no decision-window signature match "
            "occurred on this replay path."
        )
    else:
        narrative = "This run did not load contextual memory records (empty or missing store)."

    return {
        "schema": "context_memory_operator_panel_v1",
        "memory_mode": mode_label,
        "memory_mode_code": mode,
        "memory_saved_this_run": saved,
        "memory_loaded": mem_loaded > 0,
        "memory_records_loaded_count": mem_loaded,
        "recall_matches": recall_matches,
        "bias_applied": bias_applied,
        "narrative": narrative,
        "canonical_memory_path": str(mem_p),
        "persisted_record_id": record_id,
        "persist_error": err,
    }


__all__ = ["maybe_persist_harness_winner_context_memory_v1"]
