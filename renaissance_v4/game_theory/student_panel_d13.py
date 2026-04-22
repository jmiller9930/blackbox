"""
D13 — Student panel at trade grain (``graded_unit_id`` / ``trade_id``).

Slide = one trade opportunity. Run summary + carousel share one L2 panel; deep dive is L3 per trade.

See ``renaissance_v4/game_theory/docs/D13_student_panel_curriculum_v1.md``.
"""

from __future__ import annotations

from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_batch_parallel_results_v1,
)
from renaissance_v4.game_theory.student_panel_d11 import (
    SCHEMA_RUN_ROW,
    _evaluation_window_label,
    _groundhog_active_for_d11,
    _pattern_label,
    build_d11_run_rows_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    default_student_learning_store_path_v1,
    load_student_learning_records_v1,
)

SCHEMA_SELECTED_RUN = "student_panel_d13_selected_run_v1"
SCHEMA_DECISION_RECORD = "student_decision_record_v1"
SCHEMA_CAROUSEL_SLICE = "student_panel_trade_slice_v1"


def _bool_from_yes(s: Any) -> bool | None:
    if s is None:
        return None
    t = str(s).strip().upper()
    if t in ("YES", "TRUE", "1"):
        return True
    if t in ("NO", "FALSE", "0"):
        return False
    return None


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _panel_run_row_for_job(job_id: str) -> dict[str, Any] | None:
    """Reuse D11 rollups so run-summary flags match the run table."""
    jid = job_id.strip()
    if not jid:
        return None
    raw = read_batch_scorecard_recent(500, path=default_batch_scorecard_jsonl())
    clean = [x for x in raw if not str(x.get("_inflight", "")).lower() == "true"]
    rows = build_d11_run_rows_v1(clean)
    for r in rows:
        if str(r.get("run_id")) == jid:
            return r
    return None


def _ordered_parallel_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    order = payload.get("scenario_order")
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    if not isinstance(order, list) or not order:
        return list(results)
    by_sid: dict[str, dict[str, Any]] = {}
    for r in results:
        if isinstance(r, dict):
            by_sid[str(r.get("scenario_id") or "")] = r
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sid in order:
        s = str(sid)
        if s in by_sid:
            out.append(by_sid[s])
            seen.add(s)
    for r in results:
        if isinstance(r, dict) and str(r.get("scenario_id") or "") not in seen:
            out.append(r)
    return out


def _slice_groundhog_usage_scenario_level(flat: dict[str, Any]) -> str:
    """Same heuristic as D11 scenario slice (batch folder), for single-trade scenarios."""
    mem = bool(flat.get("memory_applied"))
    ghe = bool(flat.get("groundhog_env_enabled"))
    gh_mode = str(flat.get("groundhog_mode") or "")
    if mem and ghe:
        return "ctx+mem"
    if gh_mode and gh_mode.lower() not in ("", "none", "inactive"):
        return "ctx+mem"
    if mem or ghe:
        return "ctx"
    return "none"


def _trade_opportunities_from_payload(
    payload: dict[str, Any],
    flat_by_scenario: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = _ordered_parallel_rows(payload)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("ok"):
            continue
        sid = str(row.get("scenario_id") or "")
        flat = flat_by_scenario.get(sid) or {}
        scen_n = len(row.get("replay_outcomes_json") or [])
        for oj in row.get("replay_outcomes_json") or []:
            if not isinstance(oj, dict):
                continue
            tid = str(oj.get("trade_id") or "").strip()
            if not tid:
                continue
            pnl = float(oj.get("pnl") or 0.0)
            out.append(
                {
                    "trade_id": tid,
                    "scenario_id": sid,
                    "scenario_trade_count": scen_n,
                    "outcome_json": oj,
                    "scenario_flat": flat,
                    "parallel_row": row,
                    "pnl": pnl,
                    "result": "WIN" if pnl > 0.0 else "LOSS",
                }
            )
    return out


def _entry_retrieval_positive(entry: dict[str, Any]) -> bool:
    recall = _int(entry.get("recall_matches"), 0)
    stud = _int(entry.get("student_retrieval_matches"), 0)
    mci = entry.get("memory_context_impact_audit_v1")
    mem_yes = isinstance(mci, dict) and mci.get("memory_impact_yes_no") == "YES"
    return bool(recall > 0 or stud > 0 or mem_yes or _groundhog_active_for_d11(entry))


def _behavior_changed_bool_for_d13(
    row: dict[str, Any] | None,
    entry: dict[str, Any],
) -> bool:
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


def _confidence_from_student_output(so: dict[str, Any] | None) -> Any:
    if not isinstance(so, dict):
        return "data_gap"
    c = so.get("confidence_01")
    if c is None:
        return "data_gap"
    return c


def _direction_from_student_output(so: dict[str, Any] | None) -> Any:
    if not isinstance(so, dict):
        return "data_gap"
    d = so.get("direction")
    if not d:
        return "data_gap"
    return d


def build_d13_selected_run_payload_v1(job_id: str) -> dict[str, Any]:
    """
    L2 payload: one **run_summary** row object + **slices** (carousel) keyed by ``trade_id``.

    When ``batch_parallel_results_v1.json`` is missing (older batches), carousel may be empty;
    ``data_gaps`` explains the gap.
    """
    from renaissance_v4.game_theory.student_panel_d14 import (  # noqa: PLC0415 — avoid circular import
        groundhog_state_d14,
        trade_outcome_timestamp_utc,
    )

    jid = job_id.strip()
    entry = find_scorecard_entry_by_job_id(jid)
    if not entry:
        return {"ok": False, "error": "job_id not in scorecard", "schema": SCHEMA_SELECTED_RUN}

    batch_dir_s = entry.get("session_log_batch_dir")
    batch_dir, scenarios, scen_err = build_scenario_list_for_batch(jid, batch_dir_s if isinstance(batch_dir_s, str) else None)
    flat_by_sid = {str(s.get("scenario_id") or ""): s for s in scenarios}

    payload = load_batch_parallel_results_v1(batch_dir) if batch_dir and batch_dir.is_dir() else None
    gaps: list[str] = []
    if payload is None:
        gaps.append("batch_parallel_results_v1_missing_tradeenumeration_requires_new_batch")

    opportunities: list[dict[str, Any]] = []
    if payload:
        opportunities = _trade_opportunities_from_payload(payload, flat_by_sid)

    def _opp_entry_time_ms(opp: dict[str, Any]) -> int:
        oj = opp.get("outcome_json")
        if not isinstance(oj, dict):
            return 0
        return _int(oj.get("entry_time"), 0)

    opportunities.sort(key=_opp_entry_time_ms)

    panel_row = _panel_run_row_for_job(jid)
    entry_for_flags = entry
    gh_lane = _groundhog_active_for_d11(entry_for_flags)
    beh_bool = _behavior_changed_bool_for_d13(panel_row, entry_for_flags)
    oib = _outcome_improved_bool(panel_row)

    wins = [x for x in opportunities if x["result"] == "WIN"]
    losses = [x for x in opportunities if x["result"] == "LOSS"]
    n = len(opportunities)
    wc, lc = len(wins), len(losses)
    wr = round(100.0 * wc / n, 4) if n > 0 else None

    def _avg_pnl(xs: list[dict[str, Any]]) -> float | None:
        if not xs:
            return None
        return round(sum(x["pnl"] for x in xs) / len(xs), 6)

    avg_win = _avg_pnl(wins)
    avg_loss = _avg_pnl(losses)
    exp = None
    if n > 0 and avg_win is not None and avg_loss is not None:
        exp = round((wc / n) * avg_win - (lc / n) * abs(avg_loss), 6)

    gh_state = groundhog_state_d14(
        groundhog_active=gh_lane,
        behavior_changed=beh_bool,
        outcome_improved=oib,
    )
    retrieval_pos = _entry_retrieval_positive(entry_for_flags)
    ctx_used = retrieval_pos or bool(_int(entry.get("recall_matches"), 0) or _int(entry.get("student_retrieval_matches"), 0))
    mem_used = bool(_int(entry.get("student_learning_rows_appended"), 0) or _int(entry.get("recall_matches"), 0))

    store_p = default_student_learning_store_path_v1()
    # One JSONL scan for the whole carousel — ``list_student_learning_records_by_graded_unit_id``
    # reloads the entire store per trade and times out the L2 HTTP handler on ~hundreds of trades.
    by_graded_unit: dict[str, list[dict[str, Any]]] = {}
    for d in load_student_learning_records_v1(store_p):
        gid = str(d.get("graded_unit_id", "")).strip()
        if gid:
            by_graded_unit.setdefault(gid, []).append(d)

    slices: list[dict[str, Any]] = []
    for i, t in enumerate(opportunities):
        tid = t["trade_id"]
        oj = t["outcome_json"]
        flat = t["scenario_flat"]
        scen_n = int(t.get("scenario_trade_count") or 0)
        ts_utc = trade_outcome_timestamp_utc(oj)

        sl_list = by_graded_unit.get(tid, [])
        sl = sl_list[-1] if sl_list else None
        so = (sl.get("student_output") if isinstance(sl, dict) else None) or None
        conf = _confidence_from_student_output(so if isinstance(so, dict) else None)
        sdir = _direction_from_student_output(so if isinstance(so, dict) else None)

        if scen_n <= 1 and flat:
            ghu = _slice_groundhog_usage_scenario_level(flat)
        elif sl:
            ghu = "ctx+mem" if sl.get("context_signature_v1") else "ctx"
        else:
            ghu = "data_gap"

        dir_disp: Any = sdir if sdir != "data_gap" else str(oj.get("direction") or "data_gap")

        # Baseline-not-wired in v1 — do not infer Δ vs Referee as "baseline".
        dcf: Any = "data_gap"

        ref_out = "WIN" if t["result"] == "WIN" else "LOSS"
        slices.append(
            {
                "schema": SCHEMA_CAROUSEL_SLICE,
                "trade_id": tid,
                "graded_unit_id": tid,
                "timestamp_utc": ts_utc,
                "timestamp": ts_utc,
                "student_direction": dir_disp,
                "student_confidence_01": conf,
                "referee_outcome": ref_out,
                "groundhog_usage_label": ghu,
                "decision_changed_flag": dcf,
                "direction": dir_disp,
                "confidence": conf,
                "result": ref_out,
                "groundhog_usage": ghu,
                "order_index": i,
            }
        )

    run_summary = {
        "run_id": jid,
        "pattern": _pattern_label(entry),
        "evaluation_window": _evaluation_window_label(entry),
        "total_trade_opportunities": n,
        "win_count": wc,
        "loss_count": lc,
        "win_rate_percent": wr,
        "avg_win_pnl": avg_win,
        "avg_loss_pnl": avg_loss,
        "expectancy_per_trade": exp,
        "behavior_changed_flag": beh_bool,
        "outcome_improved_flag": oib,
        "groundhog_state": gh_state,
        "context_used_flag": ctx_used,
        "memory_used_flag": mem_used,
        "panel_run_row_schema": SCHEMA_RUN_ROW,
    }

    return {
        "ok": True,
        "schema": SCHEMA_SELECTED_RUN,
        "run_id": jid,
        "run_summary": run_summary,
        "slices": slices,
        "slice_ordering": "trade_opportunities_entry_time_asc",
        "grain": "trade_id",
        "scenario_list_error": scen_err,
        "data_gaps": gaps,
        "note": (
            "Carousel and deep dive use trade_id / graded_unit_id. scenario_id is batch grouping only — "
            "never the carousel slice identity."
        ),
    }


def build_student_decision_record_v1(job_id: str, trade_id: str) -> dict[str, Any] | None:
    """Delegates to :mod:`student_panel_d14` (canonical D14 flat contract)."""
    from renaissance_v4.game_theory import student_panel_d14 as _d14  # noqa: PLC0415

    return _d14.build_student_decision_record_v1(job_id, trade_id)


__all__ = [
    "SCHEMA_CAROUSEL_SLICE",
    "SCHEMA_DECISION_RECORD",
    "SCHEMA_SELECTED_RUN",
    "build_d13_selected_run_payload_v1",
    "build_student_decision_record_v1",
]
