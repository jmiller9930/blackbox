"""
learning_run_audit_v1 — operator-visible proof of what replay + learning mechanisms did.

Structured audit answers: execution-only vs learning-engaged, bars/windows, memory, Groundhog,
recall/bias counts, optional candidate-search outcome, and outcome-quality economics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.groundhog_memory import (
    groundhog_auto_merge_enabled,
    groundhog_bundle_path,
)
from renaissance_v4.game_theory.pattern_outcome_quality_v1 import compute_pattern_outcome_quality_v1

SCHEMA = "learning_run_audit_v1"


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v: Any, default: float | None = None) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _memory_operator_note(
    *,
    scenario: dict[str, Any],
    mb_proof: dict[str, Any],
    mem_applied: bool,
) -> str:
    explicit = (scenario.get("memory_bundle_path") or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        exists = p.is_file()
        loaded = bool(mb_proof.get("memory_bundle_loaded"))
        if not exists:
            return f"Explicit memory_bundle_path does not exist on disk: {explicit!r}."
        if not loaded:
            return f"Explicit memory_bundle_path exists but did not load as a valid bundle: {explicit!r}."
        if not mem_applied:
            return "Explicit memory bundle loaded but no whitelisted keys merged into manifest."
        return "Explicit memory bundle merged into manifest (whitelisted keys applied)."
    if mem_applied:
        return "Memory bundle merged into manifest (resolved path in memory_bundle_path_resolved)."
    if mb_proof.get("memory_bundle_path"):
        return "A bundle path was resolved but the file was missing or produced no merge — see memory_bundle_proof."
    return "No memory bundle path resolved for this replay — execution-only with respect to promoted memory."


def _groundhog_lane(
    *,
    scenario: dict[str, Any],
    mb_proof: dict[str, Any],
) -> tuple[str, str]:
    """
    Canonical Groundhog path only (explicit ``memory_bundle_path`` → lane **inactive** here).

    * **committed** — auto-merge used the canonical file and merged whitelisted keys.
    * **candidate_only** — env on but missing file, or file read without apply.
    * **inactive** — env off, skipped, or operator supplied an explicit bundle path.
    """
    skip = bool(scenario.get("skip_groundhog_bundle"))
    env = groundhog_auto_merge_enabled()
    canonical = groundhog_bundle_path()
    canon_exists = canonical.is_file()
    explicit = (scenario.get("memory_bundle_path") or "").strip()
    resolved = (mb_proof.get("memory_bundle_path") or "").strip()
    loaded = bool(mb_proof.get("memory_bundle_loaded"))
    applied = bool(mb_proof.get("memory_bundle_applied"))

    try:
        canon_s = str(canonical.resolve())
    except OSError:
        canon_s = str(canonical)
    resolved_is_gh = bool(
        resolved and canon_s and Path(resolved).resolve() == Path(canon_s).resolve()
    )

    if explicit:
        return (
            "inactive",
            "Groundhog lane n/a: scenario set memory_bundle_path — resolution is explicit, not canonical auto-merge.",
        )
    if skip:
        return "inactive", "Groundhog: skip_groundhog_bundle=true — canonical auto-merge suppressed."
    if not env:
        return "inactive", "Groundhog: PATTERN_GAME_GROUNDHOG_BUNDLE off — expected for runs that do not auto-load canonical bundle."
    if not canon_exists:
        return (
            "candidate_only",
            "Groundhog: auto-merge enabled but canonical groundhog_memory_bundle.json is missing.",
        )
    if applied and resolved_is_gh:
        return "committed", "Groundhog: canonical bundle merged into manifest."
    if loaded and not applied and resolved_is_gh:
        return (
            "candidate_only",
            "Groundhog: canonical file read but no whitelisted keys applied (empty apply).",
        )
    return (
        "candidate_only",
        "Groundhog: env on and file may exist, but this replay did not apply the canonical bundle.",
    )


def _format_winner_vs_control_summary(wvc: dict[str, Any] | None) -> str | None:
    """Human-readable delta from CCS ``winner_vs_control`` (runtime proof only)."""
    if not isinstance(wvc, dict) or not wvc:
        return None
    oq = wvc.get("outcome_quality_v1") or {}
    if isinstance(oq, dict):
        de = oq.get("expectancy_per_trade_delta")
        if de is not None:
            try:
                return f"ΔE/trade {round(float(de), 6)}"
            except (TypeError, ValueError):
                pass
    ed = wvc.get("expectancy_delta")
    if ed is not None:
        try:
            return f"Δexpectancy {round(float(ed), 6)}"
        except (TypeError, ValueError):
            return None
    return None


def _candidate_block(replay_out: dict[str, Any]) -> dict[str, Any]:
    proof = replay_out.get("context_candidate_search_proof")
    if not isinstance(proof, dict) or not proof.get("schema"):
        return {
            "context_candidate_search_ran": False,
            "candidate_count": 0,
            "control_vs_candidate_comparison": "not_applicable",
            "selected_candidate_id": None,
            "none_beat_control": None,
            "reason_codes_sample": [],
            "winner_vs_control": None,
            "winner_vs_control_delta_summary": None,
        }
    summaries = proof.get("candidate_summaries") or []
    n = len(summaries) if isinstance(summaries, list) else 0
    sel = proof.get("selected_candidate_id")
    codes = list(proof.get("reason_codes") or [])
    none_beat = "CCS_V1_NONE_BEAT_CONTROL" in codes if codes else None
    comparison = "completed" if n else "no_candidates"
    wvc = proof.get("winner_vs_control")
    if not isinstance(wvc, dict):
        wvc = None
    return {
        "context_candidate_search_ran": True,
        "candidate_count": n,
        "control_vs_candidate_comparison": comparison,
        "selected_candidate_id": sel,
        "none_beat_control": bool(none_beat) if none_beat is not None else None,
        "reason_codes_sample": codes[:12],
        "winner_vs_control": wvc,
        "winner_vs_control_delta_summary": _format_winner_vs_control_summary(wvc),
    }


def build_per_scenario_learning_run_audit_v1(
    replay_out: dict[str, Any],
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build one JSON object from ``run_pattern_game`` / ``run_manifest_replay`` output + scenario echo.

    Does not mutate inputs.
    """
    scen = scenario or {}
    ra = replay_out.get("replay_attempt_aggregates_v1") or {}
    sup_slots = _int(ra.get("suppressed_module_slots_total"), 0)
    pc = replay_out.get("pattern_context_v1") or {}
    mb_proof = replay_out.get("memory_bundle_proof") or {}
    if not isinstance(mb_proof, dict):
        mb_proof = {}
    dcr = replay_out.get("decision_context_recall_stats") or {}
    if not isinstance(dcr, dict):
        dcr = {}

    bars = _int(ra.get("bars_processed") or pc.get("bars_processed"), 0)
    dw = _int(ra.get("decision_windows_total"), 0)
    recall_attempts = _int(ra.get("recall_attempts_total"), 0)
    recall_matches = _int(ra.get("recall_match_windows_total"), 0)
    recall_records = _int(ra.get("recall_match_records_total"), 0)
    bias_applied = _int(ra.get("recall_bias_applied_total"), 0)
    sig_bias = _int(ra.get("recall_signal_bias_applied_total"), 0)

    mem_loaded = bool(mb_proof.get("memory_bundle_loaded"))
    mem_applied = bool(mb_proof.get("memory_bundle_applied"))
    gh_lane, gh_note = _groundhog_lane(scenario=scen, mb_proof=mb_proof)
    mem_note = _memory_operator_note(scenario=scen, mb_proof=mb_proof, mem_applied=mem_applied)

    cand = _candidate_block(replay_out)

    outcomes = list(replay_out.get("outcomes") or [])
    oq = compute_pattern_outcome_quality_v1(outcomes)
    trades_n = _int(oq.get("trades_count"), 0)
    sm = replay_out.get("summary") if isinstance(replay_out.get("summary"), dict) else {}
    trade_win_pct = _float(sm.get("win_rate")) if trades_n > 0 else None

    mechanisms: list[str] = []
    if mem_applied:
        mechanisms.append("memory_bundle_apply")
    if recall_matches > 0:
        mechanisms.append("recall_match")
    if bias_applied > 0:
        mechanisms.append("recall_fusion_bias")
    if sig_bias > 0:
        mechanisms.append("recall_signal_bias")
    if cand["context_candidate_search_ran"] and _int(cand.get("candidate_count"), 0) > 0:
        mechanisms.append("context_candidate_search")

    learning_engaged = bool(dw > 0 and len(mechanisms) > 0)
    classification = "learning_engaged" if learning_engaged else "execution_only"

    pfa = scen.get("policy_framework_audit") if isinstance(scen.get("policy_framework_audit"), dict) else None

    audit: dict[str, Any] = {
        "schema": SCHEMA,
        "run_classification_v1": classification,
        "learning_engaged_v1": learning_engaged,
        "learning_mechanisms_observed_v1": mechanisms,
        "bars_processed": bars,
        "decision_windows_total": dw,
        "trade_entries_total": _int(ra.get("trade_entries_total"), 0),
        "trade_exits_total": _int(ra.get("trade_exits_total"), 0),
        "trade_win_rate": round(float(trade_win_pct), 6) if trade_win_pct is not None else None,
        "expectancy_per_trade": oq.get("expectancy_per_trade"),
        "exit_efficiency": oq.get("exit_efficiency"),
        "win_loss_size_ratio": oq.get("win_loss_size_ratio"),
        "trades_count": trades_n,
        "memory_used_v1": mem_applied,
        "memory_bundle_loaded": mem_loaded,
        "memory_bundle_applied": mem_applied,
        "memory_bundle_path_resolved": mb_proof.get("memory_bundle_path"),
        "memory_keys_applied": list(mb_proof.get("memory_keys_applied") or []),
        "memory_operator_note_v1": mem_note,
        "groundhog_operator_note_v1": gh_note,
        "memory_records_loaded_count": max(
            _int(dcr.get("memory_records_loaded_count"), 0),
            _int(ra.get("memory_records_loaded_count"), 0),
        ),
        "groundhog_operator_lane_v1": gh_lane,
        "groundhog_auto_merge_env_enabled": groundhog_auto_merge_enabled(),
        "recall_attempts_total": recall_attempts,
        "recall_match_windows_total": recall_matches,
        "recall_match_records_total": recall_records,
        "recall_bias_applied_total": bias_applied,
        "recall_signal_bias_applied_total": sig_bias,
        "suppressed_modules_count": sup_slots,
        "decision_context_recall_enabled": bool(dcr.get("decision_context_recall_enabled")),
        "context_candidate_search_block_v1": cand,
        "policy_framework_audit": pfa,
    }
    audit["operator_learning_status_line_v1"] = build_operator_learning_status_line_v1(audit)
    return audit


def build_operator_learning_status_line_v1(audit: dict[str, Any]) -> str:
    """Single human-readable line from structured fields only (no LLM)."""
    cls = audit.get("run_classification_v1") or "unknown"
    dw = _int(audit.get("decision_windows_total"), 0)
    cand = audit.get("context_candidate_search_block_v1") or {}
    c_n = _int(cand.get("candidate_count"), 0)
    c_ran = bool(cand.get("context_candidate_search_ran"))
    parts = [
        f"classification={cls}",
        f"decision_windows={dw}",
    ]
    if c_ran:
        sel = cand.get("selected_candidate_id") or "none"
        nbc = cand.get("none_beat_control")
        parts.append(f"candidate_search=candidates={c_n} selected={sel} none_beat_control={nbc}")
    else:
        parts.append("candidate_search=not_run (parallel replay path — no multi-replay search in this worker)")
    rm = _int(audit.get("recall_match_windows_total"), 0)
    parts.append(f"recall_matches={rm}")
    parts.append(
        f"bias_applied_fusion={_int(audit.get('recall_bias_applied_total'), 0)} "
        f"signal={_int(audit.get('recall_signal_bias_applied_total'), 0)}"
    )
    mem = bool(audit.get("memory_bundle_applied"))
    parts.append(f"memory_merged={'yes' if mem else 'no'}")
    if cls == "execution_only":
        parts.append(
            "verdict=execution_only — replayed policy on tape; no memory merge, recall match, bias application, or candidate search in this run."
        )
    else:
        win = cand.get("selected_candidate_id") if c_ran else None
        win_s = f" winner={win!r}" if c_ran else ""
        parts.append(f"verdict=learning_engaged — mechanisms: {audit.get('learning_mechanisms_observed_v1')}{win_s}")
    return "; ".join(parts)


def aggregate_batch_learning_run_audit_v1(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Roll up per-scenario ``learning_run_audit_v1`` rows attached to parallel ``results``.

    ``total_processed`` in the batch scorecard remains the count of scenario result rows; this block
    adds explicit replay depth sums so operators are not misled into thinking one opaque integer
    counted candidate replays.
    """
    ok_n = sum(1 for r in results if r.get("ok"))

    def _audit_from_row(r: dict[str, Any]) -> dict[str, Any] | None:
        a = r.get("learning_run_audit_v1")
        if isinstance(a, dict):
            return a
        summ = r.get("summary")
        if isinstance(summ, dict):
            a2 = summ.get("learning_run_audit_v1")
            if isinstance(a2, dict):
                return a2
        return None

    audits: list[dict[str, Any]] = []
    for r in results:
        if not r.get("ok"):
            continue
        a = _audit_from_row(r)
        if isinstance(a, dict):
            audits.append(a)
    if not audits:
        return {
            "schema": "learning_batch_audit_v1",
            "parallel_scenarios_completed": ok_n,
            "parallel_scenarios_total_rows": len(results),
            "replay_bars_processed_sum": 0,
            "replay_decision_windows_sum": 0,
            "context_candidate_replays_sum": 0,
            "batch_run_classification_v1": "unknown" if ok_n else "execution_only",
            "any_learning_engaged": False,
            "operator_learning_status_line_v1": (
                "No learning_run_audit_v1 on successful rows — check worker wiring."
                if ok_n
                else "No successful scenarios in this batch — all workers failed or returned ok=false."
            ),
        }
    engaged = [a for a in audits if a.get("learning_engaged_v1")]
    any_eng = len(engaged) > 0
    if len(engaged) == len(audits):
        batch_cls = "learning_engaged"
    elif len(engaged) == 0:
        batch_cls = "execution_only"
    else:
        batch_cls = "mixed"

    cand_replays = 0
    for a in audits:
        blk = a.get("context_candidate_search_block_v1") or {}
        if blk.get("context_candidate_search_ran"):
            # control + each candidate replay inside search (approximate: candidates + 1 control each scenario)
            cand_replays += _int(blk.get("candidate_count"), 0) + 1

    lines = [str(a.get("operator_learning_status_line_v1") or "") for a in audits[:3]]
    tail = f" (+{len(audits) - 3} more)" if len(audits) > 3 else ""

    return {
        "schema": "learning_batch_audit_v1",
        "parallel_scenarios_completed": sum(1 for r in results if r.get("ok")),
        "parallel_scenarios_total_rows": len(results),
        "replay_bars_processed_sum": sum(_int(a.get("bars_processed"), 0) for a in audits),
        "replay_decision_windows_sum": sum(_int(a.get("decision_windows_total"), 0) for a in audits),
        "context_candidate_replays_sum": cand_replays,
        "batch_run_classification_v1": batch_cls,
        "any_learning_engaged": any_eng,
        "scenarios_learning_engaged_count": len(engaged),
        "operator_learning_status_line_v1": " | ".join(x for x in lines if x) + tail,
    }


def learning_batch_candidate_replays(audits: list[dict[str, Any]]) -> int:
    """Approximate control+candidate replays summed across scenarios (harness / CCS only)."""
    n = 0
    for a in audits:
        blk = a.get("context_candidate_search_block_v1") or {}
        if blk.get("context_candidate_search_ran"):
            n += _int(blk.get("candidate_count"), 0) + 1
    return n


def _audit_from_result_row(r: dict[str, Any]) -> dict[str, Any] | None:
    a = r.get("learning_run_audit_v1")
    if isinstance(a, dict):
        return a
    summ = r.get("summary")
    if isinstance(summ, dict):
        a2 = summ.get("learning_run_audit_v1")
        if isinstance(a2, dict):
            return a2
    return None


def compute_scorecard_learning_rollups_v1(
    results: list[dict[str, Any]],
    *,
    operator_batch_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Operator-first batch fields for ``batch_scorecard.jsonl`` and the pattern-game UI.

    ``learning_status`` follows operator directive: ``learning_active`` iff decision windows > 0
    and at least one of (candidates tested, memory records loaded, recall matches, signal bias
    applications) is positive on the summed batch.
    """
    audits: list[dict[str, Any]] = []
    for r in results or []:
        if not r.get("ok"):
            continue
        a = _audit_from_result_row(r)
        if isinstance(a, dict):
            audits.append(a)

    n_scen = len(results or [])
    n_ok = sum(1 for r in (results or []) if r.get("ok"))

    def _mean_metric(key: str) -> float | None:
        vals: list[float] = []
        for a in audits:
            if _int(a.get("trades_count"), 0) <= 0:
                continue
            v = a.get(key)
            if v is None:
                continue
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                continue
        if not vals:
            return None
        return round(sum(vals) / len(vals), 6)

    if not audits:
        la = {
            "schema": "learning_audit_v1",
            "policy_framework_id": None,
            "decision_windows_total": 0,
            "candidate_count": 0,
            "memory_records_loaded": 0,
            "recall_stats": {},
            "signal_bias_stats": {},
            "groundhog_status": "inactive",
            "winner_vs_control": None,
            "evaluation_window": None,
            "replay_data_audit": None,
        }
        return {
            "learning_audit_v1": la,
            "learning_status": "execution_only",
            "decision_windows_total": 0,
            "bars_processed": 0,
            "candidate_count": 0,
            "selected_candidate_id": None,
            "winner_vs_control_delta": None,
            "memory_used": False,
            "memory_records_loaded": 0,
            "groundhog_status": "inactive",
            "recall_attempts": 0,
            "recall_matches": 0,
            "recall_bias_applied": 0,
            "signal_bias_applied_count": 0,
            "suppressed_modules_count": 0,
            "trade_entries_total": 0,
            "trade_exits_total": 0,
            "batch_trades_count": 0,
            "expectancy_per_trade": None,
            "exit_efficiency": None,
            "win_loss_size_ratio": None,
            "work_units_v1": f"0 scenarios with audits (ok rows={n_ok}, total rows={n_scen})",
            "operator_learning_table_summary_v1": [
                "Learning Status: EXECUTION ONLY (no tuning engaged)",
                "Decision Windows: 0",
                "Candidates Tested: 0",
                "Recall Matches: 0",
                "Signal Adjustments: 0",
                "Winner: —",
            ],
        }

    sum_dw = sum(_int(a.get("decision_windows_total"), 0) for a in audits)
    sum_bars = sum(_int(a.get("bars_processed"), 0) for a in audits)
    cand_total = 0
    sel: str | None = None
    winner_delta: str | None = None
    winner_struct: dict[str, Any] | None = None
    for a in audits:
        blk = a.get("context_candidate_search_block_v1") or {}
        cand_total += _int(blk.get("candidate_count"), 0)
        if sel is None and blk.get("selected_candidate_id"):
            sel = str(blk.get("selected_candidate_id"))
        if winner_delta is None:
            wd = blk.get("winner_vs_control_delta_summary")
            if isinstance(wd, str) and wd.strip():
                winner_delta = wd.strip()
            elif blk.get("context_candidate_search_ran"):
                wvc = blk.get("winner_vs_control")
                if isinstance(wvc, dict):
                    winner_delta = _format_winner_vs_control_summary(wvc)
        if winner_struct is None:
            wvc2 = blk.get("winner_vs_control")
            if isinstance(wvc2, dict) and wvc2:
                winner_struct = dict(wvc2)

    mem_used = any(bool(a.get("memory_bundle_applied")) for a in audits)
    mem_recs = sum(_int(a.get("memory_records_loaded_count"), 0) for a in audits)
    recall_att = sum(_int(a.get("recall_attempts_total"), 0) for a in audits)
    recall_mat = sum(_int(a.get("recall_match_windows_total"), 0) for a in audits)
    recall_bias = sum(_int(a.get("recall_bias_applied_total"), 0) for a in audits)
    sig_bias = sum(_int(a.get("recall_signal_bias_applied_total"), 0) for a in audits)
    sup_mod = sum(_int(a.get("suppressed_modules_count"), 0) for a in audits)
    ent = sum(_int(a.get("trade_entries_total"), 0) for a in audits)
    exi = sum(_int(a.get("trade_exits_total"), 0) for a in audits)
    batch_trades = sum(_int(a.get("trades_count"), 0) for a in audits)

    lanes = [str(a.get("groundhog_operator_lane_v1") or "") for a in audits]
    if any(x == "committed" for x in lanes):
        gh_batch = "committed"
    elif any(x == "candidate_only" for x in lanes):
        gh_batch = "candidate"
    else:
        gh_batch = "inactive"

    learning_active = bool(
        sum_dw > 0
        and (
            cand_total > 0
            or mem_recs > 0
            or recall_mat > 0
            or sig_bias > 0
        )
    )
    learning_status = "learning_active" if learning_active else "execution_only"

    pfa0: dict[str, Any] | None = None
    if operator_batch_audit and isinstance(operator_batch_audit.get("policy_framework_audit"), dict):
        pfa0 = dict(operator_batch_audit["policy_framework_audit"])
    else:
        for a in audits:
            pfx = a.get("policy_framework_audit")
            if isinstance(pfx, dict):
                pfa0 = dict(pfx)
                break

    pf_id = (pfa0 or {}).get("framework_id")
    eval_win = (operator_batch_audit or {}).get("evaluation_window") if operator_batch_audit else None
    replay_audit = None
    if operator_batch_audit and operator_batch_audit.get("replay_data_audit") is not None:
        replay_audit = operator_batch_audit.get("replay_data_audit")
    else:
        for r in results or []:
            if not r.get("ok"):
                continue
            rda = r.get("replay_data_audit")
            if rda is not None:
                replay_audit = rda
                break

    recall_stats = {
        "attempts": recall_att,
        "matches": recall_mat,
        "bias_applied": recall_bias,
        "match_records": sum(_int(a.get("recall_match_records_total"), 0) for a in audits),
    }
    signal_bias_stats = {
        "applied_count": sig_bias,
        "suppressed_modules_count": sup_mod,
    }

    la = {
        "schema": "learning_audit_v1",
        "policy_framework_id": pf_id,
        "decision_windows_total": sum_dw,
        "candidate_count": cand_total,
        "memory_records_loaded": mem_recs,
        "recall_stats": recall_stats,
        "signal_bias_stats": signal_bias_stats,
        "groundhog_status": gh_batch,
        "winner_vs_control": winner_struct,
        "evaluation_window": eval_win,
        "replay_data_audit": replay_audit,
    }

    exp_m = _mean_metric("expectancy_per_trade")
    exi_m = _mean_metric("exit_efficiency")
    wlr_m = _mean_metric("win_loss_size_ratio")

    trade_win_vals: list[float] = []
    for r in results or []:
        if not r.get("ok"):
            continue
        summ = r.get("summary")
        if not isinstance(summ, dict):
            continue
        tr = summ.get("trades")
        if tr is None or int(tr) <= 0:
            continue
        wr = summ.get("win_rate")
        if wr is None:
            continue
        try:
            trade_win_vals.append(float(wr))
        except (TypeError, ValueError):
            continue
    batch_trade_win_pct = (
        round(100.0 * sum(trade_win_vals) / len(trade_win_vals), 2) if trade_win_vals else None
    )
    batch_trade_win_rate_n = len(trade_win_vals)

    cand_rep = learning_batch_candidate_replays(audits)

    lines = [
        f"Learning Status: {'ACTIVE' if learning_active else 'EXECUTION ONLY (no tuning engaged)'}",
        f"Decision Windows: {sum_dw:,}",
        f"Candidates Tested: {cand_total}",
        f"Recall Matches: {recall_mat:,}",
        f"Signal Adjustments: {sig_bias:,}",
    ]
    if sel:
        lines.append(f"Winner: {sel}" + (f" ({winner_delta})" if winner_delta else ""))
    else:
        lines.append("Winner: —")

    work_units = (
        f"{len(audits)} scenario row(s) · {sum_dw:,} decision windows · "
        f"{cand_rep} candidate-stack replays (control+candidates, if any)"
    )

    flat = {
        "learning_audit_v1": la,
        "learning_status": learning_status,
        "decision_windows_total": sum_dw,
        "bars_processed": sum_bars,
        "candidate_count": cand_total,
        "selected_candidate_id": sel,
        "winner_vs_control_delta": winner_delta,
        "memory_used": mem_used,
        "memory_records_loaded": mem_recs,
        "groundhog_status": gh_batch,
        "recall_attempts": recall_att,
        "recall_matches": recall_mat,
        "recall_bias_applied": recall_bias,
        "signal_bias_applied_count": sig_bias,
        "suppressed_modules_count": sup_mod,
        "trade_entries_total": ent,
        "trade_exits_total": exi,
        "batch_trades_count": batch_trades,
        "batch_trade_win_pct": batch_trade_win_pct,
        "batch_trade_win_rate_n": batch_trade_win_rate_n,
        "expectancy_per_trade": exp_m,
        "exit_efficiency": exi_m,
        "win_loss_size_ratio": wlr_m,
        "work_units_v1": work_units,
        "operator_learning_table_summary_v1": lines,
    }
    return flat


__all__ = [
    "SCHEMA",
    "aggregate_batch_learning_run_audit_v1",
    "build_operator_learning_status_line_v1",
    "build_per_scenario_learning_run_audit_v1",
    "compute_scorecard_learning_rollups_v1",
    "learning_batch_candidate_replays",
]
