"""
GT_DIRECTIVE_041 — Seeded pattern-memory store + EV proof exam helpers.

Seeds ``student_learning_records_v1.jsonl`` with valid ``perps_pattern_signature_v1`` rows so
``evaluate_pattern_memory_v1`` finds matches (≥ min sample), EV layer activates, and proof fields
are observable per scenario.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.pml_runtime_layout import blackbox_repo_root
from renaissance_v4.game_theory.student_proctor.contracts_v1 import legal_example_student_learning_record_v1
from renaissance_v4.game_theory.student_proctor.entry_reasoning_engine_v1 import run_entry_reasoning_pipeline_v1
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_PROMOTE,
    build_learning_governance_v1,
)
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import build_student_decision_packet_v1

GT041_MEMORY_EV_EXAM_ID_V1 = "d6-memory-ev-proof-001"

# Same harness + seed path layout for follow-on proof exams (e.g. GT_DIRECTIVE_043).
GT041_STYLE_EXAM_IDS_V1: frozenset[str] = frozenset(
    {
        "d6-memory-ev-proof-001",
        "d6-memory-ev-proof-002",
        "d6-memory-ev-proof-003",
    }
)


def gt041_learning_store_path_v1(exam_id: str) -> Path:
    root = blackbox_repo_root() / "runtime" / "exam" / exam_id.strip()
    root.mkdir(parents=True, exist_ok=True)
    return root / "student_learning_records_gt041_v1.jsonl"


def _lane_pnl_v1(lane: str, *, repeat_idx: int) -> float:
    """Deterministic PnL magnitudes so pooled stats stay directional per lane."""
    base = float(repeat_idx + 1)
    if lane == "memory_positive":
        return round(120.0 + base * 17.0, 4)
    if lane == "memory_negative":
        return round(-220.0 - base * 23.0, 4)
    if lane == "ev_positive":
        return round(180.0 + base * 11.0, 4)
    if lane == "ev_negative":
        return round(-190.0 - base * 13.0, 4)
    return 0.0


def _capture_signature_probe_v1(
    *,
    db_path: Path,
    symbol: str,
    candle_timeframe_minutes: int,
    decision_open_time_ms: int,
    empty_store: Path,
    scenario_id: str,
) -> dict[str, Any]:
    prev = os.environ.get("PATTERN_GAME_STUDENT_LEARNING_STORE")
    os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"] = str(empty_store)
    try:
        empty_store.parent.mkdir(parents=True, exist_ok=True)
        empty_store.write_text("", encoding="utf-8")
        pkt, perr = build_student_decision_packet_v1(
            db_path=db_path,
            symbol=symbol,
            decision_open_time_ms=decision_open_time_ms,
            candle_timeframe_minutes=candle_timeframe_minutes,
            notes=f"GT041_sig_probe {scenario_id}",
        )
        if perr or pkt is None:
            raise RuntimeError(f"GT041 probe packet: {perr}")
        ere, ere_errs, _tr, _pfm = run_entry_reasoning_pipeline_v1(
            student_decision_packet=pkt,
            retrieved_student_experience=[],
            run_candle_timeframe_minutes=candle_timeframe_minutes,
            job_id="gt041_signature_probe",
            fingerprint=None,
            scenario_id=scenario_id,
            trade_id=f"{scenario_id}_sig",
            emit_traces=False,
            unified_agent_router=False,
        )
        if ere_errs or ere is None:
            raise RuntimeError(f"GT041 probe ere: {'; '.join(ere_errs or [])}")
        pm = ere.get("pattern_memory_eval_v1")
        if not isinstance(pm, dict):
            raise RuntimeError("GT041 probe: missing pattern_memory_eval_v1")
        sig = pm.get("perps_pattern_signature_v1")
        if not isinstance(sig, dict):
            raise RuntimeError("GT041 probe: missing perps_pattern_signature_v1")
        return dict(sig)
    finally:
        if prev is None:
            os.environ.pop("PATTERN_GAME_STUDENT_LEARNING_STORE", None)
        else:
            os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"] = prev


def prepare_gt041_seeded_learning_store_v1(
    *,
    exam_id: str,
    db_path: Path,
    scenarios: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    """
    Writes ≥20 promoted learning rows (here: 30 = 3×10 scenarios) with signatures captured
    from the same windows as the exam scenarios (empty store probe pass).

    Returns ``(store_path, probe_meta)``.
    """
    if len(scenarios) != 10:
        raise RuntimeError("GT041 expects exactly 10 scenarios")
    out_path = gt041_learning_store_path_v1(exam_id)
    probe_empty = out_path.parent / ".gt041_empty_probe_store.jsonl"

    signatures: list[dict[str, Any]] = []
    lanes: list[str] = []
    for sc in scenarios:
        lanes.append(str(sc.get("gt041_lane_v1") or ""))
        signatures.append(
            _capture_signature_probe_v1(
                db_path=db_path,
                symbol=str(sc["symbol"]),
                candle_timeframe_minutes=int(sc["candle_timeframe_minutes"]),
                decision_open_time_ms=int(sc["decision_open_time_ms"]),
                empty_store=probe_empty,
                scenario_id=str(sc["scenario_id"]),
            )
        )

    meta = {
        "schema": "gt041_seed_meta_v1",
        "exam_id": exam_id,
        "gt041_lanes_v1": lanes,
        "records_written_v1": 0,
        "signature_hashes_preview_v1": [str(s.get("signature_hash_v1") or "")[:12] for s in signatures],
    }

    lines: list[str] = []
    total = 0
    for slot, sc in enumerate(scenarios):
        lane = str(sc.get("gt041_lane_v1") or "")
        sig = signatures[slot]
        tf = int(sc["candle_timeframe_minutes"])
        sym = str(sc["symbol"])
        for k in range(3):
            base = legal_example_student_learning_record_v1()
            rid = str(uuid.uuid4())
            base["record_id"] = rid
            base["run_id"] = "gt041_seed_hist_v1"
            base["graded_unit_id"] = f"gt041_{exam_id}_slot{slot}_r{k}"
            base["created_utc"] = "2026-04-27T12:00:00Z"
            base["candle_timeframe_minutes"] = tf
            base["referee_outcome_subset"] = {
                "pnl": _lane_pnl_v1(lane, repeat_idx=k),
                "trade_id": f"gt041_{slot}_{k}",
                "symbol": sym,
            }
            base["perps_pattern_signature_v1"] = dict(sig)
            base["learning_governance_v1"] = build_learning_governance_v1(
                decision=GOVERNANCE_PROMOTE,
                reason_codes=["gt041_seeded_memory_ev_proof_v1"],
                source_job_id=f"gt041_seed_{exam_id}",
                fingerprint=None,
            )
            lines.append(json.dumps(base, ensure_ascii=False))
            total += 1

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta["records_written_v1"] = total
    return out_path, meta


def extract_gt041_proof_row_v1(
    *,
    scenario: dict[str, Any],
    ere: dict[str, Any] | None,
    final_action: str,
) -> dict[str, Any]:
    """Proof bundle aligned with directive acceptance tables."""
    lane = str(scenario.get("gt041_lane_v1") or "")
    pm = ere.get("pattern_memory_eval_v1") if isinstance(ere, dict) else None
    pm = pm if isinstance(pm, dict) else {}
    ev = ere.get("expected_value_risk_cost_v1") if isinstance(ere, dict) else None
    ev = ev if isinstance(ev, dict) else {}
    ds = ere.get("decision_synthesis_v1") if isinstance(ere, dict) else None
    ds = ds if isinstance(ds, dict) else {}

    matched = int(pm.get("matched_count_v1") or 0)
    peff = float(pm.get("pattern_effect_to_score_v1") or 0.0)
    ev_avail = bool(ev.get("available_v1"))
    ev_sa = float(ds.get("ev_score_adjustment_v1") or 0.0)
    scount = int(ev.get("sample_count_v1") or 0)

    mem_ok = True
    if "memory" in lane:
        mem_ok = matched > 0 and peff != 0.0

    ev_ok = True
    if lane.startswith("ev_"):
        ev_ok = ev_avail and ev_sa != 0.0

    return {
        "schema": "gt041_scenario_proof_v1",
        "gt041_lane_v1": lane,
        "matched_count_v1": matched,
        "pattern_effect_to_score_v1": peff,
        "memory_proof_ok_v1": mem_ok,
        "expected_value_available_v1": ev_avail,
        "sample_count_v1": scount,
        "ev_score_adjustment_v1": ev_sa,
        "ev_proof_ok_v1": ev_ok,
        "sealed_action_v1": final_action,
    }


def summarize_gt041_acceptance_v1(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Directive acceptance booleans — six memory lanes + four EV lanes must individually pass."""
    mem_match_ok: list[bool] = []
    mem_eff_ok: list[bool] = []
    ev_avail_ok: list[bool] = []
    ev_adj_ok: list[bool] = []
    fingerprint_ok = len(rows) == 10

    for r in rows:
        proof = r.get("gt041_proof_v1")
        if not isinstance(proof, dict):
            fingerprint_ok = False
            continue
        lane = str(proof.get("gt041_lane_v1") or "")
        matched = int(proof.get("matched_count_v1") or 0)
        peff = float(proof.get("pattern_effect_to_score_v1") or 0.0)
        ev_av = bool(proof.get("expected_value_available_v1"))
        ev_sa = float(proof.get("ev_score_adjustment_v1") or 0.0)

        if "memory" in lane:
            mem_match_ok.append(matched > 0)
            mem_eff_ok.append(peff != 0.0)
        if lane.startswith("ev_"):
            ev_avail_ok.append(ev_av)
            ev_adj_ok.append(ev_sa != 0.0)

        mem_lane = "memory" in lane
        ev_lane = lane.startswith("ev_")
        if mem_lane and (matched <= 0 or peff == 0.0):
            fingerprint_ok = False
        if ev_lane and (not ev_av or ev_sa == 0.0):
            fingerprint_ok = False

    mem_all_match = len(mem_match_ok) == 6 and all(mem_match_ok)
    mem_all_eff = len(mem_eff_ok) == 6 and all(mem_eff_ok)
    ev_two_plus = sum(1 for x in ev_avail_ok if x) >= 2 and sum(1 for x in ev_adj_ok if x) >= 2

    return {
        "memory_matches_observed_v1": "YES" if mem_all_match else "NO",
        "memory_changes_score_or_outcome_v1": "YES" if mem_all_eff else "NO",
        "ev_active_at_least_two_scenarios_v1": "YES" if ev_two_plus else "NO",
        "ev_changes_score_or_outcome_v1": "YES" if ev_two_plus else "NO",
        "fingerprint_shows_memory_and_ev_v1": "YES" if fingerprint_ok else "NO",
        "memory_lane_match_count_ok_v1": sum(1 for x in mem_match_ok if x),
        "memory_lane_effect_nonzero_v1": sum(1 for x in mem_eff_ok if x),
        "ev_lane_available_count_v1": sum(1 for x in ev_avail_ok if x),
        "ev_lane_adjustment_nonzero_v1": sum(1 for x in ev_adj_ok if x),
    }


__all__ = [
    "GT041_MEMORY_EV_EXAM_ID_V1",
    "GT041_STYLE_EXAM_IDS_V1",
    "extract_gt041_proof_row_v1",
    "gt041_learning_store_path_v1",
    "prepare_gt041_seeded_learning_store_v1",
    "summarize_gt041_acceptance_v1",
]
