"""
parallel_runner.py

Run many pattern-game scenarios in parallel (separate processes) to use multiple cores.

SQLite is read by each worker; keep concurrent writes (experience log) in the parent process only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.groundhog_memory import resolve_memory_bundle_for_scenario
from renaissance_v4.game_theory.hunter_planner import resolve_repo_root
from renaissance_v4.game_theory.operator_test_harness_v1 import run_operator_test_harness_v1
from renaissance_v4.game_theory.pattern_game import (
    json_summary,
    prepare_effective_manifest_for_replay,
    run_pattern_game,
    score_binary_outcomes,
)
from renaissance_v4.game_theory.run_memory import (
    append_run_memory,
    build_operator_run_audit,
    build_run_memory_record,
)
from renaissance_v4.game_theory.memory_paths import (
    default_experience_log_jsonl,
    default_logs_root,
    default_run_memory_jsonl,
)
from renaissance_v4.game_theory.run_session_log import (
    allocate_unique_run_directory,
    write_batch_index_and_scenario_logs,
)
from renaissance_v4.game_theory.candle_timeframe_runtime import extract_candle_timeframe_minutes_for_replay
from renaissance_v4.game_theory.evaluation_window_runtime import extract_calendar_months_for_replay
from renaissance_v4.game_theory.live_telemetry_v1 import (
    build_live_telemetry_callback,
    telemetry_file_path,
)
from renaissance_v4.game_theory.scenario_contract import (
    extract_policy_contract_summary,
    resolve_scenario_manifest_path,
    extract_scenario_echo_fields,
    referee_session_outcome,
)
from renaissance_v4.game_theory.student_controlled_replay_v1 import attach_student_controlled_replay_v1
from renaissance_v4.manifest.validate import load_manifest_file

DEFAULT_WORKERS = max(1, (os.cpu_count() or 4))

# Hard cap: avoid fork/memory storms; soft recommendation = logical CPUs (CPU-bound replay).
_MAX_PARALLEL_ABS = 64

REFERENCE_COMPARISON_RECIPE_ID = "reference_comparison"
PATTERN_LEARNING_RECIPE_ID = "pattern_learning"
# Operator recipes that run ``run_operator_test_harness_v1`` (control + bounded candidates), not plain ``run_pattern_game``.
OPERATOR_LEARNING_HARNESS_RECIPE_IDS: frozenset[str] = frozenset(
    {REFERENCE_COMPARISON_RECIPE_ID, PATTERN_LEARNING_RECIPE_ID}
)


def validate_reference_comparison_batch_results(
    results: list[dict[str, Any]],
    *,
    operator_recipe_id: str | None,
) -> None:
    """
    Defense-in-depth: **Pattern Learning Run** and **Reference Comparison Run** must produce
    candidate search with candidates (operator harness path).

    Workers should already raise ``candidate_search_not_executed`` when ``candidate_count`` is 0;
    this batch guard catches wiring regressions.
    """
    if (operator_recipe_id or "").strip() not in OPERATOR_LEARNING_HARNESS_RECIPE_IDS:
        return
    problems: list[str] = []
    for r in results:
        if not r.get("ok"):
            continue
        la = r.get("learning_run_audit_v1")
        sid = str(r.get("scenario_id") or "?")
        if not isinstance(la, dict):
            problems.append(f"{sid}: missing learning_run_audit_v1")
            continue
        blk = la.get("context_candidate_search_block_v1") or {}
        cand = int(blk.get("candidate_count") or 0)
        ran = bool(blk.get("context_candidate_search_ran"))
        if not ran or cand <= 0:
            problems.append(
                f"{sid}: candidate_search_not_executed (ran={ran}, candidate_count={cand})"
            )
    if problems:
        tail = f" (+{len(problems) - 12} more)" if len(problems) > 12 else ""
        raise RuntimeError("learning_harness_invalid: " + " | ".join(problems[:12]) + tail)


def get_parallel_limits() -> dict[str, Any]:
    """
    Exposed for UI / API: recommended and maximum parallel workers for this host.

    Uses **processes** (not OS threads); each scenario runs a replay in a worker process.
    """
    cpu = os.cpu_count() or 4
    hard = min(_MAX_PARALLEL_ABS, max(1, cpu * 2))
    return {
        "cpu_logical_count": cpu,
        "recommended_max_workers": cpu,
        "hard_cap_workers": hard,
        "note": "Workers are processes, not Python threads; past ~CPU count yields diminishing returns for CPU-bound replay.",
    }


def _replay_outcomes_json_from_out(out: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Serialize Referee ``outcomes`` for the Student post-batch seam
    (:func:`renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1.student_loop_seam_after_parallel_batch_v1`).
    """
    raw = out.get("outcomes") or []
    out_j: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, OutcomeRecord):
            out_j.append(outcome_record_to_jsonable(item))
        elif isinstance(item, dict):
            out_j.append(item)
    return out_j


def clamp_parallel_workers(requested: int | None, num_scenarios: int) -> int:
    """Clamp user-requested worker count to [1, hard_cap, num_scenarios]."""
    if num_scenarios < 1:
        return 1
    limits = get_parallel_limits()
    hard = int(limits["hard_cap_workers"])
    if requested is None:
        return max(1, min(DEFAULT_WORKERS, num_scenarios, hard))
    try:
        w = int(requested)
    except (TypeError, ValueError):
        w = DEFAULT_WORKERS
    return max(1, min(w, num_scenarios, hard))


def _worker_run_one(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    Top-level for multiprocessing pickling. Returns JSON-friendly dict only.
    """
    sid = scenario.get("scenario_id", "unknown")
    try:
        mbp = scenario.get("memory_bundle_path")
        if mbp:
            mbp = str(Path(mbp).expanduser().resolve())
        else:
            mbp = resolve_memory_bundle_for_scenario(scenario, explicit_path=None)
        bar_m = extract_calendar_months_for_replay(scenario)
        candle_tf = extract_candle_timeframe_minutes_for_replay(scenario)
        recipe_id = str(scenario.get("operator_recipe_id") or "").strip()
        hres: dict[str, Any] | None = None
        tm = scenario.get("_live_telemetry_meta_v1")
        live_cb = (
            build_live_telemetry_callback(tm)
            if isinstance(tm, dict) and tm.get("file_path")
            else None
        )

        if recipe_id in OPERATOR_LEARNING_HARNESS_RECIPE_IDS:
            prep = prepare_effective_manifest_for_replay(
                scenario["manifest_path"],
                atr_stop_mult=scenario.get("atr_stop_mult"),
                atr_target_mult=scenario.get("atr_target_mult"),
                memory_bundle_path=mbp,
                use_groundhog_auto_resolve=False,
            )
            cmem = str(scenario.get("context_signature_memory_mode") or "").strip().lower()
            if cmem not in ("off", "read", "read_write"):
                cmem = "read_write"
            mem_jsonl = scenario.get("context_signature_memory_path")
            try:
                hres = run_operator_test_harness_v1(
                    prep.replay_path,
                    test_run_id=str(sid),
                    source_preset_or_manifest=str(scenario.get("manifest_path") or ""),
                    policy_framework_path=scenario.get("policy_framework_path"),
                    repo_root_for_git=resolve_repo_root(),
                    goal_v2=scenario.get("goal_v2") if isinstance(scenario.get("goal_v2"), dict) else None,
                    bar_window_calendar_months=bar_m,
                    candle_timeframe_minutes=candle_tf,
                    live_telemetry_callback=live_cb,
                    context_signature_memory_mode=cmem,
                    context_signature_memory_path=mem_jsonl,
                    decision_context_recall_memory_path=mem_jsonl,
                )
            finally:
                prep.cleanup()

            search_raw = hres["context_candidate_search_raw"]
            proof = search_raw["context_candidate_search_proof"]
            control_replay = search_raw["control_replay"]
            cand_n = int(proof.get("candidate_count") or 0)
            if cand_n <= 0:
                raise RuntimeError(
                    "candidate_search_not_executed: operator learning harness requires "
                    f"context-conditioned candidate search with candidates > 0 (got candidate_count={cand_n})"
                )

            panel = (hres.get("operator_test_harness_v1") or {}).get("context_memory_operator_panel_v1")
            pgm: dict[str, Any] = {
                "operator_test_harness_v1": hres.get("operator_test_harness_v1"),
                "operator_learning_harness_path_v1": True,
                "context_memory_operator_panel_v1": panel if isinstance(panel, dict) else None,
            }
            if recipe_id == REFERENCE_COMPARISON_RECIPE_ID:
                pgm["reference_comparison_learning_path_v1"] = True
            out = {
                **control_replay,
                "context_candidate_search_proof": proof,
                "manifest_effective": control_replay.get("manifest"),
                "binary_scorecard": score_binary_outcomes(list(control_replay.get("outcomes") or [])),
                "pattern_game_meta": pgm,
                "memory_bundle_proof": None,
                "memory_bundle_audit": prep.memory_bundle_audit,
            }
        else:
            cmem = str(scenario.get("context_signature_memory_mode") or "").strip().lower()
            if cmem not in ("off", "read", "read_write"):
                cmem = "off"
            mem_jsonl = scenario.get("context_signature_memory_path")
            out = run_pattern_game(
                scenario["manifest_path"],
                atr_stop_mult=scenario.get("atr_stop_mult"),
                atr_target_mult=scenario.get("atr_target_mult"),
                memory_bundle_path=mbp,
                use_groundhog_auto_resolve=False,
                emit_baseline_artifacts=bool(scenario.get("emit_baseline_artifacts", False)),
                verbose=False,
                bar_window_calendar_months=bar_m,
                candle_timeframe_minutes=candle_tf,
                live_telemetry_callback=live_cb,
                context_signature_memory_mode=cmem,
                context_signature_memory_path=mem_jsonl,
            )
        summ = json_summary(out, scenario=scenario)
        pfa = scenario.get("policy_framework_audit")
        if isinstance(pfa, dict) and pfa:
            summ = {**summ, "policy_framework_audit": pfa}
        learn = summ.get("learning_run_audit_v1")
        replay_outcomes_json = _replay_outcomes_json_from_out(out)
        row: dict[str, Any] = {
            "ok": True,
            "scenario_id": sid,
            "summary": summ,
            "replay_outcomes_json": replay_outcomes_json,
            "policy_contract": extract_policy_contract_summary(out.get("manifest_effective")),
            "referee_session": referee_session_outcome(True, summ),
            "validation_checksum": out.get("validation_checksum"),
            "cumulative_pnl": out.get("cumulative_pnl"),
            "dataset_bars": out.get("dataset_bars"),
            "manifest_path": str(scenario.get("manifest_path", "")),
            "memory_bundle_audit": out.get("memory_bundle_audit"),
            "memory_bundle_proof": out.get("memory_bundle_proof"),
            "replay_data_audit": out.get("replay_data_audit"),
            "replay_timeframe_minutes": out.get("replay_timeframe_minutes"),
            "dataset_bars_after_rollup": out.get("dataset_bars_after_rollup"),
            "atr_stop_mult": scenario.get("atr_stop_mult"),
            "atr_target_mult": scenario.get("atr_target_mult"),
            "learning_run_audit_v1": learn,
            "operator_learning_status_line_v1": summ.get("operator_learning_status_line_v1"),
        }
        if hres is not None:
            row["operator_test_harness_v1"] = hres.get("operator_test_harness_v1")
            hp = (hres.get("operator_test_harness_v1") or {}).get("context_memory_operator_panel_v1")
            if isinstance(hp, dict):
                row["context_memory_operator_panel_v1"] = hp
        row.update(extract_scenario_echo_fields(scenario))
        return row
    except Exception as e:
        pc: dict[str, Any] = {}
        try:
            mp = scenario.get("manifest_path")
            if mp and Path(mp).expanduser().is_file():
                pc = extract_policy_contract_summary(load_manifest_file(Path(mp).expanduser()))
        except Exception:
            pc = {}
        row = {
            "ok": False,
            "scenario_id": sid,
            "error": f"{type(e).__name__}: {e}",
            "manifest_path": str(scenario.get("manifest_path", "")),
            "policy_contract": pc,
            "referee_session": "ERROR",
            "summary": None,
            "atr_stop_mult": scenario.get("atr_stop_mult"),
            "atr_target_mult": scenario.get("atr_target_mult"),
        }
        row.update(extract_scenario_echo_fields(scenario))
        return row


class ParallelBatchCancelledError(Exception):
    """
    Raised when ``cancel_check`` returns true mid-batch.

    ``partial_results`` lists worker result dicts for scenarios that finished before cancel
    (completion order); scenarios still queued or cancelled pending are not included.
    """

    def __init__(self, partial_results: list[dict[str, Any]]) -> None:
        self.partial_results = partial_results
        super().__init__("parallel_batch_cancelled")


def _normalize_scenario(s: dict[str, Any]) -> dict[str, Any]:
    """Resolve manifest path so worker processes do not depend on cwd."""
    n = dict(s)
    mp = n.get("manifest_path")
    if mp:
        n["manifest_path"] = str(resolve_scenario_manifest_path(mp))
    return n


def run_scenarios_parallel(
    scenarios: list[dict[str, Any]],
    *,
    max_workers: int | None = None,
    experience_log_path: Path | str | None = None,
    run_memory_log_path: Path | str | None = None,
    write_session_logs: bool = True,
    session_logs_base: Path | str | None = None,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
    on_session_log_batch: Callable[[Path], None] | None = None,
    telemetry_job_id: str | None = None,
    telemetry_dir: Path | str | None = None,
    telemetry_context: dict[str, Any] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """
    Run each scenario in a process pool. Order of results is **completion** order unless you sort by scenario_id.

    Each scenario dict should include ``manifest_path`` and optional ``scenario_id``, ``atr_stop_mult``,
    ``atr_target_mult``, ``emit_baseline_artifacts``. Optional **echo** fields (tier,
    ``evaluation_window``, ``agent_explanation``, ids, etc.) are copied into each result for audit;
    the Referee does not use them for scoring. See ``scenario_contract.py`` / README.
    Successful rows include ``replay_outcomes_json`` (``OutcomeRecord`` JSON for each closed trade)
    for the Student post-batch seam.

    If ``experience_log_path`` is set, append one JSON line per result (parent process only).

    If ``run_memory_log_path`` is set, append one structured :mod:`run_memory` JSONL line per
    result (hypothesis + indicator_context + referee summary — durable audit trail).

    If ``write_session_logs`` is True (default), create ``logs/batch_<UTC>_<id>/`` with one subfolder
    per scenario containing ``HUMAN_READABLE.md`` and ``run_record.json``, plus **batch_parallel_results_v1.json**
    (full worker rows including ``replay_outcomes_json``) for D13 Student panel trade enumeration. Disable with
    ``write_session_logs=False`` or env ``PATTERN_GAME_NO_SESSION_LOG=1``.

    If ``progress_callback`` is set, it is invoked after each scenario completes as
    ``(completed_count, total_count, result_row)`` for live progress UIs.

    When ``telemetry_job_id`` and ``telemetry_dir`` are set, each scenario gets
    ``_live_telemetry_meta_v1`` so workers can write live JSON snapshots (see
    :mod:`renaissance_v4.game_theory.live_telemetry_v1`). ``telemetry_context`` is merged into
    that metadata (recipe id, framework id, evaluation window, learning path mode).

    If session logs are written and ``on_session_log_batch`` is set, it is called once with the
    ``batch_*`` directory path (for UIs and APIs).

    If ``cancel_check`` is set, it is polled after each ``wait`` slice (~0.5s) and after each
    completed scenario. When it returns true, pending futures are cancelled where possible
    (``cancel_futures=True``), already-running worker processes may still finish on their own,
    and :class:`ParallelBatchCancelledError` is raised with ``partial_results`` collected so far.
    """
    if not scenarios:
        raise ValueError(
            "run_scenarios_parallel: scenarios list is empty — refusing a no-op batch "
            "(callers must validate before submit; web UI uses _prepare_parallel_payload)."
        )

    normalized = [_normalize_scenario(s) for s in scenarios]
    if telemetry_job_id:
        tjid = str(telemetry_job_id).strip()
        for s in normalized:
            s["_batch_job_id_v1"] = tjid

    if telemetry_job_id and telemetry_dir:
        tdir = Path(str(telemetry_dir)).expanduser().resolve()
        tdir.mkdir(parents=True, exist_ok=True)
        ctx = dict(telemetry_context or {})
        for i, s in enumerate(normalized):
            sid = str(s.get("scenario_id") or f"row_{i}")
            path = telemetry_file_path(telemetry_job_id, sid, base=tdir)
            meta: dict[str, Any] = {
                "file_path": str(path),
                "job_id": telemetry_job_id,
                "scenario_id": sid,
                "scenario_index": i + 1,
                "scenario_total": len(normalized),
                **ctx,
            }
            s["_live_telemetry_meta_v1"] = meta

    workers = clamp_parallel_workers(max_workers, len(normalized))
    total = len(normalized)

    results: list[dict[str, Any]] = []
    cancelled_early = False
    ex = ProcessPoolExecutor(max_workers=workers)
    try:
        futures = {ex.submit(_worker_run_one, s): s for s in normalized}
        pending = set(futures.keys())
        completed = 0
        while pending:
            if cancel_check is not None and cancel_check():
                cancelled_early = True
                break
            done_now, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
            if done_now:
                for fut in done_now:
                    row = fut.result()
                    results.append(row)
                    completed += 1
                    if progress_callback is not None:
                        progress_callback(completed, total, row)
    finally:
        ex.shutdown(wait=not cancelled_early, cancel_futures=cancelled_early)

    if cancelled_early:
        if experience_log_path is not None and results:
            p = Path(experience_log_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as fh:
                for row in results:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        raise ParallelBatchCancelledError(results)

    if experience_log_path is not None:
        p = Path(experience_log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_sid = {str(s.get("scenario_id", "")): s for s in normalized}
    mem_p = Path(run_memory_log_path) if run_memory_log_path is not None else None
    if mem_p is not None:
        mem_p.parent.mkdir(parents=True, exist_ok=True)

    session_ok = write_session_logs and os.environ.get("PATTERN_GAME_NO_SESSION_LOG", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )
    session_records: list[tuple[str, dict[str, Any]]] = []

    for row in results:
        sid = str(row.get("scenario_id", "")) or "unknown"
        scen = by_sid.get(str(row.get("scenario_id", "")))
        mp = str(row.get("manifest_path") or (scen or {}).get("manifest_path", ""))
        summ = row.get("summary") if row.get("ok") else None
        err = None if row.get("ok") else str(row.get("error", "unknown"))
        atr_s = None
        atr_t = None
        if scen:
            atr_s = scen.get("atr_stop_mult")
            atr_t = scen.get("atr_target_mult")
            if isinstance(atr_s, (int, float)):
                atr_s = float(atr_s)
            else:
                atr_s = None
            if isinstance(atr_t, (int, float)):
                atr_t = float(atr_t)
            else:
                atr_t = None
        prior_rid = None
        if scen and scen.get("prior_run_id") is not None:
            prior_rid = str(scen["prior_run_id"])
        rec = build_run_memory_record(
            source="parallel_scenarios",
            manifest_path=mp,
            json_summary_row=summ,
            scenario=scen,
            parallel_error=err,
            atr_stop_mult=atr_s,
            atr_target_mult=atr_t,
            prior_run_id=prior_rid,
            memory_bundle_audit=row.get("memory_bundle_audit"),
            operator_run_audit=build_operator_run_audit(scen, summ),
            learning_run_audit_v1=row.get("learning_run_audit_v1")
            if isinstance(row.get("learning_run_audit_v1"), dict)
            else None,
        )
        if mem_p is not None:
            append_run_memory(mem_p, rec)
        if session_ok:
            session_records.append((sid, rec))

    if session_ok and session_records:
        root_raw = session_logs_base or os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT")
        log_root = Path(root_raw).expanduser() if root_raw else default_logs_root()
        batch_dir = allocate_unique_run_directory(logs_root=log_root, prefix="batch")
        write_batch_index_and_scenario_logs(batch_dir, session_records)
        bp_payload: dict[str, Any] = {
            "schema": "batch_parallel_results_v1",
            "written_at_utc": datetime.now(timezone.utc).isoformat(),
            "scenario_order": [
                str(s.get("scenario_id") or f"row_{i}") for i, s in enumerate(normalized)
            ],
            "results": results,
        }
        (batch_dir / "batch_parallel_results_v1.json").write_text(
            json.dumps(bp_payload, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        print(
            f"[session_log] batch folder={batch_dir} ({len(session_records)} scenarios — see BATCH_README.md)",
            file=sys.stderr,
        )
        if on_session_log_batch is not None:
            on_session_log_batch(batch_dir)

    # --- GT_DIRECTIVE_024C: Student-controlled replay (parent process; learning trace safe) ---
    rows_by_sid: dict[str, dict[str, Any]] = {}
    for r in results:
        sid_k = str((r or {}).get("scenario_id") or "")
        if sid_k:
            rows_by_sid[sid_k] = r
    for s in normalized:
        if not s.get("enable_student_controlled_replay_v1"):
            continue
        sid_k = str(s.get("scenario_id") or "")
        if not sid_k:
            continue
        row = rows_by_sid.get(sid_k)
        if not row or not row.get("ok"):
            continue
        fp = s.get("exam_run_fingerprint_preview_v1") or s.get("fingerprint_sha256_40") or s.get("fingerprint")
        job_e = telemetry_job_id or s.get("_batch_job_id_v1")
        row["student_controlled_replay_v1"] = attach_student_controlled_replay_v1(
            s,
            row,
            job_id=str(job_e).strip() if job_e else None,
            fingerprint=str(fp).strip() if fp else None,
        )

    return results


def _load_scenarios_from_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict) and "scenarios" in raw:
        s = raw["scenarios"]
        return [x for x in s if isinstance(x, dict)]
    raise ValueError("JSON must be a list of scenario objects or { \"scenarios\": [ ... ] }")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run multiple pattern-game scenarios in parallel (process pool).",
    )
    parser.add_argument(
        "scenarios_json",
        type=str,
        help="JSON file: list of { scenario_id?, manifest_path, atr_stop_mult?, atr_target_mult? }",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help=f"Max parallel workers (default: min(cpu_count, num scenarios), ~{DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="Append JSONL results to this path (default: game_theory/experience_log.jsonl)",
    )
    parser.add_argument(
        "--run-memory-log",
        type=str,
        nargs="?",
        const="default",
        default=None,
        help="Also append structured run_memory JSONL (default: game_theory/run_memory.jsonl)",
    )
    parser.add_argument(
        "--no-session-log",
        action="store_true",
        help="Skip logs/batch_<UTC>_<id>/ human-readable folders (default: session logs ON)",
    )
    parser.add_argument(
        "--session-logs-root",
        type=str,
        default=None,
        help="Base directory for batch session folders (default: game_theory/logs)",
    )
    args = parser.parse_args()
    scenarios_path = Path(args.scenarios_json)
    scenarios = _load_scenarios_from_json(scenarios_path)

    log_path = args.log
    if log_path is None:
        log_path = default_experience_log_jsonl()

    rmem: Path | None = None
    if args.run_memory_log is not None:
        rmem = (
            default_run_memory_jsonl()
            if args.run_memory_log in ("default", "1")
            else Path(args.run_memory_log).expanduser()
        )

    sl_root = Path(args.session_logs_root).expanduser() if args.session_logs_root else None
    results = run_scenarios_parallel(
        scenarios,
        max_workers=args.jobs,
        experience_log_path=log_path,
        run_memory_log_path=rmem,
        write_session_logs=not args.no_session_log,
        session_logs_base=sl_root,
    )
    ok = sum(1 for r in results if r.get("ok"))
    print(json.dumps({"ran": len(results), "ok": ok, "failed": len(results) - ok, "results": results}, indent=2))


if __name__ == "__main__":
    main()
