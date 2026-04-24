"""
D14 — canonical ``student_decision_record_v1`` export, run-row enrichment, Groundhog rules.

Spec: ``renaissance_v4/game_theory/docs/D14_student_panel_architecture_spec_v1.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
    load_run_record,
)
from renaissance_v4.game_theory.student_panel_d13 import (
    SCHEMA_DECISION_RECORD,
    _bool_from_yes,
    _int,
    _ordered_parallel_rows,
    _panel_run_row_for_job,
    _trade_opportunities_from_payload,
)


def _float(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
)
from renaissance_v4.game_theory.student_panel_d11 import SCHEMA_RUN_ROW, _groundhog_active_for_d11
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    default_student_learning_store_path_v1,
    list_student_learning_records_by_graded_unit_id,
)


def _dg() -> str:
    return "data_gap"


def _entry_retrieval_positive(entry: dict[str, Any]) -> bool:
    recall = _int(entry.get("recall_matches"), 0)
    stud = _int(entry.get("student_retrieval_matches"), 0)
    mci = entry.get("memory_context_impact_audit_v1")
    mem_yes = isinstance(mci, dict) and mci.get("memory_impact_yes_no") == "YES"
    return bool(recall > 0 or stud > 0 or mem_yes or _groundhog_active_for_d11(entry))


def _behavior_changed_bool(row: dict[str, Any] | None, entry: dict[str, Any]) -> bool:
    if row:
        hb = _bool_from_yes(row.get("harness_behavior_changed"))
        sh = _bool_from_yes(row.get("student_handoff_active"))
        if hb is True or sh is True:
            return True
        if hb is False and sh is False:
            return False
    hb2 = str(entry.get("recall_bias_applied") or "") and _int(entry.get("recall_bias_applied"), 0) > 0
    return bool(
        _int(entry.get("recall_matches"), 0) > 0
        or _int(entry.get("student_retrieval_matches"), 0) > 0
        or _int(entry.get("student_learning_rows_appended"), 0) > 0
        or hb2
    )


def _outcome_improved_bool(row: dict[str, Any] | None) -> bool | None:
    if not row:
        return None
    oi = row.get("outcome_improved")
    if oi is None or str(oi).strip() in ("", "—"):
        return None
    b = _bool_from_yes(oi)
    if b is not None:
        return b
    t = str(oi).strip().upper()
    if t == "N/A":
        return None
    return None


def groundhog_state_d14(
    *,
    groundhog_active: bool,
    behavior_changed: bool,
    outcome_improved: bool | None,
) -> str:
    """
    D14 §2 classification. ``groundhog_active`` = retrieval / memory lane signal (see spec).
    """
    if not groundhog_active:
        return "COLD"
    if behavior_changed and outcome_improved is True:
        return "STRONG"
    if behavior_changed and outcome_improved is False:
        return "WEAK"
    if behavior_changed:
        return "ACTIVE"
    return "ACTIVE"


def aggregate_trades_for_job_id(job_id: str) -> dict[str, Any] | None:
    """
    Trade-level aggregates from ``batch_parallel_results_v1.json`` when present.
    Returns None if job or batch artifact missing.
    """
    jid = job_id.strip()
    entry = find_scorecard_entry_by_job_id(jid)
    if not entry:
        return None
    batch_dir_s = entry.get("session_log_batch_dir")
    batch_dir, scenarios, _err = build_scenario_list_for_batch(jid, batch_dir_s if isinstance(batch_dir_s, str) else None)
    if not batch_dir or not batch_dir.is_dir():
        return None
    payload = load_batch_parallel_results_v1(batch_dir)
    if not payload:
        return None
    flat_by_sid = {str(s.get("scenario_id") or ""): s for s in scenarios}
    opps = _trade_opportunities_from_payload(payload, flat_by_sid)
    wins = [x for x in opps if x["result"] == "WIN"]
    losses = [x for x in opps if x["result"] == "LOSS"]
    n = len(opps)
    wc, lc = len(wins), len(losses)

    def _avg(xs: list[dict[str, Any]]) -> float | None:
        if not xs:
            return None
        return round(sum(x["pnl"] for x in xs) / len(xs), 6)

    aw = _avg(wins)
    al = _avg(losses)
    wr = round(100.0 * wc / n, 4) if n > 0 else None
    exp = None
    if n > 0 and aw is not None and al is not None:
        exp = round((wc / n) * aw - (lc / n) * abs(al), 6)
    return {
        "total_trade_opportunities": n,
        "win_count": wc,
        "loss_count": lc,
        "win_rate_percent": wr,
        "avg_win_pnl": aw,
        "avg_loss_pnl": al,
        "expectancy_per_trade": exp,
    }


def enrich_student_panel_run_rows_d14(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge D14-demanded L1 aliases and, when possible, trade aggregates from batch artifacts.

    Preserves existing ``student_panel_run_row_v2`` keys; adds ``d14`` sub-object and top-level D14 aliases.
    """
    out: list[dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("run_id") or "")
        clone = dict(r)
        clone["schema"] = SCHEMA_RUN_ROW
        clone["timestamp_start"] = r.get("timestamp")
        entry = find_scorecard_entry_by_job_id(rid) if rid else None
        panel_row = _panel_run_row_for_job(rid) if rid else None
        gh_active = _entry_retrieval_positive(entry) if entry else False
        beh = _behavior_changed_bool(panel_row, entry) if entry else False
        oib = _outcome_improved_bool(panel_row)
        ghs = groundhog_state_d14(groundhog_active=gh_active, behavior_changed=beh, outcome_improved=oib)

        agg = aggregate_trades_for_job_id(rid) if rid else None
        d14_block: dict[str, Any] = {
            "run_id": rid,
            "timestamp_start": clone.get("timestamp_start"),
            "pattern": clone.get("pattern"),
            "evaluation_window": clone.get("evaluation_window"),
            "total_trade_opportunities": agg["total_trade_opportunities"] if agg else clone.get("total_trades"),
            "win_count": agg["win_count"] if agg else "data_gap",
            "loss_count": agg["loss_count"] if agg else "data_gap",
            "win_rate_percent": agg["win_rate_percent"] if agg else "data_gap",
            "avg_win_pnl": agg["avg_win_pnl"] if agg else "data_gap",
            "avg_loss_pnl": agg["avg_loss_pnl"] if agg else "data_gap",
            "expectancy_per_trade": agg["expectancy_per_trade"] if agg else clone.get("expectancy_per_trade"),
            "behavior_changed_flag": beh,
            "outcome_improved_flag": oib,
            "groundhog_state": ghs,
            "aggregate_source": "batch_parallel_results_v1" if agg else "data_gap_or_scorecard_only",
        }
        if agg is None and clone.get("total_trades") is not None:
            d14_block["total_trade_opportunities"] = clone.get("total_trades")
        clone["d14_run_row_v1"] = d14_block
        out.append(clone)
    return out


def _ms_to_utc_iso(ms: int) -> Any:
    if not ms:
        return _dg()
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError, TypeError):
        return _dg()


def trade_outcome_timestamp_utc(outcome_json: dict[str, Any]) -> Any:
    """Expose for L2 carousel: decision-time anchor from OutcomeRecord JSON (``entry_time`` ms)."""
    et = _int(outcome_json.get("entry_time"), 0)
    return _ms_to_utc_iso(et) if et else _dg()


def _student_action_from_so(so: dict[str, Any] | None) -> Any:
    if not isinstance(so, dict) or "act" not in so:
        return _dg()
    try:
        act = so.get("act")
        if act is True:
            return "ENTER"
        if act is False:
            return "NO_TRADE"
    except Exception:
        pass
    return _dg()


def build_student_decision_record_v1(job_id: str, trade_id: str) -> dict[str, Any] | None:
    """
    Single authoritative D14-shaped ``student_decision_record_v1`` (flat keys per architecture spec).

    Missing lineage exports are the string ``data_gap`` — never substituted across domains.
    """
    jid = job_id.strip()
    tid = trade_id.strip()
    if not jid or not tid:
        return None
    entry = find_scorecard_entry_by_job_id(jid)
    if not entry:
        return None
    batch_dir_s = entry.get("session_log_batch_dir")
    batch_dir, scenarios, _err = build_scenario_list_for_batch(jid, batch_dir_s if isinstance(batch_dir_s, str) else None)
    folder = ""
    if not batch_dir or not batch_dir.is_dir():
        return None

    payload = load_batch_parallel_results_v1(batch_dir)
    if not payload:
        return {
            "schema": SCHEMA_DECISION_RECORD,
            "ok": False,
            "error": "batch_parallel_results_v1_missing",
            "run_id": jid,
            "trade_id": tid,
            "graded_unit_id": tid,
            "data_gaps": ["batch_parallel_results_v1_missing"],
        }

    target_oj: dict[str, Any] | None = None
    scenario_id = ""
    for row in _ordered_parallel_rows(payload):
        if not row.get("ok"):
            continue
        for oj in row.get("replay_outcomes_json") or []:
            if isinstance(oj, dict) and str(oj.get("trade_id") or "").strip() == tid:
                target_oj = oj
                scenario_id = str(row.get("scenario_id") or "")
                break
        if target_oj is not None:
            break

    if not target_oj:
        return None

    for s in scenarios:
        if str(s.get("scenario_id") or "") == scenario_id:
            folder = str(s.get("folder") or "")
            break

    rr = load_run_record(batch_dir, folder) if folder else None
    rr = rr if isinstance(rr, dict) else {}

    store_p = default_student_learning_store_path_v1()
    sl_list = list_student_learning_records_by_graded_unit_id(store_p, tid)
    sl = sl_list[-1] if sl_list else None
    so = (sl.get("student_output") if isinstance(sl, dict) else None) or {}
    if not isinstance(so, dict):
        so = {}

    meta = target_oj.get("metadata") if isinstance(target_oj.get("metadata"), dict) else {}
    gaps: list[str] = []

    def _meta(key: str) -> Any:
        v = meta.get(key)
        return v if v is not None else _dg()

    # OHLC: structured or gap
    ohlc = meta.get("ohlc")
    po = ph = pl = pc = _dg()
    if isinstance(ohlc, dict):
        po = ohlc.get("open", _dg())
        ph = ohlc.get("high", _dg())
        pl = ohlc.get("low", _dg())
        pc = ohlc.get("close", _dg())
    elif ohlc is not None:
        po = ph = pl = pc = ohlc
    else:
        gaps.append("decision_time_ohlc_not_in_outcome_metadata")

    et = _int(target_oj.get("entry_time"), 0)
    ts = _ms_to_utc_iso(et) if et else _dg()

    pnl = _float(target_oj.get("pnl"))
    is_win = bool(pnl is not None and pnl > 0.0)
    is_loss = bool(pnl is not None and pnl <= 0.0)
    ref_out = "WIN" if is_win else "LOSS"

    student_direction = so.get("direction") or _dg()
    student_conf = so.get("confidence_01")
    if student_conf is None:
        student_conf = _dg()
        gaps.append("student_confidence_01_missing")

    job_pf = str(
        (entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or "")
    ).strip()
    if job_pf == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        if not isinstance(so, dict) or not so:
            gaps.append("student_directional_thesis_store_missing_for_llm_profile_v1")
        else:
            tv = validate_student_output_directional_thesis_required_for_llm_profile_v1(so)
            if tv:
                gaps.append("student_directional_thesis_incomplete_for_llm_profile_v1")

    def _so_thesis_field(key: str) -> Any:
        if not isinstance(so, dict):
            return _dg()
        v = so.get(key)
        return v if v is not None else _dg()

    def _so_thesis_list(key: str) -> Any:
        if not isinstance(so, dict):
            return _dg()
        v = so.get(key)
        return v if isinstance(v, list) else _dg()

    ctx_sig: Any = None
    if isinstance(sl, dict):
        ctx_sig = sl.get("context_signature_v1")
    sk = str(ctx_sig.get("signature_key") or "").strip() if isinstance(ctx_sig, dict) else ""
    ret_count: Any = _dg()
    if isinstance(sl, dict) and sk:
        ret_count = 1
    elif sl is None:
        gaps.append("student_store_record_missing_for_trade")

    gh_used: Any = _dg()
    if isinstance(sl, dict):
        gh_used = bool(sl.get("context_signature_v1") or sl.get("student_output"))

    ctx_f: Any = bool(sl) if sl else _dg()
    mem_f: Any = bool(isinstance(sl, dict) and sl.get("context_signature_v1")) if sl else _dg()

    influence = _dg()
    if isinstance(sl, dict) and sl.get("record_id"):
        influence = f"student_learning_record_v1:{sl.get('record_id')}"

    structured = {
        "context_factors_considered": _dg(),
        "pattern_candidates": _dg(),
        "pattern_selected": _dg(),
        "groundhog_influence": _dg(),
        "decision_basis_summary": _dg(),
        "baseline_difference_summary": _dg(),
    }

    tf = meta.get("timeframe")
    if tf is None and isinstance(rr, dict):
        tf = rr.get("timeframe")
    timeframe_val: Any = tf if tf is not None else _dg()
    if timeframe_val == _dg():
        gaps.append("timeframe_not_exported")

    gaps.append("structured_reasoning_export_not_wired")
    gaps.extend(
        [
            "per_trade_baseline_not_exported",
            "pattern_eval_per_trade_not_exported",
        ]
    )

    ema_f = meta.get("ema_fast") if "ema_fast" in meta else meta.get("ema")
    ema_s = meta.get("ema_slow")
    rsi_v = meta.get("rsi_14") if "rsi_14" in meta else meta.get("rsi")
    atr_v = meta.get("atr_14") if "atr_14" in meta else meta.get("atr")

    rec: dict[str, Any] = {
        "schema": SCHEMA_DECISION_RECORD,
        "run_id": jid,
        "trade_id": tid,
        "graded_unit_id": tid,
        "scenario_id": scenario_id if scenario_id else _dg(),
        "timestamp_utc": ts,
        "symbol": str(target_oj.get("symbol") or _dg()),
        "timeframe": timeframe_val,
        # Student
        "student_action": _student_action_from_so(so),
        "student_direction": student_direction,
        "student_confidence_01": student_conf,
        "student_confidence_band": _so_thesis_field("confidence_band"),
        "student_action_v1": _so_thesis_field("student_action_v1"),
        "student_supporting_indicators": _so_thesis_list("supporting_indicators"),
        "student_conflicting_indicators": _so_thesis_list("conflicting_indicators"),
        "student_context_fit": _so_thesis_field("context_fit"),
        "student_invalidation_text": _so_thesis_field("invalidation_text"),
        "student_reasoning_text": _so_thesis_field("reasoning_text"),
        # Baseline
        "baseline_action": _dg(),
        "baseline_direction": _dg(),
        "baseline_confidence_01": _dg(),
        "decision_changed_flag": _dg(),
        # Context (decision-time — only from export)
        "price_open": po,
        "price_high": ph,
        "price_low": pl,
        "price_close": pc,
        "ema_fast": ema_f if ema_f is not None else _dg(),
        "ema_slow": ema_s if ema_s is not None else _dg(),
        "rsi_14": rsi_v if rsi_v is not None else _dg(),
        "atr_14": atr_v if atr_v is not None else _dg(),
        "volume": _meta("volume"),
        "trend_state": _meta("trend_state"),
        "volatility_regime": _meta("volatility_regime"),
        "structure_state": _meta("structure_state"),
        # Groundhog
        "groundhog_used_flag": gh_used,
        "context_used_flag": ctx_f,
        "memory_used_flag": mem_f,
        "retrieval_count": ret_count,
        "retrieval_signature_key": sk if sk else _dg(),
        "influence_summary": influence,
        # Pattern
        "pattern_selected": _dg(),
        "patterns_evaluated": _dg(),
        "pattern_pass_fail_summary": _dg(),
        # Referee
        "referee_actual_trade": 1,
        "referee_direction": str(target_oj.get("direction") or _dg()),
        "referee_outcome": ref_out,
        "referee_pnl": pnl if pnl is not None else _dg(),
        # Flags
        "is_win": is_win,
        "is_loss": is_loss,
        # D14-5
        "structured_reasoning_v1": structured,
        # Audit
        "data_gaps": sorted(set(gaps)),
        "run_record_path_resolved": bool(rr),
    }
    return rec


__all__ = [
    "aggregate_trades_for_job_id",
    "build_student_decision_record_v1",
    "enrich_student_panel_run_rows_d14",
    "groundhog_state_d14",
    "trade_outcome_timestamp_utc",
]
