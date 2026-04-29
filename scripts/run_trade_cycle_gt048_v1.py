#!/usr/bin/env python3
"""
GT048 — Production learning path (scorecard + L3 + governance, no patches).

Runs one scenario through ``run_scenarios_parallel`` (writes ``batch_parallel_results_v1.json``
under session logs), registers ``batch_scorecard.jsonl`` via ``record_parallel_batch_finished``,
then ``student_loop_seam_after_parallel_batch_v1`` so ``classify_trade_memory_promotion_v1`` can
**promote** without mocks.

Isolation: sets ``PATTERN_GAME_MEMORY_ROOT`` to ``runtime/gt048_cycle/<job-id>/`` so scorecard +
logs stay out of the repo default tree.

Usage::

  PYTHONPATH=. python3 scripts/run_trade_cycle_gt048_v1.py \\
    --bars 100 \\
    --job-id gt048-prod-001

Exit: 0 pass, 2 insufficient trades, 3 acceptance fail, 4 error.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")


def _bootstrap_env(job_id: str) -> Path:
    root = (_REPO / "runtime" / "gt048_cycle" / job_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["PATTERN_GAME_MEMORY_ROOT"] = str(root)
    store = root / "student_learning_records_v1.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"] = str(store)
    if store.is_file():
        store.unlink()
    return root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bars", type=int, default=100, help="Replay tail bars (rm_preflight_replay_tail_bars_v1).")
    ap.add_argument("--job-id", type=str, required=True, dest="job_id")
    ap.add_argument("--manifest", type=str, default=str(_DEFAULT_MANIFEST()))
    args = ap.parse_args()

    jid = str(args.job_id).strip()
    if not jid:
        print("ERROR: --job-id required", file=sys.stderr)
        return 4

    _bootstrap_env(jid)

    # Imports after env so memory paths resolve under gt048_cycle/<job_id>.
    from renaissance_v4.core.outcome_record import (
        OutcomeRecord,
        outcome_record_from_jsonable,
        outcome_record_to_jsonable,
    )
    from renaissance_v4.game_theory.batch_scorecard import record_parallel_batch_finished, utc_timestamp_iso
    from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
    from renaissance_v4.game_theory.scenario_contract import resolve_scenario_manifest_path
    from renaissance_v4.game_theory.student_proctor.contracts_v1 import FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1
    from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
        build_student_decision_packet_v1_with_cross_run_retrieval,
    )
    from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1
    from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import build_student_decision_packet_v1
    from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
        student_loop_seam_after_parallel_batch_v1,
    )
    from renaissance_v4.utils.db import DB_PATH

    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_file():
        alt = _REPO / manifest_path
        manifest_path = alt if alt.is_file() else manifest_path
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        return 4

    mp_resolved = str(resolve_scenario_manifest_path(manifest_path))
    scenario_sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in jid)[:120]
    scenario = {
        "scenario_id": scenario_sid or "gt048_scenario",
        "manifest_path": mp_resolved,
        "rm_preflight_replay_tail_bars_v1": int(args.bars),
    }

    tf_min = 5
    ob_audit = {"candle_timeframe_minutes": tf_min}
    scorecard_extras = {"skip_cold_baseline": True}

    batch_dirs: list[Path] = []

    def _capture_batch(p: Path) -> None:
        batch_dirs.append(Path(p))

    def _run_parallel(telemetry_job_id: str) -> list[dict[str, Any]]:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return run_scenarios_parallel(
                [scenario],
                max_workers=1,
                write_session_logs=True,
                telemetry_job_id=telemetry_job_id,
                on_session_log_batch=_capture_batch,
            )

    start_unix = time.time()
    started_utc = utc_timestamp_iso()

    try:
        results = _run_parallel(jid)
    except Exception as e:
        print(f"ERROR: parallel replay failed: {e}", file=sys.stderr)
        return 4

    if not batch_dirs:
        print("ERROR: session batch directory not captured", file=sys.stderr)
        return 4
    batch_dir = batch_dirs[0]

    if not results or not results[0].get("ok"):
        err = (results[0].get("error") if results else None) or "unknown"
        print(f"ERROR: worker failed: {err}", file=sys.stderr)
        return 4

    out0 = results[0]
    raw_oj = out0.get("replay_outcomes_json") or []
    outcomes: list[OutcomeRecord] = []
    for item in raw_oj:
        if not isinstance(item, dict):
            continue
        try:
            outcomes.append(outcome_record_from_jsonable(item))
        except (TypeError, ValueError):
            continue

    if not outcomes:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from renaissance_v4.game_theory.pattern_game import run_pattern_game

            prep = run_pattern_game(
                Path(mp_resolved),
                use_groundhog_auto_resolve=False,
                emit_baseline_artifacts=False,
                verbose=False,
                replay_max_bars_v1=int(args.bars),
            )
            outcomes = list(prep.get("outcomes") or [])

    n_closed = len(outcomes)
    min_tr = 5
    if n_closed < min_tr:
        print(
            f"ERROR: need >={min_tr} closed trades for stable proof, got {n_closed}",
            file=sys.stderr,
        )
        return 2

    replay_json = [outcome_record_to_jsonable(o) for o in outcomes]

    try:
        record_parallel_batch_finished(
            job_id=jid,
            started_at_utc=started_utc,
            start_unix=start_unix,
            total_scenarios=1,
            workers_used=1,
            results=results,
            session_log_batch_dir=str(batch_dir.resolve()),
            error=None,
            source="gt048_cli",
            path=None,
            operator_batch_audit=ob_audit,
            student_seam_observability_v1=None,
            exam_run_line_meta_v1=scorecard_extras,
        )
    except Exception as e:
        print(f"ERROR: record_parallel_batch_finished: {e}", file=sys.stderr)
        return 4

    try:
        seam1 = student_loop_seam_after_parallel_batch_v1(
            results=[
                {
                    "ok": True,
                    "scenario_id": scenario_sid,
                    "replay_outcomes_json": replay_json,
                }
            ],
            run_id=jid,
            db_path=DB_PATH,
            store_path=os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"],
            operator_batch_audit=ob_audit,
        )
    except Exception as e:
        print(f"ERROR: seam pass1: {e}", file=sys.stderr)
        return 4

    def _promote_count(seam: dict[str, Any]) -> int:
        mb = seam.get("memory_promotion_batch_v1") or {}
        n = 0
        for row in mb.get("per_trade") or []:
            gov = row.get("learning_governance_v1") if isinstance(row.get("learning_governance_v1"), dict) else {}
            if str(gov.get("decision") or "").strip().lower() != "promote":
                continue
            if row.get("stored") is False:
                continue
            n += 1
        return n

    promoted = _promote_count(seam1)
    appended = int(seam1.get("student_learning_rows_appended") or 0)
    if promoted <= 0 and appended <= 0:
        errs = seam1.get("errors") or []
        print(
            json.dumps(
                {
                    "error": "no_learning_rows",
                    "seam_pass1": seam1,
                    "errors": errs[:20],
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3

    if promoted <= 0:
        errs = seam1.get("errors") or []
        print(
            json.dumps(
                {
                    "error": "no_memory_promotion_decisions",
                    "student_learning_rows_appended": appended,
                    "seam_pass1": seam1,
                    "errors": errs[:20],
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3

    # Pass 2: deterministic replay + scorecard + seam (different run_id → new record_ids).
    jid2 = f"{jid}-pass2"
    start_unix2 = time.time()
    started_utc2 = utc_timestamp_iso()
    batch_dirs.clear()
    try:
        results2 = _run_parallel(jid2)
    except Exception as e:
        print(f"ERROR: parallel pass2: {e}", file=sys.stderr)
        return 4
    if not batch_dirs:
        print("ERROR: batch dir pass2 missing", file=sys.stderr)
        return 4
    batch_dir2 = batch_dirs[0]

    try:
        record_parallel_batch_finished(
            job_id=jid2,
            started_at_utc=started_utc2,
            start_unix=start_unix2,
            total_scenarios=1,
            workers_used=1,
            results=results2,
            session_log_batch_dir=str(batch_dir2.resolve()),
            error=None,
            source="gt048_cli_pass2",
            path=None,
            operator_batch_audit=ob_audit,
            exam_run_line_meta_v1=scorecard_extras,
        )
    except Exception as e:
        print(f"ERROR: scorecard pass2: {e}", file=sys.stderr)
        return 4

    try:
        seam2 = student_loop_seam_after_parallel_batch_v1(
            results=[
                {
                    "ok": True,
                    "scenario_id": scenario_sid,
                    "replay_outcomes_json": replay_json,
                }
            ],
            run_id=jid2,
            db_path=DB_PATH,
            store_path=os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"],
            operator_batch_audit=ob_audit,
        )
    except Exception as e:
        print(f"ERROR: seam pass2: {e}", file=sys.stderr)
        return 4

    retrieval_later = int(seam2.get("student_retrieval_matches") or 0)

    t2 = outcomes[1]
    sk2 = f"student_entry_v1:{t2.symbol}:{t2.entry_time}:{int(tf_min)}"
    store_p = Path(os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"])
    pkt_b, _eb = build_student_decision_packet_v1(
        db_path=DB_PATH,
        symbol=t2.symbol,
        decision_open_time_ms=int(t2.entry_time),
        candle_timeframe_minutes=tf_min,
        max_bars_in_packet=500,
    )
    pkt_rx, _er = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=DB_PATH,
        symbol=t2.symbol,
        decision_open_time_ms=int(t2.entry_time),
        candle_timeframe_minutes=tf_min,
        store_path=store_p,
        retrieval_signature_key=sk2,
        max_bars_in_packet=500,
    )
    changed = False
    if pkt_b and pkt_rx:
        so0, e0 = emit_shadow_stub_student_output_v1(
            pkt_b, graded_unit_id=str(t2.trade_id), decision_at_ms=int(t2.entry_time)
        )
        so1, e1 = emit_shadow_stub_student_output_v1(
            pkt_rx, graded_unit_id=str(t2.trade_id), decision_at_ms=int(t2.entry_time)
        )
        if not e0 and not e1 and so0 and so1:
            keys = ("confidence_01", "student_decision_ref", "pattern_recipe_ids", "reasoning_text")
            changed = any(so0.get(k) != so1.get(k) for k in keys)

    rx_n = 0
    if isinstance(pkt_rx, dict):
        rx = pkt_rx.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
        rx_n = len(rx) if isinstance(rx, list) else 0

    proof = {
        "directive": "GT048",
        "job_id": jid,
        "memory_root": os.environ.get("PATTERN_GAME_MEMORY_ROOT"),
        "student_learning_store": os.environ.get("PATTERN_GAME_STUDENT_LEARNING_STORE"),
        "session_log_batch_dir_pass1": str(batch_dir.resolve()),
        "closed_trades": n_closed,
        "memory_rows_promoted": promoted,
        "retrieval_matches_later": max(retrieval_later, rx_n),
        "decisions_changed_due_to_memory_or_ev": changed,
        "seam_pass1": {
            "student_learning_rows_appended": seam1.get("student_learning_rows_appended"),
            "student_retrieval_matches": seam1.get("student_retrieval_matches"),
        },
        "seam_pass2": {
            "student_learning_rows_appended": seam2.get("student_learning_rows_appended"),
            "student_retrieval_matches": seam2.get("student_retrieval_matches"),
        },
        "acceptance": {
            "memory_rows_promoted_gt_0": promoted > 0,
            "retrieval_matches_later_gt_0": max(retrieval_later, rx_n) > 0,
            "met": promoted > 0 and max(retrieval_later, rx_n) > 0,
        },
    }

    out_path = Path(os.environ["PATTERN_GAME_MEMORY_ROOT"]) / "gt048_proof.json"
    out_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))

    if not proof["acceptance"]["met"]:
        return 3
    return 0


def _DEFAULT_MANIFEST() -> Path:
    return _REPO / "renaissance_v4" / "configs" / "manifests" / "sr1_deterministic_trade_proof_v1.json"


if __name__ == "__main__":
    raise SystemExit(main())
