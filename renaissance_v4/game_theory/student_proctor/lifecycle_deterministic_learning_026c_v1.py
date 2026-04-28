"""
GT_DIRECTIVE_026C — deterministic lifecycle learning (no LLM, append-only, traceable).

Converts a **closed** ``lifecycle_tape_result_v1`` into scored records, promotion decisions, and
retrieval of **promoted** pattern summaries only. Router / external APIs do not write learning.
"""

from __future__ import annotations

import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord
from renaissance_v4.game_theory.pml_runtime_layout import pml_runtime_root
from renaissance_v4.game_theory.student_test_mode_v1 import student_test_mode_isolation_active_v1
from renaissance_v4.game_theory.student_proctor.student_reasoning_fault_map_v1 import (
    CONTRACT_VERSION_FAULT_MAP,
    SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
    STATUS_FAIL,
    STATUS_NOT_PROVEN,
    STATUS_PASS,
    STATUS_SKIPPED,
    build_fault_map_v1,
    make_fault_node_v1,
    NODE_IDS_ORDER,
)

SCHEMA_LIFECYCLE_DETERMINISTIC_LEARNING_RECORD_026C = "student_lifecycle_deterministic_learning_record_026c_v1"
CONTRACT_VERSION_026C = 1
SCHEMA_DECISION_QUALITY_SCORE_026C = "decision_quality_score_v1"
SCHEMA_ATTRIBUTION_BREAKDOWN_026C = "attribution_breakdown_v1"
SCHEMA_LEARNING_DECISION_026C = "learning_decision_v1"
FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C = "retrieved_lifecycle_deterministic_learning_026c_v1"

_PROMOTE_MIN_SAMPLES = 3
_PROMOTE_MIN_OVERALL = 0.72
_REJECT_MAX_OVERALL = 0.35
_LAMBDA_DECAY_PER_DAY = 0.03
_MAX_RETRIEVAL_026C = 8


def default_lifecycle_deterministic_learning_store_path_v1() -> Path:
    """Append-only JSONL: ``<runtime>/student_learning/lifecycle_deterministic_learning_026c_v1.jsonl``."""
    override = (os.environ.get("PATTERN_GAME_LIFECYCLE_DETERMINISTIC_LEARNING_026C_STORE") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    p = pml_runtime_root() / "student_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p / "lifecycle_deterministic_learning_026c_v1.jsonl"


def _final_thesis_state_v1(
    entry_thesis: dict[str, Any] | None,
    tape: dict[str, Any],
) -> str:
    """``valid`` | ``degraded`` | ``invalidated`` from tape + thesis snapshot."""
    ex = str(tape.get("exit_reason_code_v1") or "")
    exu = ex.upper()
    if "INVALIDAT" in exu or "THESIS_INVALID" in exu:
        return "invalidated"
    rows = _per_bar_rows(tape)
    if rows:
        le = rows[-1].get("lifecycle_reasoning_eval_v1")
        if isinstance(le, dict):
            ts = str(le.get("thesis_state_v1") or "")
            if "invalid" in ts.lower():
                return "invalidated"
            if "degrad" in ts.lower() or "stress" in ts.lower():
                return "degraded"
    t = (entry_thesis or {}).get("thesis_text_v1") or (entry_thesis or {}).get("narrative_v1")
    if t and "stress" in str(t).lower():
        return "degraded"
    return "valid"


def _per_bar_rows(tape: dict[str, Any]) -> list[dict[str, Any]]:
    slim = tape.get("per_bar_slim_v1")
    if isinstance(slim, list):
        return [x for x in slim if isinstance(x, dict)]
    full = tape.get("per_bar_v1")
    if isinstance(full, list):
        return [x for x in full if isinstance(x, dict)]
    return []


def compute_decision_quality_score_026c_v1(
    *,
    tape: dict[str, Any],
    entry_reasoning_eval_v1: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    ``decision_quality_score_v1`` — entry / hold / exit in ``[0,1]``, deterministic rules only.
    """
    rows = _per_bar_rows(tape)
    exit_code = str(tape.get("exit_reason_code_v1") or "")
    n_hold = sum(
        1
        for r in rows
        if str((r.get("decision_v1") or r.get("lifecycle_reasoning_eval_v1") or {}).get("decision_v1") or r.get("decision_v1") or "")  # type: ignore[union-attr]
        in ("", "hold")
    )
    n_rows = max(1, len(rows))
    # Entry: if exit is thesis-invalidated, entry likely poor
    if "invalidat" in exit_code or "thesis" in exit_code:
        entry_01 = 0.25
    else:
        entry_01 = 0.65 + 0.35 * min(1.0, (1.0 if "target" in exit_code or "stop" in exit_code else 0.7))

    # Hold: share of non-exit rows that are hold
    if len(rows) <= 1:
        hold_01 = 0.75
    else:
        hold_01 = min(1.0, 0.5 + 0.5 * (n_hold / max(1, n_rows - 1)))

    # Exit: match quality to exit type
    if "target" in exit_code:
        exit_01 = 0.95
    elif "stop" in exit_code:
        exit_01 = 0.55
    elif "time" in exit_code or "expired" in exit_code:
        exit_01 = 0.6
    elif "opposing" in exit_code or "signal" in exit_code:
        exit_01 = 0.7
    elif "confiden" in exit_code or "collaps" in exit_code:
        exit_01 = 0.45
    elif "invalidat" in exit_code:
        exit_01 = 0.35
    else:
        exit_01 = 0.55

    overall = round((entry_01 + hold_01 + exit_01) / 3.0, 6)
    return {
        "schema": SCHEMA_DECISION_QUALITY_SCORE_026C,
        "contract_version": CONTRACT_VERSION_026C,
        "entry_score_01": round(entry_01, 6),
        "hold_score_01": round(hold_01, 6),
        "exit_score_01": round(exit_01, 6),
        "overall_score_v1": overall,
    }


def compute_attribution_breakdown_026c_v1(
    scores: dict[str, Any],
) -> dict[str, Any]:
    """
    ``attribution_breakdown_v1`` — quality split across entry / hold / exit + luck; sums to 1.0.
    """
    se = float(scores.get("entry_score_01") or 0.0)
    sh = float(scores.get("hold_score_01") or 0.0)
    sx = float(scores.get("exit_score_01") or 0.0)
    s = se + sh + sx
    quality_01 = min(1.0, max(0.0, s / 3.0))
    luck_01 = max(0.0, 1.0 - quality_01)
    if s < 1e-12:
        e, h, x = quality_01 / 3.0, quality_01 / 3.0, quality_01 / 3.0
    else:
        e, h, x = (se / s) * quality_01, (sh / s) * quality_01, (sx / s) * quality_01
    sm = e + h + x + luck_01
    if sm > 1e-12 and abs(sm - 1.0) > 1e-6:
        f = 1.0 / sm
        e, h, x, luck_01 = e * f, h * f, x * f, luck_01 * f
    return {
        "schema": SCHEMA_ATTRIBUTION_BREAKDOWN_026C,
        "contract_version": CONTRACT_VERSION_026C,
        "entry_contribution_01": round(e, 6),
        "hold_contribution_01": round(h, 6),
        "exit_contribution_01": round(x, 6),
        "luck_contribution_01": round(luck_01, 6),
    }


def make_learning_decision_026c_v1(
    *,
    overall_score: float,
    pnl: float,
    pattern_sample_count: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema": SCHEMA_LEARNING_DECISION_026C,
        "contract_version": CONTRACT_VERSION_026C,
    }
    if pnl < 0.0 or overall_score < _REJECT_MAX_OVERALL:
        out["outcome_v1"] = "reject_pattern_v1"
        out["detail_v1"] = "reject: negative pnl or below reject threshold on overall score"
    elif (
        overall_score >= _PROMOTE_MIN_OVERALL
        and pnl > 0.0
        and pattern_sample_count + 1 >= _PROMOTE_MIN_SAMPLES
    ):
        out["outcome_v1"] = "promote_pattern_v1"
        out["detail_v1"] = "promote: overall>= min, pnl>0, enough prior samples (including this close)"
    elif pattern_sample_count < 2:
        out["outcome_v1"] = "insufficient_data_v1"
        out["detail_v1"] = f"insufficient: need prior N>={2} for cut, have={pattern_sample_count}"
    else:
        out["outcome_v1"] = "insufficient_data_v1"
        out["detail_v1"] = "mixed: no promote/reject (between thresholds)"
    return out


def _pattern_key_026c_v1(
    symbol: str,
    candle_timeframe_minutes: int,
    side: str,
    exit_reason_code: str,
) -> str:
    s = f"{str(symbol).strip().upper()}:{int(candle_timeframe_minutes)}:{side}:{exit_reason_code}"
    return re.sub(r"[^a-zA-Z0-9:._-]", "_", s)[:256]


def count_pattern_key_occurrences_026c_v1(store_path: Path | str, pattern_key: str) -> int:
    p = Path(store_path)
    if not p.is_file():
        return 0
    n = 0
    pk = str(pattern_key)
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict) and str((o.get("pattern_key_026c_v1") or "")) == pk:
            n += 1
    return n


def build_lifecycle_learning_record_026c_v1(
    *,
    tape: dict[str, Any],
    entry_reasoning_eval_v1: dict[str, Any] | None,
    outcome: OutcomeRecord,
    trade_id: str,
    symbol: str,
    candle_timeframe_minutes: int,
    job_id: str,
    context_signature_key: str,
    entry_bar_index_v1: int = 0,
) -> dict[str, Any] | None:
    if not tape.get("closed_v1"):
        return None
    ex = int(tape.get("exit_at_bar_index_v1") or -1)
    e_in = int(entry_bar_index_v1)
    rows = _per_bar_rows(tape)
    ent_thesis = (entry_reasoning_eval_v1 or {}).get("entry_thesis_v1")
    if not isinstance(ent_thesis, dict):
        ent_thesis = ((entry_reasoning_eval_v1 or {}).get("thesis_synthesis_v1") or {}) if isinstance(
            (entry_reasoning_eval_v1 or {}).get("thesis_synthesis_v1"), dict
        ) else {"snapshot_v1": "n/a"}
    final_ts = _final_thesis_state_v1(ent_thesis, tape)  # type: ignore[arg-type]
    et = entry_reasoning_eval_v1 or {}
    side = "long" if str(outcome.direction or "").lower() == "long" else "short"
    scores = compute_decision_quality_score_026c_v1(
        tape=tape, entry_reasoning_eval_v1=entry_reasoning_eval_v1
    )
    attr = compute_attribution_breakdown_026c_v1(scores)
    pnl = float(outcome.pnl) if outcome.pnl is not None else 0.0
    pk = _pattern_key_026c_v1(
        symbol, candle_timeframe_minutes, side, str(tape.get("exit_reason_code_v1") or "unknown")
    )
    path = default_lifecycle_deterministic_learning_store_path_v1()
    prior_n = count_pattern_key_occurrences_026c_v1(path, pk)
    decision = make_learning_decision_026c_v1(
        overall_score=float(scores.get("overall_score_v1") or 0.0),
        pnl=pnl,
        pattern_sample_count=prior_n,
    )
    entry_px = float(outcome.entry_price) if outcome.entry_price is not None else 0.0
    exit_px = float(outcome.exit_price) if outcome.exit_price is not None else 0.0
    bars_held = max(0, ex - e_in + 1) if ex >= e_in else 0
    mdd = 0.0
    # crude max adverse excursion from rows if available
    for r in rows:
        ev = r.get("lifecycle_reasoning_eval_v1")
        u = (ev or {}).get("unrealized_pnl_fraction_v1")
        if isinstance(u, (int, float)):
            mdd = min(mdd, float(u))

    rid = f"ldl_026c_{uuid.uuid4().hex}"
    rec: dict[str, Any] = {
        "schema": SCHEMA_LIFECYCLE_DETERMINISTIC_LEARNING_RECORD_026C,
        "contract_version": CONTRACT_VERSION_026C,
        "record_id_026c": rid,
        "created_utc_026c": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "job_id_v1": str(job_id).strip(),
        "trade_id_v1": str(trade_id).strip(),
        "symbol_v1": str(symbol).strip(),
        "timeframe_v1": int(candle_timeframe_minutes),
        "entry_bar_index_v1": e_in,
        "exit_bar_index_v1": int(ex) if ex >= 0 else 0,
        "exit_reason_code_v1": str(tape.get("exit_reason_code_v1") or ""),
        "direction_v1": side,
        "entry_price_v1": entry_px,
        "exit_price_v1": exit_px,
        "pnl_v1": pnl,
        "max_drawdown_v1": round(mdd, 8),
        "bars_held_v1": int(bars_held),
        "entry_thesis_v1": dict(ent_thesis) if isinstance(ent_thesis, dict) else {"note": "missing"},
        "final_thesis_state_v1": final_ts,
        "decision_quality_score_v1": scores,
        "attribution_breakdown_v1": attr,
        "learning_decision_v1": decision,
        "context_signature_key_v1": str(context_signature_key).strip(),
        "pattern_key_026c_v1": pk,
    }
    return rec


def _created_utc_to_ms_026c(created_utc: str) -> int | None:
    try:
        t0 = datetime.fromisoformat(str(created_utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    return int(t0.timestamp() * 1000)


def append_lifecycle_deterministic_learning_record_026c_v1(
    path: Path | str,
    record: dict[str, Any],
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    with p.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _decay_weight_01_v1(created_utc: str, *, now_utc: datetime | None = None) -> float:
    try:
        t0 = datetime.fromisoformat(created_utc.replace("Z", "+00:00"))
    except ValueError:
        return 0.5
    now = now_utc or datetime.now(timezone.utc)
    if t0.tzinfo is None:
        t0 = t0.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - t0).total_seconds() / 86400.0)
    return max(0.05, min(1.0, math.exp(-_LAMBDA_DECAY_PER_DAY * days)))


def retrieve_applicable_learning_context_026c_v1(
    *,
    symbol: str,
    candle_timeframe_minutes: int,
    context_signature_key: str,
    decision_open_time_ms: int,
    store_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    **STRICT** retrieval: only ``promote_pattern_v1`` rows, same symbol+timeframe+signature, prior
    decision time, bounded, decay-weighted, conflict-resolved (higher sample n then higher score).
    """
    if student_test_mode_isolation_active_v1():
        return []

    p = Path(store_path or default_lifecycle_deterministic_learning_store_path_v1())
    if not p.is_file():
        return []
    sk_req = str(context_signature_key).strip()
    sym = str(symbol).strip().upper()
    candidates: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(o, dict):
            continue
        if str(o.get("context_signature_key_v1") or "") != sk_req:
            continue
        if str(o.get("symbol_v1") or "").upper() != sym:
            continue
        if int(o.get("timeframe_v1") or -1) != int(candle_timeframe_minutes):
            continue
        ld = o.get("learning_decision_v1")
        if not isinstance(ld, dict):
            continue
        if str(ld.get("outcome_v1") or "") != "promote_pattern_v1":
            continue
        rec_ms = _created_utc_to_ms_026c(str(o.get("created_utc_026c") or ""))
        if rec_ms is not None and rec_ms >= int(decision_open_time_ms):
            continue
        candidates.append(o)

    def sort_key(c: dict[str, Any]) -> tuple:
        s = c.get("decision_quality_score_v1")
        ovr = float((s or {}).get("overall_score_v1") or 0.0) if isinstance(s, dict) else 0.0
        pk = str(c.get("pattern_key_026c_v1") or "")
        n = count_pattern_key_occurrences_026c_v1(p, pk)
        return (-n, -ovr)

    candidates.sort(key=sort_key)
    seen: set[str] = set()
    conf_logged = len(candidates) > 1
    uniq: list[dict[str, Any]] = []
    for c in candidates:
        rid = str(c.get("record_id_026c") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        uniq.append(c)
    out: list[dict[str, Any]] = []
    for i, c in enumerate(uniq[:_MAX_RETRIEVAL_026C]):
        w = _decay_weight_01_v1(str(c.get("created_utc_026c") or ""))
        row: dict[str, Any] = {
            "schema": "retrieved_lifecycle_deterministic_learning_slice_026c_v1",
            "record_id_026c": c.get("record_id_026c"),
            "pattern_key_026c_v1": c.get("pattern_key_026c_v1"),
            "overall_score_01": (c.get("decision_quality_score_v1") or {}).get("overall_score_v1")
            if isinstance(c.get("decision_quality_score_v1"), dict)
            else None,
            "decay_weight_01": round(w, 6),
        }
        if i == 0 and conf_logged:
            row["conflict_resolved_v1"] = "prefer_larger_sample_then_higher_score"
        out.append(row)
    return out


def merge_026c_deterministic_learning_fault_nodes_v1(
    base: dict[str, Any],
    *,
    record_ok: bool,
    scoring_ok: bool,
    decision_ok: bool,
    retrieval_in_path: bool,
) -> dict[str, Any]:
    """GT_DIRECTIVE_026C + 026R — set last four nodes in ``NODE_IDS_ORDER``."""
    import copy

    b = base if isinstance(base, dict) else {"schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1, "nodes_v1": []}
    nodes = [copy.deepcopy(x) for x in (b.get("nodes_v1") or []) if isinstance(x, dict)]
    by_id: dict[str, dict[str, Any]] = {str(n.get("node_id") or ""): n for n in nodes}

    prev = by_id.get("learning_retrieval_applied")
    prev_retrieval_pass = isinstance(prev, dict) and str(prev.get("status") or "") == STATUS_PASS
    eff_retrieval = bool(retrieval_in_path or prev_retrieval_pass)

    by_id["learning_record_created"] = make_fault_node_v1(
        "learning_record_created",
        STATUS_PASS if record_ok else STATUS_FAIL,
        input_summary_v1="Closed lifecycle tape + entry reasoning.",
        output_summary_v1="Record written" if record_ok else "Not written",
        operator_message_v1="GT_DIRECTIVE_026C append-only deterministic record (no LLM).",
    )
    by_id["learning_scoring_evaluated"] = make_fault_node_v1(
        "learning_scoring_evaluated",
        STATUS_PASS if scoring_ok and record_ok else (STATUS_FAIL if not scoring_ok else STATUS_SKIPPED),
        input_summary_v1="decision_quality_score_v1 + attribution",
        output_summary_v1="Scores computed" if scoring_ok else "Failed",
        operator_message_v1="Deterministic entry/hold/exit scores; overall_score_v1.",
    )
    by_id["learning_promotion_decision"] = make_fault_node_v1(
        "learning_promotion_decision",
        STATUS_PASS if decision_ok and scoring_ok else (STATUS_FAIL if not decision_ok else STATUS_SKIPPED),
        input_summary_v1="Sample count + pnl + thresholds",
        output_summary_v1="Decision" if decision_ok else "Not made",
        operator_message_v1="promote_pattern_v1 | reject_pattern_v1 | insufficient_data_v1 (no silent promote).",
    )
    by_id["learning_retrieval_applied"] = make_fault_node_v1(
        "learning_retrieval_applied",
        STATUS_PASS if eff_retrieval else STATUS_SKIPPED,
        input_summary_v1="Promoted 026C rows for this signature (packet path).",
        output_summary_v1="Slices attached" if eff_retrieval else "Not attached for this run",
        operator_message_v1="STRICT: promoted patterns only, bounded, prior to decision time.",
    )
    if not record_ok:
        by_id["learning_scoring_evaluated"] = make_fault_node_v1(
            "learning_scoring_evaluated",
            STATUS_SKIPPED,
            input_summary_v1="—",
            output_summary_v1="—",
            operator_message_v1="Record not created.",
        )
        by_id["learning_promotion_decision"] = make_fault_node_v1(
            "learning_promotion_decision",
            STATUS_SKIPPED,
            input_summary_v1="—",
            output_summary_v1="—",
            operator_message_v1="Record not created.",
        )

    ordered = [
        by_id.get(nid)
        or make_fault_node_v1(
            nid, STATUS_NOT_PROVEN, input_summary_v1="—", output_summary_v1="—", operator_message_v1="Missing node."
        )
        for nid in NODE_IDS_ORDER
    ]
    return {
        "schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "contract_version": CONTRACT_VERSION_FAULT_MAP,
        "nodes_v1": ordered,
    }


def process_closed_lifecycle_for_deterministic_learning_026c_v1(
    *,
    tape_result_v1: dict[str, Any],
    entry_reasoning_eval_v1: dict[str, Any] | None,
    outcome: OutcomeRecord,
    job_id: str,
    scenario_id: str,
    trade_id: str,
    candle_timeframe_minutes: int,
    context_signature_key: str,
    symbol: str,
    pfm: dict[str, Any] | None,
    entry_bar_index_v1: int = 0,
    retrieval_in_path: bool = False,
    fingerprint: str | None = None,
    emit_trace_events: bool = True,
) -> dict[str, Any] | None:
    """Build record, append store, optional learning-trace events, return merged fault map."""
    if not isinstance(tape_result_v1, dict) or not tape_result_v1.get("closed_v1"):
        return pfm
    rec = build_lifecycle_learning_record_026c_v1(
        tape=tape_result_v1,
        entry_reasoning_eval_v1=entry_reasoning_eval_v1,
        outcome=outcome,
        trade_id=trade_id,
        symbol=symbol,
        candle_timeframe_minutes=candle_timeframe_minutes,
        job_id=job_id,
        context_signature_key=context_signature_key,
        entry_bar_index_v1=entry_bar_index_v1,
    )
    if not isinstance(rec, dict):
        return pfm
    store = default_lifecycle_deterministic_learning_store_path_v1()
    try:
        append_lifecycle_deterministic_learning_record_026c_v1(store, rec)
        record_ok = True
    except OSError:
        record_ok = False
    scoring_ok = True
    decision_ok = bool(rec.get("learning_decision_v1"))
    if emit_trace_events and str(job_id or "").strip():
        from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import (
            emit_026c_learning_decision_made_v1,
            emit_026c_learning_record_created_v1,
            emit_026c_learning_scoring_completed_v1,
        )

        emit_026c_learning_record_created_v1(
            job_id=str(job_id).strip(),
            fingerprint=fingerprint,
            scenario_id=scenario_id,
            trade_id=trade_id,
            record_id_026c=str(rec.get("record_id_026c") or ""),
        )
        emit_026c_learning_scoring_completed_v1(
            job_id=str(job_id).strip(),
            fingerprint=fingerprint,
            scenario_id=scenario_id,
            trade_id=trade_id,
            decision_quality_score_v1=rec.get("decision_quality_score_v1"),
        )
        emit_026c_learning_decision_made_v1(
            job_id=str(job_id).strip(),
            fingerprint=fingerprint,
            scenario_id=scenario_id,
            trade_id=trade_id,
            learning_decision_v1=rec.get("learning_decision_v1"),
        )
    if not isinstance(pfm, dict):
        pfm = build_fault_map_v1([], fill_missing_as=STATUS_NOT_PROVEN)
    return merge_026c_deterministic_learning_fault_nodes_v1(
        pfm,
        record_ok=record_ok,
        scoring_ok=scoring_ok,
        decision_ok=decision_ok,
        retrieval_in_path=retrieval_in_path,
    )


def merge_026c_learning_retrieval_node_only_v1(
    base: dict[str, Any],
    *,
    retrieval_slices_attached: bool,
) -> dict[str, Any]:
    """
    For entry pipeline only: set ``learning_retrieval_applied`` without touching the other
    026C nodes (left NOT_PROVEN until a closed-tape run fills them).
    """
    import copy

    b = base if isinstance(base, dict) else {"schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1, "nodes_v1": []}
    nodes = [copy.deepcopy(x) for x in (b.get("nodes_v1") or []) if isinstance(x, dict)]
    by_id: dict[str, dict[str, Any]] = {str(n.get("node_id") or ""): n for n in nodes}
    by_id["learning_retrieval_applied"] = make_fault_node_v1(
        "learning_retrieval_applied",
        STATUS_PASS if retrieval_slices_attached else STATUS_SKIPPED,
        input_summary_v1="026C packet retrieval (promoted patterns, prior, bounded).",
        output_summary_v1="Attached" if retrieval_slices_attached else "No promoted rows",
        operator_message_v1="GT_DIRECTIVE_026C retrieval only; learning record nodes remain NOT_PROVEN until a closed trade.",
    )
    return {
        "schema": SCHEMA_STUDENT_REASONING_FAULT_MAP_V1,
        "contract_version": CONTRACT_VERSION_FAULT_MAP,
        "nodes_v1": [
            by_id.get(nid)
            or make_fault_node_v1(nid, STATUS_NOT_PROVEN, "—", "—", "Missing node.")
            for nid in NODE_IDS_ORDER
        ],
    }


__all__ = [
    "FIELD_RETRIEVED_LIFECYCLE_LEARNING_026C",
    "SCHEMA_LIFECYCLE_DETERMINISTIC_LEARNING_RECORD_026C",
    "SCHEMA_ATTRIBUTION_BREAKDOWN_026C",
    "SCHEMA_LEARNING_DECISION_026C",
    "default_lifecycle_deterministic_learning_store_path_v1",
    "compute_decision_quality_score_026c_v1",
    "compute_attribution_breakdown_026c_v1",
    "make_learning_decision_026c_v1",
    "count_pattern_key_occurrences_026c_v1",
    "build_lifecycle_learning_record_026c_v1",
    "append_lifecycle_deterministic_learning_record_026c_v1",
    "retrieve_applicable_learning_context_026c_v1",
    "merge_026c_deterministic_learning_fault_nodes_v1",
    "process_closed_lifecycle_for_deterministic_learning_026c_v1",
    "merge_026c_learning_retrieval_node_only_v1",
]
