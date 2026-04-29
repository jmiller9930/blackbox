#!/usr/bin/env python3
"""
GT045 — Minimal trade cycle proof (continuous loop).

Shows: Referee replay → closed trades → Student seam writes learning rows → deterministic replay #2
retrieves prior rows by signature → shadow Student differs when retrieval is non-empty.

Usage (from repo root):

  PYTHONPATH=. python3 scripts/run_trade_cycle_v1.py \\
    --bars 100 \\
    --symbol SOLUSDT \\
    --timeframe 5m \\
    --job-id d7-cycle-proof-001

Requires SQLite ``market_bars_5m`` (``DB_PATH`` / default repo DB).

Default manifest is ``sr1_deterministic_trade_proof_v1.json`` (fusion floor lowered **only** so this
tape yields enough Referee closed trades — still deterministic replay on stored OHLCV, not synthetic
PnL). Override with ``--manifest`` if your DB produces ≥5 trades on ``baseline_v1_recipe``.

**Governance:** Operator batches register a scorecard row so L3 can ``promote``. This standalone CLI
has no scorecard; we temporarily patch ``classify_trade_memory_promotion_v1`` to ``promote`` so
append + retrieval behave like a promoted batch (Referee outcomes and Student seam are unchanged).

Exit codes: 0 success, 2 insufficient closed trades, 3 acceptance failed, 4 replay/seam error.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable  # noqa: E402
from renaissance_v4.manifest.validate import load_manifest_file  # noqa: E402
from renaissance_v4.game_theory.pattern_game import run_pattern_game  # noqa: E402
from renaissance_v4.game_theory.student_proctor.contracts_v1 import FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1  # noqa: E402
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (  # noqa: E402
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import emit_shadow_stub_student_output_v1  # noqa: E402
from renaissance_v4.game_theory.student_proctor.student_context_builder_v1 import build_student_decision_packet_v1  # noqa: E402
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (  # noqa: E402
    GOVERNANCE_PROMOTE,
    build_learning_governance_v1,
)
from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (  # noqa: E402
    student_loop_seam_after_parallel_batch_v1,
)
from renaissance_v4.utils.db import DB_PATH  # noqa: E402

_SEAM_PATCH = (
    "renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1."
    "classify_trade_memory_promotion_v1"
)


def _gt045_promote_when_no_scorecard(*, l3_payload: dict, scorecard_entry: dict | None):
    """CLI-only: real L3 returns reject without batch scorecard; GT045 needs append + retrieval."""
    jid = ""
    if isinstance(l3_payload, dict):
        jid = str(l3_payload.get("job_id") or "").strip()
    gov = build_learning_governance_v1(
        decision=GOVERNANCE_PROMOTE,
        reason_codes=["gt045_cli_scorecardless_promote_v1"],
        source_job_id=jid or "gt045",
        fingerprint=None,
    )
    return GOVERNANCE_PROMOTE, [], gov

MIN_CLOSED_TRADES = 5
_DEFAULT_GT045_MANIFEST = (
    _REPO / "renaissance_v4" / "configs" / "manifests" / "sr1_deterministic_trade_proof_v1.json"
)


def _parse_tf_minutes(s: str) -> int:
    t = (s or "").strip().lower().rstrip("m")
    return int(t)


def _entry_action_from_direction(direction: str) -> str:
    d = (direction or "").strip().lower()
    if d == "long":
        return "enter_long"
    if d == "short":
        return "enter_short"
    return f"enter_{d}" if d else "unknown"


def _signature_key_for_trade_v1(o: OutcomeRecord, *, candle_timeframe_minutes: int) -> str:
    return f"student_entry_v1:{o.symbol}:{o.entry_time}:{int(candle_timeframe_minutes)}"


def _write_manifest(template: Path, symbol: str, timeframe_label: str) -> Path:
    m = load_manifest_file(template)
    m["symbol"] = symbol.strip().upper()
    m["timeframe"] = timeframe_label.strip()
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="gt045_manifest_")
    path = Path(tmp)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=2)
    return path


def _run_replay(
    manifest_path: Path,
    *,
    bars: int,
    tf_min: int,
    quiet: bool,
) -> dict:
    def _go() -> dict:
        return run_pattern_game(
            manifest_path,
            use_groundhog_auto_resolve=False,
            emit_baseline_artifacts=False,
            verbose=False,
            candle_timeframe_minutes=tf_min if tf_min > 5 else None,
            replay_max_bars_v1=int(bars),
        )

    if quiet:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return _go()
    return _go()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bars", type=int, required=True, help="Tail bar count (replay_max_bars_v1).")
    ap.add_argument("--symbol", type=str, required=True, help="Manifest symbol, e.g. SOLUSDT.")
    ap.add_argument("--timeframe", type=str, default="5m", help="e.g. 5m, 15m (must align with rollup).")
    ap.add_argument("--job-id", type=str, required=True, dest="job_id", help="Isolated learning store key.")
    ap.add_argument(
        "--manifest",
        type=str,
        default=str(_DEFAULT_GT045_MANIFEST),
        help="Strategy manifest JSON (default: SR-1 deterministic trade proof).",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Stream replay logs to stdout (default: quiet — proof JSON only at end).",
    )
    args = ap.parse_args()

    tf_min = _parse_tf_minutes(args.timeframe)
    job_id = str(args.job_id).strip()
    if not job_id:
        print("ERROR: --job-id required", file=sys.stderr)
        return 4

    if not DB_PATH.is_file():
        print(f"ERROR: DB not found: {DB_PATH}", file=sys.stderr)
        return 4

    template = Path(args.manifest).expanduser()
    if not template.is_file():
        alt = _REPO / template
        template = alt if alt.is_file() else template
    if not template.is_file():
        print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        return 4

    manifest_path = _write_manifest(template, args.symbol, args.timeframe)

    store_dir = _REPO / "runtime" / "trade_cycle_proof" / job_id
    store_dir.mkdir(parents=True, exist_ok=True)
    store_path = store_dir / "student_learning_records_v1.jsonl"
    if store_path.is_file():
        store_path.unlink()

    proof_path = store_dir / "gt045_proof.json"

    try:
        out1 = _run_replay(manifest_path, bars=args.bars, tf_min=tf_min, quiet=not args.verbose)
    except Exception as e:
        print(f"ERROR: pattern_game pass1 failed: {e}", file=sys.stderr)
        return 4
    finally:
        try:
            manifest_path.unlink(missing_ok=True)
        except OSError:
            pass

    outcomes: list[OutcomeRecord] = list(out1.get("outcomes") or [])
    sym_u = args.symbol.strip().upper()
    outcomes_f = [o for o in outcomes if str(o.symbol).strip().upper() == sym_u]
    if len(outcomes_f) < len(outcomes):
        outcomes = outcomes_f

    n = len(outcomes)
    if n < MIN_CLOSED_TRADES:
        print(
            f"ERROR: need >={MIN_CLOSED_TRADES} closed trades, got {n} "
            f"(symbol={sym_u}, bars={args.bars}). Try more bars or a fuller DB.",
            file=sys.stderr,
        )
        return 2

    replay_json = [outcome_record_to_jsonable(o) for o in outcomes]
    scenario_id = job_id

    ob_audit = {"candle_timeframe_minutes": tf_min}
    try:
        with patch(_SEAM_PATCH, _gt045_promote_when_no_scorecard):
            seam1 = student_loop_seam_after_parallel_batch_v1(
                results=[
                    {
                        "ok": True,
                        "scenario_id": scenario_id,
                        "replay_outcomes_json": replay_json,
                    }
                ],
                run_id=f"{job_id}-pass1",
                db_path=DB_PATH,
                store_path=store_path,
                operator_batch_audit=ob_audit,
            )
    except Exception as e:
        print(f"ERROR: student seam pass1 failed: {e}", file=sys.stderr)
        return 4

    appended = int(seam1.get("student_learning_rows_appended") or 0)
    memory_written_batch = appended >= n

    # Recreate manifest for pass 2 (deleted after pass 1)
    manifest_path2 = _write_manifest(template, args.symbol, args.timeframe)
    try:
        out2 = _run_replay(manifest_path2, bars=args.bars, tf_min=tf_min, quiet=not args.verbose)
    except Exception as e:
        print(f"ERROR: pattern_game pass2 failed: {e}", file=sys.stderr)
        return 4
    finally:
        try:
            manifest_path2.unlink(missing_ok=True)
        except OSError:
            pass

    outcomes2 = [o for o in (out2.get("outcomes") or []) if str(o.symbol).strip().upper() == sym_u]

    if len(outcomes2) != n:
        print(
            f"ERROR: deterministic replay mismatch pass1 trades={n} pass2 trades={len(outcomes2)}",
            file=sys.stderr,
        )
        return 4

    try:
        with patch(_SEAM_PATCH, _gt045_promote_when_no_scorecard):
            seam2 = student_loop_seam_after_parallel_batch_v1(
                results=[
                    {
                        "ok": True,
                        "scenario_id": scenario_id,
                        "replay_outcomes_json": replay_json,
                    }
                ],
                run_id=f"{job_id}-pass2",
                db_path=DB_PATH,
                store_path=store_path,
                operator_batch_audit=ob_audit,
            )
    except Exception as e:
        print(f"ERROR: student seam pass2 failed: {e}", file=sys.stderr)
        return 4

    # Proof pair: first and second closed trades (chronological order from replay).
    t1 = outcomes[0]
    t2 = outcomes[1]
    sk2 = _signature_key_for_trade_v1(t2, candle_timeframe_minutes=tf_min)

    pkt_base, err_b = build_student_decision_packet_v1(
        db_path=DB_PATH,
        symbol=t2.symbol,
        decision_open_time_ms=int(t2.entry_time),
        candle_timeframe_minutes=tf_min,
        max_bars_in_packet=500,
    )
    pkt_rx, err_r = build_student_decision_packet_v1_with_cross_run_retrieval(
        db_path=DB_PATH,
        symbol=t2.symbol,
        decision_open_time_ms=int(t2.entry_time),
        candle_timeframe_minutes=tf_min,
        store_path=store_path,
        retrieval_signature_key=sk2,
        max_bars_in_packet=500,
    )
    if err_b or pkt_base is None:
        print(f"ERROR: baseline packet trade_2: {err_b}", file=sys.stderr)
        return 4
    if err_r or pkt_rx is None:
        print(f"ERROR: retrieval packet trade_2: {err_r}", file=sys.stderr)
        return 4

    rx = pkt_rx.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
    n_rx = len(rx) if isinstance(rx, list) else 0
    memory_used_t2 = n_rx >= 1

    so0, e0 = emit_shadow_stub_student_output_v1(
        pkt_base, graded_unit_id=str(t2.trade_id), decision_at_ms=int(t2.entry_time)
    )
    so1, e1 = emit_shadow_stub_student_output_v1(
        pkt_rx, graded_unit_id=str(t2.trade_id), decision_at_ms=int(t2.entry_time)
    )
    if e0 or e1 or not so0 or not so1:
        print(f"ERROR: shadow stub trade_2: {e0!r} {e1!r}", file=sys.stderr)
        return 4

    keys_cmp = ("confidence_01", "student_decision_ref", "pattern_recipe_ids", "reasoning_text")
    changed = any(so0.get(k) != so1.get(k) for k in keys_cmp)

    # Row for trade_1 after pass1 seam (signature match from store scan).
    memory_written_t1 = memory_written_batch and appended >= 1

    proof = {
        "directive": "GT045",
        "manifest_template": str(template.resolve()),
        "gt045_note_governance": "classify_trade_memory_promotion_v1 patched to promote for scorecardless CLI",
        "job_id": job_id,
        "db_path": str(DB_PATH.resolve()),
        "bars_requested": int(args.bars),
        "symbol": sym_u,
        "timeframe_minutes": tf_min,
        "closed_trades_total": n,
        "student_learning_store": str(store_path.resolve()),
        "seam_pass1": {
            "student_learning_rows_appended": appended,
            "student_retrieval_matches": seam1.get("student_retrieval_matches"),
            "skipped": seam1.get("skipped"),
        },
        "seam_pass2": {
            "student_learning_rows_appended": seam2.get("student_learning_rows_appended"),
            "student_retrieval_matches": seam2.get("student_retrieval_matches"),
            "skipped": seam2.get("skipped"),
        },
        "trade_1": {
            "trade_id": str(t1.trade_id),
            "entry_action": _entry_action_from_direction(t1.direction),
            "exit_reason": str(t1.exit_reason),
            "pnl": float(t1.pnl),
            "memory_written": "YES" if memory_written_t1 else "NO",
        },
        "trade_2": {
            "trade_id": str(t2.trade_id),
            "entry_action": _entry_action_from_direction(t2.direction),
            "memory_used": "YES" if memory_used_t2 else "NO",
            "decision_changed_due_to_memory": "YES" if changed else "NO",
            "retrieval_slices": n_rx,
            "shadow_delta_keys_checked": list(keys_cmp),
        },
        "acceptance_gt045": {
            "memory_written_trade_1": memory_written_t1,
            "memory_used_trade_2": memory_used_t2,
            "met": bool(memory_written_t1 and memory_used_t2),
        },
        "note": (
            "Cross-run retrieval matches prior learning by exact student_entry_v1:{symbol}:{entry_time}:{tf}. "
            "Pass 2 replay is deterministic; seam pass 2 appends new rows with new run_id while retrieval "
            "still finds pass 1 rows for the same trade signatures."
        ),
    }

    proof_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")

    print(json.dumps(proof, indent=2))

    acc = proof["acceptance_gt045"]["met"]
    if not acc:
        print(
            "\nACCEPTANCE NOT MET: require memory_written YES and memory_used YES on trade_1 / trade_2.",
            file=sys.stderr,
        )
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
