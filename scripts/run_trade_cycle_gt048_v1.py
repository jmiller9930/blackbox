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

  PYTHONPATH=. python3 scripts/run_trade_cycle_gt048_v1.py \\
    --bars 2000 --symbol SOLUSDT --timeframe 15m \\
    --job-id d9-generalization-proof-001 \\
    --promotion-e-min -0.05 --gt051-report

  PYTHONPATH=. python3 scripts/run_trade_cycle_gt048_v1.py \\
    --bars 6000 --symbol SOLUSDT --timeframe 15m \\
    --job-id d11-triple-barrier-proof-001 \\
    --promotion-e-min -0.05 --enable-labels --walk-forward --gt055-report

Each successful run writes ``gt056`` (opportunity selection metrics from Referee truth × pass2 learning rows) into ``gt048_proof.json``.
Use ``--gt057-tape-repeat N`` when the SQLite fixture is short (GT057 density unlock).

Exit: 0 pass, 2 insufficient trades, 3 acceptance fail, 4 error, 5 enforce-gt050 fail, 6 enforce-gt051 fail.
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


def _parse_timeframe_to_minutes(tf: str | None) -> int:
    """Replay rollup granularity; must be >=5 and a multiple of 5 (5m base bars)."""
    if tf is None or not str(tf).strip():
        return 5
    s = str(tf).strip().lower()
    if s.endswith("m"):
        n = int(s[:-1])
    elif s.endswith("h"):
        n = int(s[:-1]) * 60
    else:
        n = int(float(s))
    if n < 5:
        n = 5
    if n % 5 != 0:
        raise ValueError(f"timeframe minutes must be a multiple of 5, got {n}")
    return n


def _write_effective_manifest(
    *,
    repo: Path,
    base_manifest: Path,
    symbol: str | None,
    timeframe_label: str | None,
    job_root: Path,
) -> Path:
    """Copy SR1-style manifest with optional symbol/timeframe overrides (audit + replay hints)."""
    data = json.loads(base_manifest.read_text(encoding="utf-8"))
    if symbol:
        data["symbol"] = str(symbol).strip().upper()
    if timeframe_label:
        data["timeframe"] = str(timeframe_label).strip().lower()
    sid = str(data.get("strategy_id") or "manifest")
    data["strategy_id"] = f"{sid}_gt048_overlay_v1"
    out = job_root / "effective_manifest_gt048.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _bootstrap_env(job_id: str) -> Path:
    root = (_REPO / "runtime" / "gt048_cycle" / job_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["PATTERN_GAME_MEMORY_ROOT"] = str(root)
    store = root / "student_learning_records_v1.jsonl"
    store.parent.mkdir(parents=True, exist_ok=True)
    os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"] = str(store)
    if store.is_file():
        store.unlink()
    # Parallel scorecard uses total_processed=scenario rows (often 1). Do not let a host env of
    # PATTERN_GAME_STUDENT_PROMOTION_MIN_SCENARIOS>1 force hold_insufficient_sample_v1 on every trade.
    os.environ["PATTERN_GAME_STUDENT_PROMOTION_MIN_SCENARIOS"] = "1"
    return root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bars", type=int, default=100, help="Replay tail bars (rm_preflight_replay_tail_bars_v1).")
    ap.add_argument("--job-id", type=str, required=True, dest="job_id")
    ap.add_argument("--manifest", type=str, default=str(_DEFAULT_MANIFEST()))
    ap.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Override manifest symbol (e.g. SOLUSDT).",
    )
    ap.add_argument(
        "--timeframe",
        type=str,
        default=None,
        help='Replay candle timeframe label / rollup (e.g. "15m" → 15-minute bars from 5m DB).',
    )
    ap.add_argument(
        "--min-closed-trades",
        type=int,
        default=5,
        dest="min_closed_trades",
        help="Minimum closed trades required before seam (GT050 often uses 100+).",
    )
    ap.add_argument(
        "--enforce-gt050",
        action="store_true",
        help="Exit 5 if GT050 loss_avoided_count < 1 (large-cycle loss-avoidance proof).",
    )
    ap.add_argument(
        "--gt051-report",
        action="store_true",
        help="Append GT051 generalization probes (near-match, regime, EV bins, OOS split) to gt048_proof.json.",
    )
    ap.add_argument(
        "--enforce-gt051",
        action="store_true",
        help="Exit 6 if GT051 acceptance fails (requires --gt051-report).",
    )
    ap.add_argument(
        "--enable-labels",
        action="store_true",
        dest="enable_labels",
        help="GT055: attach triple-barrier labels (TP/SL/time) and timing fields to referee_outcome_subset.",
    )
    ap.add_argument(
        "--walk-forward",
        action="store_true",
        dest="walk_forward",
        help="GT055: record walk-forward intent (use with --gt055-report).",
    )
    ap.add_argument(
        "--gt055-report",
        action="store_true",
        dest="gt055_report",
        help="Append GT055 walk-forward label-learning proof to gt048_proof.json.",
    )
    ap.add_argument(
        "--promotion-e-min",
        type=float,
        default=None,
        dest="promotion_e_min",
        metavar="E",
        help=(
            "Set PATTERN_GAME_STUDENT_PROMOTION_E_MIN for this process (governance). "
            "Large replays often have slightly negative batch expectancy; use e.g. -0.05 so clean-L3 "
            "trades can still PROMOTE (GT048/GT050 harness)."
        ),
    )
    ap.add_argument(
        "--gt057-tape-repeat",
        type=int,
        default=None,
        dest="gt057_tape_repeat",
        metavar="N",
        help=(
            "GT057 trade-density unlock: set GT057_REPLAY_TAPE_REPEAT_V1 so replay repeats the "
            "resolved tape N times with shifted timestamps (short fixture DBs)."
        ),
    )
    ap.add_argument(
        "--gt058-label-gate",
        action="store_true",
        dest="gt058_label_gate",
        help=(
            "GT058 (test mode): label-based replay entry gate + student_output overlay from GT055 labels."
        ),
    )
    args = ap.parse_args()

    jid = str(args.job_id).strip()
    if not jid:
        print("ERROR: --job-id required", file=sys.stderr)
        return 4

    if args.promotion_e_min is not None:
        os.environ["PATTERN_GAME_STUDENT_PROMOTION_E_MIN"] = str(float(args.promotion_e_min))

    if args.gt057_tape_repeat is not None:
        os.environ["GT057_REPLAY_TAPE_REPEAT_V1"] = str(max(1, int(args.gt057_tape_repeat)))

    if args.gt058_label_gate:
        os.environ["GT058_LABEL_GATE_ACTIVATION_V1"] = "1"

    if args.enable_labels or args.gt055_report:
        os.environ["GT055_TRIPLE_BARRIER_LABELS_V1"] = "1"
    if args.walk_forward:
        os.environ["GT055_WALK_FORWARD_V1"] = "1"

    root = _bootstrap_env(jid)

    try:
        tf_min = _parse_timeframe_to_minutes(args.timeframe)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4

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

    base_resolved = resolve_scenario_manifest_path(manifest_path)
    if args.symbol or args.timeframe:
        eff = _write_effective_manifest(
            repo=_REPO,
            base_manifest=base_resolved,
            symbol=args.symbol,
            timeframe_label=args.timeframe,
            job_root=root,
        )
        mp_resolved = str(eff.resolve())
    else:
        mp_resolved = str(base_resolved)

    scenario_sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in jid)[:120]
    scenario = {
        "scenario_id": scenario_sid or "gt048_scenario",
        "manifest_path": mp_resolved,
        "rm_preflight_replay_tail_bars_v1": int(args.bars),
        "evaluation_window": {"candle_timeframe_minutes": int(tf_min)},
    }

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
                candle_timeframe_minutes=int(tf_min),
            )
            outcomes = list(prep.get("outcomes") or [])

    n_closed = len(outcomes)
    min_tr = max(1, int(args.min_closed_trades))
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

    gt050 = _gt050_analysis(store_p, jid)
    proof = {
        "directive": "GT048",
        "job_id": jid,
        "memory_root": os.environ.get("PATTERN_GAME_MEMORY_ROOT"),
        "student_learning_store": os.environ.get("PATTERN_GAME_STUDENT_LEARNING_STORE"),
        "session_log_batch_dir_pass1": str(batch_dir.resolve()),
        "closed_trades": n_closed,
        "memory_rows_promoted": promoted,
        "retrieval_matches": int(seam2.get("student_retrieval_matches") or 0),
        "retrieval_matches_later": max(retrieval_later, rx_n),
        "decisions_changed_due_to_memory_or_ev": changed,
        "repeated_losing_patterns": gt050.get("repeated_losing_patterns", 0),
        "memory_blocked_trades": gt050.get("memory_blocked_trades", 0),
        "loss_avoided_count": gt050.get("loss_avoided_count", 0),
        "gt050": gt050,
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

    if args.gt051_report:
        import importlib.util

        mod_path = _REPO / "scripts" / "analyze_gt051_generalization_v1.py"
        spec = importlib.util.spec_from_file_location("analyze_gt051_generalization_v1", mod_path)
        if spec is None or spec.loader is None:
            proof["gt051"] = {"error": "analyze_gt051_generalization_v1_load_failed"}
        else:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            proof["gt051"] = mod.analyze_gt051_generalization_v1(store_path=store_p, job_id=jid)

    if args.gt055_report:
        from renaissance_v4.game_theory.analyze_gt055_walk_forward_v1 import analyze_gt055_walk_forward_v1

        proof["gt055"] = analyze_gt055_walk_forward_v1(
            store_path=store_p,
            job_id=jid,
            closed_trades=int(n_closed),
        )

    # GT056 — opportunity selection (Referee PnL × sealed student_action_v1), pass2 rows only.
    try:
        from renaissance_v4.game_theory.opportunity_selection_metrics_v1 import (
            compute_opportunity_selection_metrics_v1,
        )
        from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
            load_student_learning_records_v1,
        )

        _rows_all = load_student_learning_records_v1(store_p)
        _pass2_id = f"{jid}-pass2"
        _pass2_recs = [r for r in _rows_all if isinstance(r, dict) and str(r.get("run_id") or "") == _pass2_id]
        proof["gt056"] = compute_opportunity_selection_metrics_v1(_pass2_recs)
    except Exception as _gt056_err:
        proof["gt056"] = {"schema": "opportunity_selection_metrics_v1", "error": str(_gt056_err)}

    out_path = Path(os.environ["PATTERN_GAME_MEMORY_ROOT"]) / "gt048_proof.json"
    out_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))

    if not proof["acceptance"]["met"]:
        return 3
    if args.enforce_gt050 and int(gt050.get("loss_avoided_count") or 0) < 1:
        return 5
    if args.enforce_gt051:
        g51 = proof.get("gt051") if isinstance(proof.get("gt051"), dict) else {}
        acc = g51.get("acceptance") if isinstance(g51.get("acceptance"), dict) else {}
        if not acc.get("met"):
            return 6
    return 0


def _DEFAULT_MANIFEST() -> Path:
    return _REPO / "renaissance_v4" / "configs" / "manifests" / "sr1_deterministic_trade_proof_v1.json"


def _sig_hash_v1(rec: dict[str, Any]) -> str | None:
    pps = rec.get("perps_pattern_signature_v1")
    if isinstance(pps, dict):
        h = pps.get("signature_hash_v1")
        return str(h).strip() if h else None
    return None


def _referee_pnl(rec: dict[str, Any]) -> float | None:
    ref = rec.get("referee_outcome_subset")
    if not isinstance(ref, dict):
        return None
    try:
        return float(ref.get("pnl"))
    except (TypeError, ValueError):
        return None


def _student_action_v1(rec: dict[str, Any]) -> str:
    so = rec.get("student_output")
    if not isinstance(so, dict):
        return ""
    return str(so.get("student_action_v1") or "").strip().lower()


def _pattern_memory_eval(rec: dict[str, Any]) -> dict[str, Any]:
    so = rec.get("student_output")
    if not isinstance(so, dict):
        return {}
    ere = so.get("entry_reasoning_eval_v1")
    if not isinstance(ere, dict):
        return {}
    pme = ere.get("pattern_memory_eval_v1")
    return pme if isinstance(pme, dict) else {}


def _indicator_bias_from_ere(ere: dict[str, Any] | None) -> str:
    if not isinstance(ere, dict):
        return ""
    ice = ere.get("indicator_context_eval_v1")
    if not isinstance(ice, dict):
        return ""
    sf = ice.get("support_flags_v1")
    if not isinstance(sf, dict):
        return ""
    if sf.get("long"):
        return "long_bias"
    if sf.get("short"):
        return "short_bias"
    return "neutral"


def _gt050_analysis(store_path: Path, job_id: str) -> dict[str, Any]:
    """GT050 counters + one proof pair from merged pass1/pass2 JSONL (same store file)."""
    records: list[dict[str, Any]] = []
    p = Path(store_path)
    if not p.is_file():
        return {
            "repeated_losing_patterns": 0,
            "memory_blocked_trades": 0,
            "loss_avoided_count": 0,
            "proof_pair": None,
            "note": "store_missing",
        }
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    from collections import defaultdict

    losses_per_sig: defaultdict[str, int] = defaultdict(int)
    for r in records:
        sh = _sig_hash_v1(r)
        if not sh:
            continue
        pnl = _referee_pnl(r)
        if pnl is not None and pnl < 0:
            losses_per_sig[sh] += 1

    repeated_losing_patterns = sum(1 for n in losses_per_sig.values() if n >= 2)

    blocked: list[dict[str, Any]] = []
    pass2 = f"{job_id}-pass2"
    for r in records:
        if str(r.get("run_id") or "") != pass2:
            continue
        pme = _pattern_memory_eval(r)
        stats = pme.get("pattern_outcome_stats_v1") if isinstance(pme.get("pattern_outcome_stats_v1"), dict) else {}
        try:
            avg_pnl = float(stats.get("avg_pnl") or 0.0)
        except (TypeError, ValueError):
            avg_pnl = 0.0
        try:
            wins_frac = float(stats.get("wins_total_fraction_v1") or 1.0)
        except (TypeError, ValueError):
            wins_frac = 1.0
        try:
            cnt_st = int(stats.get("count") or 0)
        except (TypeError, ValueError):
            cnt_st = 0
        losing_history = avg_pnl < 0 or (cnt_st >= 3 and wins_frac < 0.5)
        mc = 0
        try:
            mc = int(pme.get("matched_count_v1") or 0)
        except (TypeError, ValueError):
            mc = 0
        if _student_action_v1(r) == "no_trade" and mc >= 1 and losing_history:
            blocked.append(r)

    memory_blocked_trades = len(blocked)
    loss_avoided_count = memory_blocked_trades

    proof_pair: dict[str, Any] | None = None
    if blocked:
        b = blocked[0]
        sh_b = _sig_hash_v1(b)
        if sh_b:
            a_loss = next(
                (
                    x
                    for x in records
                    if str(x.get("run_id") or "") == job_id
                    and _sig_hash_v1(x) == sh_b
                    and (_referee_pnl(x) or 0.0) < 0
                ),
                None,
            )
            if a_loss is None:
                a_loss = next(
                    (
                        x
                        for x in records
                        if str(x.get("run_id") or "") == job_id
                        and _sig_hash_v1(x) == sh_b
                    ),
                    None,
                )
            refb = b.get("referee_outcome_subset") if isinstance(b.get("referee_outcome_subset"), dict) else {}
            proof_pair = {
                "trade_a_loss": None,
                "trade_b_later": None,
            }
            if a_loss is not None:
                refa = a_loss.get("referee_outcome_subset") if isinstance(a_loss.get("referee_outcome_subset"), dict) else {}
                ere_a = (
                    (a_loss.get("student_output") or {}).get("entry_reasoning_eval_v1")
                    if isinstance(a_loss.get("student_output"), dict)
                    else None
                )
                pre_a = _indicator_bias_from_ere(ere_a) if isinstance(ere_a, dict) else ""
                proof_pair["trade_a_loss"] = {
                    "trade_id": str(a_loss.get("graded_unit_id") or ""),
                    "signature_hash": _sig_hash_v1(a_loss),
                    "action": _student_action_v1(a_loss) or None,
                    "pnl": _referee_pnl(a_loss),
                    "exit_reason": refa.get("exit_reason"),
                    "pre_indicator_bias": pre_a or None,
                }
            ere_b = (
                (b.get("student_output") or {}).get("entry_reasoning_eval_v1")
                if isinstance(b.get("student_output"), dict)
                else None
            )
            pre_b = _indicator_bias_from_ere(ere_b) if isinstance(ere_b, dict) else ""
            proof_pair["trade_b_later"] = {
                "trade_id": str(b.get("graded_unit_id") or ""),
                "signature_hash": sh_b,
                "retrieved": True,
                "pre_memory_action": pre_b or None,
                "final_action": _student_action_v1(b) or None,
                "pnl": _referee_pnl(b),
                "loss_avoided": "YES" if loss_avoided_count >= 1 else "NO",
            }

    return {
        "repeated_losing_patterns": repeated_losing_patterns,
        "memory_blocked_trades": memory_blocked_trades,
        "loss_avoided_count": loss_avoided_count,
        "proof_pair": proof_pair,
    }


if __name__ == "__main__":
    raise SystemExit(main())
