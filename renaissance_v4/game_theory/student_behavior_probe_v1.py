"""
Student **behavior probe** — deterministic fast-fail gate after RM preflight, before full parallel.

* Does **not** call ``run_scenarios_parallel`` or Referee replay workers.
* Builds a **thin** ``results`` row with synthetic :class:`OutcomeRecord` shells anchored on real DB bar
  timestamps (same packet source as RM decision snapshot).
* Invokes ``student_loop_seam_after_parallel_batch_v1`` once — full Student seam (packet → ERE → LLM → authority → seal).

**Hard wall-clock:** By default the seam runs in a **spawn subprocess**. The parent ``terminate()`` / ``kill()`` the
child if it exceeds ``PATTERN_GAME_STUDENT_PROBE_MAX_WALL_S`` (default **120**), returning
``failed_student_behavior_probe_timeout_v1`` — same pattern as RM preflight hard timeout. Slow local LLMs need
this headroom; tighten with env if desired.

Disable isolation with ``PATTERN_GAME_STUDENT_PROBE_SUBPROCESS_ISOLATION=0`` (tests only; can hang).
"""

from __future__ import annotations

import copy
import json
import multiprocessing
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    normalize_student_reasoning_mode_v1,
)
from renaissance_v4.game_theory.groundhog_memory import resolve_memory_bundle_for_scenario
from renaissance_v4.game_theory.learning_trace_events_v1 import SCHEMA_EVENT, read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.pattern_game import prepare_effective_manifest_for_replay
from renaissance_v4.manifest.validate import load_manifest_file
from renaissance_v4.utils.db import DB_PATH


SCHEMA_FAILED_STUDENT_BEHAVIOR_PROBE_V1 = "failed_student_behavior_probe_v1"
FAILED_STUDENT_BEHAVIOR_PROBE_TIMEOUT_V1 = "failed_student_behavior_probe_timeout_v1"

# Directive SLA — strict gate (fail probe if exceeded).
# Default wall allows at least one full Student seam decision cycle on typical lab LLM latency (was 5s — timed out before any seal).
_PROBE_DEFAULT_MAX_WALL_S = 120.0
# Fewer synthetic trades by default = less sequential LLM work; operators can raise via PATTERN_GAME_STUDENT_PROBE_MAX_TRADES.
_PROBE_MIN_TRADES = 3
_PROBE_MAX_TRADES_CAP = 20
_PROBE_DEFAULT_TRADES = 5
# At least one completed seal (authority-aligned); raised counts still allowed if the seam produces them.
_PASS_MIN_SEALED = 1
_PASS_MAX_REJECTION_RATE = 0.20


def student_behavior_probe_enabled_v1() -> bool:
    v = (os.environ.get("PATTERN_GAME_STUDENT_BEHAVIOR_PROBE") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def student_behavior_probe_max_wall_seconds_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_STUDENT_PROBE_MAX_WALL_S") or "").strip()
    try:
        t = float(raw) if raw else _PROBE_DEFAULT_MAX_WALL_S
    except ValueError:
        t = _PROBE_DEFAULT_MAX_WALL_S
    return max(1.0, min(t, 120.0))


def student_behavior_probe_subprocess_isolation_enabled_v1() -> bool:
    """When true (default), seam body runs in a spawn child and is SIGKILL/terminate on SLA (like RM preflight)."""
    v = (os.environ.get("PATTERN_GAME_STUDENT_PROBE_SUBPROCESS_ISOLATION") or "1").strip().lower()
    return v not in ("0", "false", "off", "no")


def student_behavior_probe_trade_count_v1() -> int:
    raw = (os.environ.get("PATTERN_GAME_STUDENT_PROBE_MAX_TRADES") or "").strip()
    try:
        n = int(raw) if raw else _PROBE_DEFAULT_TRADES
    except ValueError:
        n = _PROBE_DEFAULT_TRADES
    return max(_PROBE_MIN_TRADES, min(_PROBE_MAX_TRADES_CAP, n))


def behavior_probe_trace_job_id_v1(main_job_id: str) -> str:
    base = str(main_job_id or "").strip()
    suf = "_sb_pr"
    if len(base) + len(suf) > 64:
        return base[: 64 - len(suf)] + suf
    return base + suf


def profile_requires_student_behavior_probe_v1(exam_req: dict[str, Any] | None) -> bool:
    if not isinstance(exam_req, dict):
        return False
    prof = normalize_student_reasoning_mode_v1(
        str(exam_req.get("student_brain_profile_v1") or exam_req.get("student_reasoning_mode") or "")
    )
    return prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1


def evaluate_full_student_run_contract_v1(
    job_id: str,
    seam_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    After full seam on the **real** job id: fail contract if trace integrity or stop reason demands suppression.
    """
    from renaissance_v4.game_theory.learning_trace_events_v1 import count_learning_trace_terminal_integrity_v1

    jid = str(job_id or "").strip()
    reasons: list[str] = []
    intr = count_learning_trace_terminal_integrity_v1(jid)
    auth = int(intr.get("student_decision_authority_v1_count") or 0)
    sealed = int(intr.get("student_output_sealed_count") or 0)
    if auth <= 0:
        reasons.append("authority_count_zero_v1")
    if sealed <= 0:
        reasons.append("sealed_count_zero_v1")
    if not bool(intr.get("integrity_ok")):
        reasons.append("authority_ne_sealed_trace_integrity_v1")
    sr = str((seam_audit or {}).get("student_seam_stop_reason_v1") or "") if isinstance(seam_audit, dict) else ""
    sr_terminal_ok_v1 = sr in (
        "completed_all_trades_v1",
        "rm_preflight_early_exit_first_seal_v1",
    )
    if not sr_terminal_ok_v1:
        reasons.append(f"student_seam_stop_reason_not_completed_v1:{sr or 'missing'}")
    failed = len(reasons) > 0
    return {
        "student_full_run_contract_failed_v1": failed,
        "operator_metrics_suppressed_v1": failed,
        "contract_failure_reasons_v1": reasons,
        "learning_trace_terminal_integrity_echo_v1": intr,
    }


def finalize_seam_audit_authority_seal_contract_v1(
    job_id: str,
    seam_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Post-seam belt-and-suspenders: if mandate applies and terminal trace counts show authority≠sealed,
    emit ``fatal_authority_seal_mismatch_v1`` and flag the seam audit (job batch path treats as terminal error).
    """
    sa = seam_audit if isinstance(seam_audit, dict) else {}
    if sa.get("fatal_authority_seal_mismatch_v1"):
        return sa
    if not sa.get("student_decision_authority_mandate_enforced_v1"):
        return sa
    if sa.get("skipped"):
        return sa
    from renaissance_v4.game_theory.learning_trace_events_v1 import count_learning_trace_terminal_integrity_v1
    from renaissance_v4.game_theory.learning_trace_instrumentation_v1 import emit_fatal_authority_seal_mismatch_v1

    jid = str(job_id or "").strip()
    intr = count_learning_trace_terminal_integrity_v1(jid)
    if bool(intr.get("integrity_ok")):
        return sa
    detail = json.dumps(intr, default=str)[:4000]
    emit_fatal_authority_seal_mismatch_v1(
        job_id=jid,
        fingerprint=None,
        scenario_id=None,
        trade_id=None,
        reason_code="terminal_integrity_auth_ne_sealed_v1",
        detail=detail,
    )
    out = dict(sa)
    out["fatal_authority_seal_mismatch_v1"] = True
    out["student_seam_stop_reason_v1"] = "fatal_authority_seal_mismatch_v1"
    out["fatal_authority_seal_detail_v1"] = {
        "reason_code": "terminal_integrity_auth_ne_sealed_v1",
        "learning_trace_terminal_integrity_echo_v1": intr,
    }
    errs = list(out.get("errors") or []) if isinstance(out.get("errors"), list) else []
    errs.append("fatal_authority_seal_mismatch_v1: terminal_integrity_auth_ne_sealed_v1")
    out["errors"] = errs
    return out


def _symbol_from_manifest_v1(manifest: dict[str, Any]) -> str:
    sym = str(manifest.get("symbol") or "").strip()
    if sym:
        return sym
    return str(manifest.get("strategy_id") or "").strip()


def _probe_decision_open_times_v1(db_path: Path, symbol: str, n: int) -> list[int]:
    """Latest ``n`` bar open times for ``symbol`` (descending order → chronological processing varies by seam)."""
    try:
        conn = sqlite3.connect(str(db_path))
    except OSError:
        return []
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT open_time FROM market_bars_5m WHERE symbol = ? ORDER BY open_time DESC LIMIT ?",
            (symbol, max(1, n)),
        ).fetchall()
        out = [int(r[0]) for r in rows if r and r[0] is not None]
        return out
    finally:
        conn.close()


def _contract_violation_from_error_line_v1(err: str) -> bool:
    s = (err or "").lower()
    return (
        "student_output_invalid" in s
        or "student_output_thesis" in s
        or "thesis_incomplete" in s
        or "decision_protocol_incomplete" in s
        or "protocol" in s and "incomplete" in s
        or "validate_student_output" in s
    )


def _metrics_from_probe_trace_events_v1(events: list[dict[str, Any]]) -> dict[str, Any]:
    auth = sealed = rej = viol = 0
    failures: list[dict[str, Any]] = []
    rejection_reasons: list[str] = []
    for ev in events:
        if str(ev.get("schema") or "") != SCHEMA_EVENT:
            continue
        st = str(ev.get("stage") or "")
        if st == "student_decision_authority_v1":
            auth += 1
        elif st == "student_output_sealed":
            sealed += 1
        elif st == "llm_output_rejected":
            rej += 1
            ep = ev.get("evidence_payload") if isinstance(ev.get("evidence_payload"), dict) else {}
            errs = ep.get("errors") if isinstance(ep.get("errors"), list) else []
            for e in errs:
                es = str(e)
                if _contract_violation_from_error_line_v1(es):
                    viol += 1
                if es and es not in rejection_reasons:
                    rejection_reasons.append(es[:500])
            if len(failures) < 12:
                failures.append(
                    {
                        "scenario_id": ev.get("scenario_id"),
                        "trade_id": ev.get("trade_id"),
                        "errors": [str(x) for x in errs[:12]],
                        "summary": str(ev.get("summary") or "")[:800],
                    }
                )
    return {
        "authority_count_v1": auth,
        "sealed_count_v1": sealed,
        "rejection_count_v1": rej,
        "contract_violation_count_v1": viol,
        "failure_samples_v1": failures[:3],
        "rejection_reasons_v1": rejection_reasons[:24],
    }


def evaluate_student_behavior_probe_gates_v1(
    *,
    metrics: dict[str, Any],
    wall_clock_s_v1: float,
    wall_limit_s_v1: float,
) -> tuple[bool, list[str]]:
    errs: list[str] = []
    auth = int(metrics.get("authority_count_v1") or 0)
    sealed = int(metrics.get("sealed_count_v1") or 0)
    rej = int(metrics.get("rejection_count_v1") or 0)
    viol = int(metrics.get("contract_violation_count_v1") or 0)

    if wall_clock_s_v1 > float(wall_limit_s_v1):
        errs.append(
            f"gate_probe_wall_clock_v1: probe_wall_clock_s_v1 ({wall_clock_s_v1:.3f}s) exceeds "
            f"limit ({wall_limit_s_v1:.3f}s)"
        )
    if sealed < _PASS_MIN_SEALED:
        errs.append(f"gate_sealed_ge_min_v1: sealed_count_v1 ({sealed}) must be >= {_PASS_MIN_SEALED}")
    if auth != sealed:
        errs.append(f"gate_authority_equals_sealed_v1: authority_count_v1 ({auth}) != sealed_count_v1 ({sealed})")
    denom = rej + sealed
    rate = (rej / denom) if denom > 0 else 0.0
    if rate >= _PASS_MAX_REJECTION_RATE:
        errs.append(
            f"gate_rejection_rate_v1: rejection_rate ({rate:.4f}) must be < {_PASS_MAX_REJECTION_RATE}"
        )
    if viol != 0:
        errs.append(f"gate_contract_violations_zero_v1: contract_violation_count_v1={viol} must be 0")

    return len(errs) == 0, errs


def build_probe_minimal_results_v1(
    *,
    scenario: dict[str, Any],
    exam_run_contract_request_v1: dict[str, Any] | None,
    max_trades: int,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """
    One parallel-style row with ``replay_outcomes_json`` — **no** Referee replay; outcomes use DB anchors only.
    """
    mbp = scenario.get("memory_bundle_path")
    if mbp:
        mbp = str(Path(str(mbp)).expanduser().resolve())
    else:
        mbp = resolve_memory_bundle_for_scenario(scenario, explicit_path=None)

    prep = None
    try:
        prep = prepare_effective_manifest_for_replay(
            scenario["manifest_path"],
            atr_stop_mult=scenario.get("atr_stop_mult"),
            atr_target_mult=scenario.get("atr_target_mult"),
            memory_bundle_path=mbp,
            use_groundhog_auto_resolve=False,
        )
        manifest = load_manifest_file(prep.replay_path)
    except Exception as e:
        if prep is not None:
            try:
                prep.cleanup()
            except Exception:
                pass
        return None, f"probe_manifest_prepare_failed_v1:{type(e).__name__}:{e}"

    try:
        sym = _symbol_from_manifest_v1(manifest)
        db_used = Path(str(DB_PATH)).resolve()
        times = _probe_decision_open_times_v1(db_used, sym, max_trades)
        if len(times) < _PASS_MIN_SEALED:
            return (
                None,
                f"probe_insufficient_anchor_times_v1: need at least {_PASS_MIN_SEALED} rows in market_bars_5m "
                f"for symbol={sym!r}, got {len(times)}",
            )

        sid = str(scenario.get("scenario_id") or "probe_scenario_v1").strip() or "probe_scenario_v1"
        outcomes: list[dict[str, Any]] = []
        for i, t_ms in enumerate(times):
            exit_ms = int(t_ms) + 300_000
            o = OutcomeRecord(
                trade_id=f"behavior_probe_{i:04d}_v1",
                symbol=sym,
                direction="long",
                entry_time=int(t_ms),
                exit_time=exit_ms,
                entry_price=1.0,
                exit_price=1.01,
                pnl=0.0,
                mae=0.0,
                mfe=0.0,
                exit_reason="probe_shell_v1",
                metadata={"behavior_probe_synthetic_outcome_v1": True},
            )
            outcomes.append(outcome_record_to_jsonable(o))

        row = {
            "ok": True,
            "scenario_id": sid,
            "replay_outcomes_json": outcomes,
        }
        return [row], None
    finally:
        if prep is not None:
            try:
                prep.cleanup()
            except Exception:
                pass


def build_failed_student_behavior_probe_payload_v1(
    *,
    main_job_id: str,
    trace_job_id: str,
    metrics: dict[str, Any],
    gate_errors_v1: list[str],
    wall_clock_s_v1: float,
    wall_limit_s_v1: float,
    explicit_failure_reason_v1: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_FAILED_STUDENT_BEHAVIOR_PROBE_V1,
        "ok_v1": False,
        "job_id": main_job_id,
        "behavior_probe_trace_job_id_v1": trace_job_id,
        "authority_count_v1": metrics.get("authority_count_v1"),
        "sealed_count_v1": metrics.get("sealed_count_v1"),
        "rejection_count_v1": metrics.get("rejection_count_v1"),
        "contract_violation_count_v1": metrics.get("contract_violation_count_v1"),
        "probe_wall_clock_s_v1": wall_clock_s_v1,
        "probe_wall_limit_s_v1": wall_limit_s_v1,
        "gate_errors_v1": gate_errors_v1,
        "explicit_failure_reason_v1": explicit_failure_reason_v1,
        "rejection_reasons_v1": metrics.get("rejection_reasons_v1") or [],
        "first_three_failure_examples_v1": metrics.get("failure_samples_v1") or [],
    }


def build_failed_student_behavior_probe_timeout_payload_v1(
    *,
    main_job_id: str,
    trace_job_id: str,
    wall_clock_s_v1: float,
    wall_limit_s_v1: float,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_FAILED_STUDENT_BEHAVIOR_PROBE_V1,
        "ok_v1": False,
        "status_v1": FAILED_STUDENT_BEHAVIOR_PROBE_TIMEOUT_V1,
        "probe_timeout_v1": True,
        "job_id": main_job_id,
        "behavior_probe_trace_job_id_v1": trace_job_id,
        "authority_count_v1": None,
        "sealed_count_v1": None,
        "rejection_count_v1": None,
        "contract_violation_count_v1": None,
        "probe_wall_clock_s_v1": wall_clock_s_v1,
        "probe_wall_limit_s_v1": wall_limit_s_v1,
        "gate_errors_v1": [FAILED_STUDENT_BEHAVIOR_PROBE_TIMEOUT_V1],
        "explicit_failure_reason_v1": FAILED_STUDENT_BEHAVIOR_PROBE_TIMEOUT_V1,
        "rejection_reasons_v1": [],
        "first_three_failure_examples_v1": [],
    }


def _run_probe_seam_body_v1(
    *,
    results: list[dict[str, Any]],
    main_job_id: str,
    trace_jid: str,
    n_tr: int,
    wall_limit: float,
    exam_run_contract_request_v1: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    strategy_id: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Seam + trace scan + gates (runs in main process or probe subprocess)."""
    from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
        student_loop_seam_after_parallel_batch_v1,
    )

    prev_llm_cap = (os.environ.get("PATTERN_GAME_STUDENT_LLM_MAX_TRADES") or "").strip()
    os.environ["PATTERN_GAME_STUDENT_LLM_MAX_TRADES"] = str(max(n_tr + 2, _PROBE_MAX_TRADES_CAP))

    t0 = time.perf_counter()
    try:
        student_loop_seam_after_parallel_batch_v1(
            results=results,
            run_id=trace_jid,
            strategy_id=strategy_id,
            exam_run_contract_request_v1=exam_run_contract_request_v1
            if isinstance(exam_run_contract_request_v1, dict)
            else None,
            operator_batch_audit=operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
        )
    finally:
        if prev_llm_cap:
            os.environ["PATTERN_GAME_STUDENT_LLM_MAX_TRADES"] = prev_llm_cap
        else:
            os.environ.pop("PATTERN_GAME_STUDENT_LLM_MAX_TRADES", None)

    wall_s = time.perf_counter() - t0
    trace_path = default_learning_trace_events_jsonl()
    events = read_learning_trace_events_for_job_v1(trace_jid, path=trace_path, max_lines=2_000_000)
    metrics = _metrics_from_probe_trace_events_v1(events)

    ok_gate, gate_errs = evaluate_student_behavior_probe_gates_v1(
        metrics=metrics,
        wall_clock_s_v1=wall_s,
        wall_limit_s_v1=wall_limit,
    )
    summary: dict[str, Any] = {
        "probe_summary_v1": metrics,
        "probe_wall_clock_s_v1": wall_s,
        "probe_wall_limit_s_v1": wall_limit,
        "behavior_probe_trace_job_id_v1": trace_jid,
        "probe_pass_v1": ok_gate,
        "probe_outcome_v1": "PASS" if ok_gate else "FAIL",
    }
    if ok_gate:
        return None, summary

    explicit = "; ".join(gate_errs[:12]) if gate_errs else "probe_gates_failed_v1"
    return (
        build_failed_student_behavior_probe_payload_v1(
            main_job_id=main_job_id,
            trace_job_id=trace_jid,
            metrics=metrics,
            gate_errors_v1=gate_errs,
            wall_clock_s_v1=wall_s,
            wall_limit_s_v1=wall_limit,
            explicit_failure_reason_v1=explicit,
        ),
        summary,
    )


def _student_behavior_probe_child_main_v1(q: Any, kwargs: dict[str, Any]) -> None:
    """Spawn entry point — must stay module-level for ``multiprocessing`` spawn."""
    try:
        pair = _run_probe_seam_body_v1(**kwargs)
        q.put(("ok", pair[0], pair[1]))
    except Exception:
        import traceback

        q.put(("err", traceback.format_exc()[:12000]))


def execute_student_behavior_probe_v1(
    *,
    scenarios: list[dict[str, Any]],
    main_job_id: str,
    exam_run_contract_request_v1: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    telemetry_dir: Any,
    strategy_id: str | None,
    probe_progress_line_cb_v1: Any | None = None,
    probe_cancel_check_v1: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """
    Run seam directly on synthetic minimal outcomes.

    Returns ``(failure_payload_or_none, probe_summary_v1)``. On PASS, failure is ``None`` and summary carries counts.

    By default the seam body runs in a **spawn subprocess** and is **terminated** if it exceeds the wall SLA
    (RM-preflight-style hard timeout).     Optional ``probe_progress_line_cb_v1(line: str)`` receives elapsed/budget
    ticks and PASS/FAIL/TIMEOUT lines for the operator terminal.

    Optional ``probe_cancel_check_v1()`` is polled ~every 0.5s while the isolated subprocess runs (same idea as
    RM preflight cancel). When it returns True, the child is terminated and the probe returns with
    ``probe_cancelled_v1`` in the summary so the batch can finalize as **cancelled** without starting parallel workers.

    Does **not** invoke ``run_scenarios_parallel``.
    """
    from pathlib import Path

    from renaissance_v4.game_theory.live_telemetry_v1 import clear_job_telemetry_files

    def _line(msg: str) -> None:
        if probe_progress_line_cb_v1 is not None:
            try:
                probe_progress_line_cb_v1(msg)
            except Exception:
                pass

    empty_m = {
        "authority_count_v1": 0,
        "sealed_count_v1": 0,
        "rejection_count_v1": 0,
        "contract_violation_count_v1": 0,
        "failure_samples_v1": [],
        "rejection_reasons_v1": [],
    }
    if not scenarios:
        fl = build_failed_student_behavior_probe_payload_v1(
            main_job_id=main_job_id,
            trace_job_id="",
            metrics=empty_m,
            gate_errors_v1=["gate_probe_scenarios_nonempty_v1"],
            wall_clock_s_v1=0.0,
            wall_limit_s_v1=student_behavior_probe_max_wall_seconds_v1(),
            explicit_failure_reason_v1="probe_no_scenarios_v1",
        )
        return fl, {"probe_summary_v1": empty_m, "probe_pass_v1": False, "probe_outcome_v1": "FAIL"}

    n_tr = student_behavior_probe_trade_count_v1()
    trace_jid = behavior_probe_trace_job_id_v1(main_job_id)
    wall_limit = student_behavior_probe_max_wall_seconds_v1()
    _line(f"PROBE: started budget={wall_limit:.2f}s (hard timeout; subprocess={student_behavior_probe_subprocess_isolation_enabled_v1()})")

    td = Path(str(telemetry_dir)) if telemetry_dir is not None else None
    if td is not None:
        clear_job_telemetry_files(trace_jid, base=td)

    scen0 = copy.deepcopy(scenarios[0])
    results, prep_err = build_probe_minimal_results_v1(
        scenario=scen0,
        exam_run_contract_request_v1=exam_run_contract_request_v1,
        max_trades=n_tr,
    )
    if prep_err or not results:
        fl = build_failed_student_behavior_probe_payload_v1(
            main_job_id=main_job_id,
            trace_job_id=trace_jid,
            metrics=empty_m,
            gate_errors_v1=[f"probe_build_failed_v1:{prep_err or 'unknown'}"],
            wall_clock_s_v1=0.0,
            wall_limit_s_v1=wall_limit,
            explicit_failure_reason_v1=str(prep_err or "probe_build_failed_v1"),
        )
        _line("PROBE: FAIL (could not build minimal outcomes)")
        return fl, {"probe_summary_v1": empty_m, "probe_pass_v1": False, "probe_outcome_v1": "FAIL"}

    seam_kw: dict[str, Any] = {
        "results": results,
        "main_job_id": main_job_id,
        "trace_jid": trace_jid,
        "n_tr": n_tr,
        "wall_limit": wall_limit,
        "exam_run_contract_request_v1": exam_run_contract_request_v1
        if isinstance(exam_run_contract_request_v1, dict)
        else None,
        "operator_batch_audit": operator_batch_audit if isinstance(operator_batch_audit, dict) else None,
        "strategy_id": strategy_id,
    }

    t_wall0 = time.monotonic()
    if probe_cancel_check_v1 is not None and probe_cancel_check_v1():
        elapsed = time.monotonic() - t_wall0
        _line(f"PROBE: CANCELLED elapsed={elapsed:.2f}s — operator stop before seam execution")
        return None, {
            "probe_summary_v1": empty_m,
            "probe_wall_clock_s_v1": elapsed,
            "probe_wall_limit_s_v1": wall_limit,
            "behavior_probe_trace_job_id_v1": trace_jid,
            "probe_pass_v1": False,
            "probe_outcome_v1": "CANCELLED",
            "probe_cancelled_v1": True,
        }

    use_subproc = student_behavior_probe_subprocess_isolation_enabled_v1()
    stop_hb = threading.Event()

    def _heartbeat_loop_v1() -> None:
        while not stop_hb.wait(1.0):
            el = time.monotonic() - t_wall0
            _line(f"PROBE: elapsed={el:.2f}s budget={wall_limit:.2f}s")

    hb_thread = threading.Thread(target=_heartbeat_loop_v1, name="student_behavior_probe_hb_v1", daemon=True)
    hb_thread.start()

    failure: dict[str, Any] | None = None
    summary: dict[str, Any] = {}

    try:
        if use_subproc:
            ctx = multiprocessing.get_context("spawn")
            q = ctx.Queue(maxsize=1)
            proc = ctx.Process(target=_student_behavior_probe_child_main_v1, args=(q, seam_kw))
            proc.start()
            deadline = time.monotonic() + float(wall_limit)
            while proc.is_alive():
                if probe_cancel_check_v1 is not None and probe_cancel_check_v1():
                    proc.terminate()
                    proc.join(2.0)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(2.0)
                    elapsed = time.monotonic() - t_wall0
                    _line(f"PROBE: CANCELLED elapsed={elapsed:.2f}s — operator stop (subprocess terminated)")
                    return None, {
                        "probe_summary_v1": empty_m,
                        "probe_wall_clock_s_v1": elapsed,
                        "probe_wall_limit_s_v1": wall_limit,
                        "behavior_probe_trace_job_id_v1": trace_jid,
                        "probe_pass_v1": False,
                        "probe_outcome_v1": "CANCELLED",
                        "probe_cancelled_v1": True,
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                proc.join(timeout=min(0.5, max(remaining, 0.01)))
            if proc.is_alive():
                proc.terminate()
                proc.join(2.0)
                if proc.is_alive():
                    proc.kill()
                    proc.join(2.0)
                elapsed = time.monotonic() - t_wall0
                _line(f"PROBE: TIMEOUT elapsed={elapsed:.2f}s budget={wall_limit:.2f}s — seam subprocess terminated")
                fl = build_failed_student_behavior_probe_timeout_payload_v1(
                    main_job_id=main_job_id,
                    trace_job_id=trace_jid,
                    wall_clock_s_v1=elapsed,
                    wall_limit_s_v1=wall_limit,
                )
                return fl, {
                    "probe_summary_v1": empty_m,
                    "probe_wall_clock_s_v1": elapsed,
                    "probe_wall_limit_s_v1": wall_limit,
                    "behavior_probe_trace_job_id_v1": trace_jid,
                    "probe_pass_v1": False,
                    "probe_outcome_v1": "TIMEOUT",
                    "probe_timeout_v1": True,
                }
            try:
                raw = q.get(timeout=5.0)
            except Exception:
                raw = None
            if raw is None or not isinstance(raw, tuple) or len(raw) < 1:
                elapsed = time.monotonic() - t_wall0
                _line(f"PROBE: TIMEOUT — invalid subprocess result")
                fl = build_failed_student_behavior_probe_timeout_payload_v1(
                    main_job_id=main_job_id,
                    trace_job_id=trace_jid,
                    wall_clock_s_v1=elapsed,
                    wall_limit_s_v1=wall_limit,
                )
                return fl, {
                    "probe_summary_v1": empty_m,
                    "probe_wall_clock_s_v1": elapsed,
                    "probe_wall_limit_s_v1": wall_limit,
                    "behavior_probe_trace_job_id_v1": trace_jid,
                    "probe_pass_v1": False,
                    "probe_outcome_v1": "TIMEOUT",
                    "probe_timeout_v1": True,
                }
            kind = raw[0]
            if kind == "err":
                msg = str(raw[1]) if len(raw) > 1 else "unknown_err"
                elapsed = time.monotonic() - t_wall0
                fl = build_failed_student_behavior_probe_payload_v1(
                    main_job_id=main_job_id,
                    trace_job_id=trace_jid,
                    metrics=empty_m,
                    gate_errors_v1=[f"probe_subprocess_exception_v1:{msg[:2000]}"],
                    wall_clock_s_v1=elapsed,
                    wall_limit_s_v1=wall_limit,
                    explicit_failure_reason_v1="probe_subprocess_exception_v1",
                )
                _line(f"PROBE: FAIL elapsed={elapsed:.2f}s (subprocess error)")
                return fl, {
                    "probe_summary_v1": empty_m,
                    "probe_wall_clock_s_v1": elapsed,
                    "probe_wall_limit_s_v1": wall_limit,
                    "behavior_probe_trace_job_id_v1": trace_jid,
                    "probe_pass_v1": False,
                    "probe_outcome_v1": "FAIL",
                    "probe_subprocess_traceback_v1": msg[:8000],
                }
            if kind != "ok" or len(raw) != 3:
                elapsed = time.monotonic() - t_wall0
                fl = build_failed_student_behavior_probe_payload_v1(
                    main_job_id=main_job_id,
                    trace_job_id=trace_jid,
                    metrics=empty_m,
                    gate_errors_v1=["probe_subprocess_protocol_error_v1"],
                    wall_clock_s_v1=elapsed,
                    wall_limit_s_v1=wall_limit,
                    explicit_failure_reason_v1="probe_subprocess_protocol_error_v1",
                )
                _line(f"PROBE: FAIL elapsed={elapsed:.2f}s (protocol)")
                return fl, {"probe_summary_v1": empty_m, "probe_pass_v1": False, "probe_outcome_v1": "FAIL"}
            failure, summary = raw[1], raw[2]
        else:
            if probe_cancel_check_v1 is not None and probe_cancel_check_v1():
                elapsed = time.monotonic() - t_wall0
                _line(f"PROBE: CANCELLED elapsed={elapsed:.2f}s — operator stop before in-process seam")
                return None, {
                    "probe_summary_v1": empty_m,
                    "probe_wall_clock_s_v1": elapsed,
                    "probe_wall_limit_s_v1": wall_limit,
                    "behavior_probe_trace_job_id_v1": trace_jid,
                    "probe_pass_v1": False,
                    "probe_outcome_v1": "CANCELLED",
                    "probe_cancelled_v1": True,
                }
            failure, summary = _run_probe_seam_body_v1(**seam_kw)
    finally:
        stop_hb.set()

    ws = float(summary.get("probe_wall_clock_s_v1") or 0.0)
    outcome = str(summary.get("probe_outcome_v1") or ("PASS" if failure is None else "FAIL"))
    if failure is None:
        _line(f"PROBE: PASS wall_clock={ws:.2f}s budget={wall_limit:.2f}s")
    elif outcome != "TIMEOUT":
        _line(f"PROBE: FAIL wall_clock={ws:.2f}s budget={wall_limit:.2f}s")

    return failure, summary


__all__ = [
    "FAILED_STUDENT_BEHAVIOR_PROBE_TIMEOUT_V1",
    "SCHEMA_FAILED_STUDENT_BEHAVIOR_PROBE_V1",
    "behavior_probe_trace_job_id_v1",
    "build_failed_student_behavior_probe_payload_v1",
    "build_failed_student_behavior_probe_timeout_payload_v1",
    "evaluate_full_student_run_contract_v1",
    "finalize_seam_audit_authority_seal_contract_v1",
    "evaluate_student_behavior_probe_gates_v1",
    "execute_student_behavior_probe_v1",
    "profile_requires_student_behavior_probe_v1",
    "student_behavior_probe_enabled_v1",
    "student_behavior_probe_max_wall_seconds_v1",
    "student_behavior_probe_subprocess_isolation_enabled_v1",
    "student_behavior_probe_trade_count_v1",
]
