"""
D11 — Student panel API: run index (Referee replay rollups + harness deltas) and drilldown payloads.

Rows are built from ``batch_scorecard.jsonl`` (and in-flight jobs on the server). Referee facts live
in the scorecard; Student-specific truth per decision is deep-dive when present. Missing wiring is
``data_gaps``, not mixed into Referee columns.
"""

from __future__ import annotations

import hashlib
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent
from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl
from renaissance_v4.game_theory.scorecard_drill import (
    build_scenario_list_for_batch,
    find_scorecard_entry_by_job_id,
    load_run_record,
)
from renaissance_v4.game_theory.student_panel_l1_road_v1 import line_e_value_for_l1_v1
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    default_student_learning_store_path_v1,
    list_student_learning_records_by_run_id,
)

SCHEMA_RUN_ROW = "student_panel_run_row_v2"
SCHEMA_DECISION_SLICE = "student_panel_decision_slice_v1"
SCHEMA_DECISION_RECORD = "student_decision_record_v3"


def _float(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _started_ts(row: dict[str, Any]) -> str:
    return str(row.get("started_at_utc") or row.get("ended_at_utc") or "")


def _fingerprint_from_scorecard_line(row: dict[str, Any]) -> str | None:
    mci = row.get("memory_context_impact_audit_v1")
    if isinstance(mci, dict):
        fp = mci.get("run_config_fingerprint_sha256_40")
        if fp:
            return str(fp).strip()
    oba = row.get("operator_batch_audit")
    if isinstance(oba, dict):
        parts = [
            str(oba.get("operator_recipe_id") or ""),
            str(oba.get("evaluation_window_effective_calendar_months") or ""),
            str(oba.get("manifest_path_primary") or ""),
            str(oba.get("policy_framework_id") or ""),
        ]
        blob = "\n".join(parts)
        if blob.strip():
            # short stable key when MCI fingerprint is missing in older rows
            return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:40]
    return None


def _pattern_label(row: dict[str, Any]) -> str:
    oba = row.get("operator_batch_audit")
    if isinstance(oba, dict):
        for k in ("operator_recipe_label", "operator_recipe_id"):
            v = oba.get(k)
            if v:
                return str(v)
    la = row.get("learning_audit_v1")
    if isinstance(la, dict):
        pf = la.get("policy_framework_id")
        if pf:
            return str(pf)
    return "—"


def _evaluation_window_label(row: dict[str, Any]) -> str:
    oba = row.get("operator_batch_audit")
    if isinstance(oba, dict):
        m = oba.get("evaluation_window_effective_calendar_months")
        if m is not None:
            return f"{m} mo"
    la = row.get("learning_audit_v1")
    if isinstance(la, dict):
        ew = la.get("evaluation_window")
        if isinstance(ew, dict):
            cm = ew.get("calendar_months")
            if cm is not None:
                return f"{cm} mo"
    return "—"


def _groundhog_active_for_d11(row: dict[str, Any]) -> bool:
    """
    Directive tiers require "Groundhog active" — v1 treats canonical bundle lane **or** harness
    memory/recall/Student retrieval as active for attribution (see panel legend).
    """
    gs = str(row.get("groundhog_status") or "").strip().lower()
    gh_lane = bool(gs and gs not in ("inactive", "none", ""))
    recall = _int(row.get("recall_matches"), 0)
    stud_ret = _int(row.get("student_retrieval_matches"), 0)
    mci = row.get("memory_context_impact_audit_v1")
    mem_yes = isinstance(mci, dict) and mci.get("memory_impact_yes_no") == "YES"
    return bool(gh_lane or recall > 0 or stud_ret > 0 or mem_yes)


def _harness_behavior_changed(row: dict[str, Any]) -> str:
    """
    Replay/harness path only (memory bundle, recall, bias) — **not** Student store writes.
    """
    mci = row.get("memory_context_impact_audit_v1")
    if isinstance(mci, dict) and mci.get("memory_impact_yes_no") == "YES":
        return "YES"
    if _int(row.get("recall_matches"), 0) > 0:
        return "YES"
    if _int(row.get("recall_bias_applied"), 0) > 0:
        return "YES"
    if _int(row.get("signal_bias_applied_count"), 0) > 0:
        return "YES"
    return "NO"


def _student_handoff_signal(row: dict[str, Any]) -> str:
    """Directive 09 / Student store: YES if rows were appended or retrieval matched."""
    if _int(row.get("student_learning_rows_appended"), 0) > 0:
        return "YES"
    if _int(row.get("student_retrieval_matches"), 0) > 0:
        return "YES"
    return "NO"


def _behavior_changed_legacy_union(row: dict[str, Any]) -> str:
    """Deprecated single flag = YES if either harness or Student handoff fired (compat only)."""
    if _harness_behavior_changed(row) == "YES":
        return "YES"
    if _student_handoff_signal(row) == "YES":
        return "YES"
    return "NO"


def _batch_trade_win_pct_from_line(row: dict[str, Any] | None) -> float | None:
    """Referee batch rollup trade win % (0–100) from one scorecard line."""
    if not row:
        return None
    btw = row.get("batch_trade_win_pct")
    if btw is None:
        btw = row.get("avg_trade_win_pct")
    try:
        return float(btw) if btw is not None else None
    except (TypeError, ValueError):
        return None


def _expectancy_per_trade_for_row(row: dict[str, Any]) -> tuple[float | None, str | None]:
    """
    Prefer batch rollup expectancy; optional formula cross-check when batch trade stats exist.
    Directive: E = (WR×AvgWin) − (LR×AvgLoss). Rollup ``expectancy_per_trade`` is already from ledger math.
    """
    e = row.get("expectancy_per_trade")
    if e is not None:
        try:
            return round(float(e), 6), None
        except (TypeError, ValueError):
            pass
    btp = _float(row.get("batch_trade_win_pct"))
    wlr = _float(row.get("win_loss_size_ratio"))
    if btp is not None and wlr is not None and wlr >= 0:
        wr = max(0.0, min(1.0, btp / 100.0))
        lr = max(0.0, min(1.0, 1.0 - wr))
        # scale-free: set AvgLoss = 1, AvgWin = wlr
        e2 = wr * wlr - lr * 1.0
        return round(e2, 6), "scaled_from_batch_trade_win_pct_and_wlr"
    return None, "missing_expectancy_inputs"


def _fp_tail(v: Any, n: int = 12) -> str | None:
    s = str(v or "").strip()
    if not s:
        return None
    return s[-n:] if len(s) >= n else s


def _build_evidence_v1(row: dict[str, Any]) -> dict[str, Any]:
    """Nested evidence for control — Referee vs harness vs Student handoff (no merged semantics)."""
    exp, _exp_gap = _expectancy_per_trade_for_row(row)
    btc = _int(row.get("batch_trades_count"), 0)
    btw = row.get("batch_trade_win_pct")
    if btw is None:
        btw = row.get("avg_trade_win_pct")
    wr = None
    try:
        wr = float(btw) if btw is not None else None
    except (TypeError, ValueError):
        pass
    hb = _harness_behavior_changed(row)
    sh = _student_handoff_signal(row)
    rows_n = _int(row.get("student_learning_rows_appended"), 0)
    retr_n = _int(row.get("student_retrieval_matches"), 0)
    mci = row.get("memory_context_impact_audit_v1")
    mem_imp = mci.get("memory_impact_yes_no") if isinstance(mci, dict) else None
    return {
        "referee": {
            "total_trades": btc,
            "trade_win_percent": wr,
            "expectancy_per_trade": exp,
        },
        "harness": {
            "behavior_changed": hb,
            "memory_impact_yes_no": mem_imp,
            "recall_matches": _int(row.get("recall_matches"), 0),
            "recall_bias_applied": _int(row.get("recall_bias_applied"), 0),
            "signal_bias_applied_count": _int(row.get("signal_bias_applied_count"), 0),
        },
        "student_handoff": {
            "active": sh,
            "rows_appended": rows_n,
            "retrieval_matches": retr_n,
            "output_fingerprint_tail": _fp_tail(row.get("student_output_fingerprint")),
        },
    }


def _groundhog_state_d11(
    *,
    gh_active: bool,
    behavior: str,
    outcome: str,
) -> str:
    if not gh_active:
        return "COLD"
    if behavior != "YES":
        return "COLD"
    if outcome == "YES":
        return "STRONG"
    if outcome == "NO":
        return "WEAK"
    if outcome == "N/A":
        return "ACTIVE"
    return "ACTIVE"


def _groundhog_state_for_row(
    *,
    is_running: bool,
    is_first_in_fingerprint_chain: bool,
    gh_active: bool,
    behavior: str,
    outcome: str,
) -> str:
    """First run in a fingerprint chain has no prior paired batch — Groundhog/learning delta is N/A."""
    if is_running:
        return "RUNNING"
    if is_first_in_fingerprint_chain:
        return "N/A"
    return _groundhog_state_d11(
        gh_active=gh_active, behavior=behavior, outcome=outcome
    )


def build_d11_run_rows_v1(
    entries_newest_first: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    One row per scorecard line (learning run). ``entries_newest_first`` same order as ``read_batch_scorecard_recent``.

    **System baseline trade win %:** the **first (oldest) completed run** in the same
    ``run_config_fingerprint`` chain — frozen anchor for that recipe/window. **Run trade win %** is
    this line's batch rollup. ``beats_system_baseline_trade_win`` is YES/NO when this row is not
    the anchor and both percents exist (strict ``run > baseline``).
    """
    if not entries_newest_first:
        return []
    chronological = list(reversed(entries_newest_first))
    by_fp: dict[str, list[dict[str, Any]]] = {}
    for r in chronological:
        if str(r.get("status") or "") == "running" or r.get("scorecard_inflight"):
            continue
        fp = _fingerprint_from_scorecard_line(r) or "__no_fp__"
        by_fp.setdefault(fp, []).append(r)

    out: list[dict[str, Any]] = []
    for r in chronological:
        fp = _fingerprint_from_scorecard_line(r) or "__no_fp__"
        prev_same: dict[str, Any] | None = None
        chain = by_fp.get(fp) or []
        for i, x in enumerate(chain):
            if x is r and i > 0:
                prev_same = chain[i - 1]
                break

        job_id = str(r.get("job_id") or "")
        st = str(r.get("status") or "")
        is_running = st == "running" or bool(r.get("scorecard_inflight"))

        if is_running:
            row_obj: dict[str, Any] = {
                "schema": SCHEMA_RUN_ROW,
                "run_id": job_id,
                "timestamp": _started_ts(r),
                "pattern": _pattern_label(r),
                "evaluation_window": _evaluation_window_label(r),
                "total_trades": None,
                "harness_baseline_trade_win_percent": None,
                "run_trade_win_percent": None,
                "beats_system_baseline_trade_win": "—",
                "expectancy_per_trade": None,
                "harness_behavior_changed": "—",
                "student_handoff_active": "—",
                "behavior_changed": "—",
                "evidence": None,
                "outcome_improved": "—",
                "groundhog_state": "RUNNING",
                "run_progress": (
                    f"{_int(r.get('total_processed'), 0)}/{_int(r.get('total_scenarios'), 0)}"
                ),
                "is_inflight": True,
                "data_gaps": [],
                "status": "running",
                "fingerprint": _fingerprint_from_scorecard_line(r),
                "baseline_run_id": None,
                "exam_e_score_v1": None,
                "exam_p_score_v1": None,
                "exam_pass_v1": None,
                "l1_e_value_source_v1": None,
                "l1_p_value_source_v1": None,
            }
            out.append(row_obj)
            continue

        if st == "error":
            exp, exp_gap = None, "batch_status_error"
        else:
            exp, exp_gap = _expectancy_per_trade_for_row(r)

        btc = _int(r.get("batch_trades_count"), 0)
        win_rate_p = _batch_trade_win_pct_from_line(r)
        anchor_r = chain[0] if chain else None
        baseline_p = _batch_trade_win_pct_from_line(anchor_r)
        is_anchor = bool(chain) and anchor_r is r
        beats_bl: str
        if is_anchor or baseline_p is None or win_rate_p is None:
            beats_bl = "—"
        elif win_rate_p > baseline_p + 1e-9:
            beats_bl = "YES"
        elif win_rate_p < baseline_p - 1e-9:
            beats_bl = "NO"
        else:
            beats_bl = "="

        harness_beh = _harness_behavior_changed(r)
        stud_hand = _student_handoff_signal(r)
        legacy_beh = _behavior_changed_legacy_union(r)
        outcome_imp: str
        e_cur = line_e_value_for_l1_v1(r)
        e_prev = line_e_value_for_l1_v1(prev_same) if prev_same else None
        if prev_same is None:
            outcome_imp = "N/A"
        elif e_cur is None or e_prev is None:
            outcome_imp = "N/A"
        else:
            if e_cur > e_prev:
                outcome_imp = "YES"
            elif e_cur < e_prev:
                outcome_imp = "NO"
            else:
                outcome_imp = "NO"

        gh_active = _groundhog_active_for_d11(r)
        first_in_chain = prev_same is None
        ghs = _groundhog_state_for_row(
            is_running=False,
            is_first_in_fingerprint_chain=first_in_chain,
            gh_active=gh_active,
            behavior=harness_beh,
            outcome=outcome_imp,
        )

        row_obj = {
            "schema": SCHEMA_RUN_ROW,
            "run_id": job_id,
            "timestamp": _started_ts(r),
            "pattern": _pattern_label(r),
            "evaluation_window": _evaluation_window_label(r),
            "total_trades": btc,
            # Fingerprint anchor (oldest run in same config) — system BL% for "beat baseline" story.
            "harness_baseline_trade_win_percent": baseline_p,
            "run_trade_win_percent": win_rate_p,
            "beats_system_baseline_trade_win": beats_bl,
            "expectancy_per_trade": exp,
            "harness_behavior_changed": harness_beh,
            "student_handoff_active": stud_hand,
            "behavior_changed": legacy_beh,
            "evidence": _build_evidence_v1(r),
            "outcome_improved": outcome_imp,
            "groundhog_state": ghs,
            "run_progress": None,
            "is_inflight": False,
            "data_gaps": [x for x in [exp_gap] if x],
            "status": st,
            "fingerprint": _fingerprint_from_scorecard_line(r),
            "baseline_run_id": str(prev_same.get("job_id")) if prev_same else None,
            "exam_e_score_v1": r.get("exam_e_score_v1"),
            "exam_p_score_v1": r.get("exam_p_score_v1"),
            "exam_pass_v1": r.get("exam_pass_v1"),
            "l1_e_value_source_v1": r.get("l1_e_value_source_v1"),
            "l1_p_value_source_v1": r.get("l1_p_value_source_v1"),
        }
        out.append(row_obj)

    return list(reversed(out))


def fetch_d11_run_rows_v1(*, limit: int = 50) -> list[dict[str, Any]]:
    """File-only rows (no in-memory inflight merge). Prefer ``api_student_panel_runs`` merge on server."""
    lim = max(1, min(200, limit))
    raw = read_batch_scorecard_recent(lim, path=default_batch_scorecard_jsonl())
    clean = [x for x in raw if not str(x.get("_inflight", "")).lower() == "true"]
    return build_d11_run_rows_v1(clean)


def _ref_direction_from_labels(ol: dict[str, Any] | None) -> str:
    if not isinstance(ol, dict):
        return "NONE"
    for k in ("direction_bias", "bias_direction", "direction"):
        v = ol.get(k)
        if isinstance(v, str) and v.strip():
            u = v.strip().upper()
            if "LONG" in u or u == "L":
                return "LONG"
            if "SHORT" in u or u == "S":
                return "SHORT"
    return "NONE"


def _slice_from_flat_scenario(flat: dict[str, Any]) -> dict[str, Any]:
    rs = str(flat.get("referee_session") or "").upper()
    if rs == "WIN":
        result = "WIN"
    elif rs == "LOSS":
        result = "LOSS"
    else:
        tr = _int(flat.get("trades"), 0)
        result = "NO_TRADE" if tr <= 0 else "LOSS"
    ol = flat.get("operator_labels")
    direction = _ref_direction_from_labels(ol if isinstance(ol, dict) else None)
    mem = bool(flat.get("memory_applied"))
    ghe = bool(flat.get("groundhog_env_enabled"))
    gh_mode = str(flat.get("groundhog_mode") or "")
    if mem and ghe:
        ghu = "ctx+mem"
    elif gh_mode and gh_mode.lower() not in ("", "none", "inactive"):
        ghu = "ctx+mem"
    elif mem or ghe:
        ghu = "ctx"
    else:
        ghu = "none"
    return {
        "schema": SCHEMA_DECISION_SLICE,
        "decision_id": str(flat.get("scenario_id") or flat.get("folder") or ""),
        "timestamp": None,
        "result": result,
        "direction": direction,
        "confidence": None,
        "confidence_gap": "not_exported",
        "groundhog_usage": ghu,
        "decision_changed_flag": None,
        "decision_changed_gap": "not_wired",
    }


def build_d11_decision_strip_payload_v1(job_id: str) -> dict[str, Any]:
    entry = find_scorecard_entry_by_job_id(job_id)
    if not entry:
        return {"ok": False, "error": "job_id not in scorecard", "slices": []}
    _bd, scenarios, err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
    slices = [_slice_from_flat_scenario(s) for s in scenarios]
    return {
        "ok": True,
        "run_id": job_id,
        "scenario_list_error": err,
        "slice_ordering": "scenario_slices_in_batch_order",
        "slice_ordering_note": (
            "Slices follow batch README / folder discovery order — not a canonical exam sequence "
            "or guaranteed trade-by-trade timeline unless the batch manifest enforces it."
        ),
        "slices": slices,
        "data_gaps": (
            [
                "decision_changed_flag_not_wired",
                "confidence_not_exported_per_slice",
            ]
            if slices
            else ["no_scenario_rows"]
        ),
    }


def build_student_decision_record_v1(
    job_id: str,
    decision_id: str,
) -> dict[str, Any] | None:
    entry = find_scorecard_entry_by_job_id(job_id)
    if not entry:
        return None
    batch_dir, scenarios, _err = build_scenario_list_for_batch(job_id, entry.get("session_log_batch_dir"))
    if not batch_dir or not batch_dir.is_dir():
        return None
    target = None
    for s in scenarios:
        sid = str(s.get("scenario_id") or s.get("folder") or "")
        if sid == decision_id:
            target = s
            break
    if not target:
        return None
    folder = str(target.get("folder") or "")
    rr = load_run_record(batch_dir, folder) if folder else None

    ref = (rr or {}).get("referee") if isinstance(rr, dict) else {}
    ref = ref if isinstance(ref, dict) else {}
    summ = ref.get("summary") if isinstance(ref.get("summary"), dict) else {}
    lme = (rr or {}).get("learning_memory_evidence") if isinstance(rr, dict) else {}
    lme = lme if isinstance(lme, dict) else {}
    da = (rr or {}).get("decision_audit") if isinstance(rr, dict) else {}
    da = da if isinstance(da, dict) else {}
    icq = (rr or {}).get("indicator_context_quality") if isinstance(rr, dict) else None

    action = "ENTER" if _int(ref.get("trades"), 0) > 0 else "NO_TRADE"
    ol = target.get("operator_labels")
    direction = _ref_direction_from_labels(ol if isinstance(ol, dict) else None)

    rr_dict = rr if isinstance(rr, dict) else {}
    la = rr_dict.get("learning_run_audit_v1")
    if not isinstance(la, dict):
        la = None

    sl_count = 0
    sl_sample: list[str] = []
    store_path_s = ""
    try:
        store_p = default_student_learning_store_path_v1()
        store_path_s = str(store_p)
        sl_rows = list_student_learning_records_by_run_id(store_p, job_id)
        sl_count = len(sl_rows)
        for doc in sl_rows[:5]:
            rid = doc.get("record_id") if isinstance(doc, dict) else None
            if isinstance(rid, str) and rid.strip():
                sl_sample.append(rid.strip())
    except OSError:
        pass

    gaps = [
        "confidence_not_in_run_record",
        "baseline_decision_not_wired",
        "pattern_evaluation_stub",
    ]

    rec: dict[str, Any] = {
        "schema": SCHEMA_DECISION_RECORD,
        "decision_time": str((rr or {}).get("utc") or target.get("run_id") or ""),
        "run_id": job_id,
        "decision_id": decision_id,
        "decision": {
            "action": action,
            "direction": direction,
            "confidence": None,
        },
        "context": {
            "price": summ.get("average_pnl"),
            "indicators": "see scenario manifest / run_record.summary",
            "structure": icq if icq is not None else None,
        },
        "pattern_evaluation": {
            "patterns_tested": [],
            "note": "Per-decision pattern checklist not exported in run_record v1 — use HUMAN_READABLE.md / harness.",
            "export_status": "not_exported",
        },
        "groundhog": {
            "used": "YES" if target.get("memory_applied") else "NO",
            "retrieval_count": None,
            "summary_of_influence": _str_or_none(lme.get("narrative") or lme.get("operator_note")) or "—",
        },
        "baseline_comparison": {
            "baseline_decision": "—",
            "current_decision": f"{action} {direction}",
            "changed": "—",
        },
        "referee": {
            "actual_trade": _int(ref.get("trades"), 0),
            "outcome": str(target.get("referee_session") or "N/A"),
            "pnl": ref.get("cumulative_pnl"),
        },
        "learning_run_audit_v1": la,
        "student_learning_store": {
            "path": store_path_s,
            "records_for_run_count": sl_count,
            "record_id_sample": sl_sample,
            "scope": "run_scoped",
        },
        "evidence_scope_v1": {
            "referee_and_run_record": "scenario_folder",
            "learning_run_audit_v1": "scenario_when_present_on_run_record",
            "student_learning_store": "run_scoped_not_slice_scoped",
            "baseline_comparison": "not_fully_implemented",
            "pattern_evaluation": "not_exported",
            "decision_change_attribution": "not_fully_implemented",
        },
        "data_gaps": gaps,
    }
    return rec


__all__ = [
    "SCHEMA_RUN_ROW",
    "SCHEMA_DECISION_SLICE",
    "SCHEMA_DECISION_RECORD",
    "build_d11_run_rows_v1",
    "fetch_d11_run_rows_v1",
    "build_d11_decision_strip_payload_v1",
    "build_student_decision_record_v1",
]
