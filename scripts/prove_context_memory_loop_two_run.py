#!/usr/bin/env python3
"""
Two-run proof: harness winner → contextual JSONL → next harness reads / matches / bias counters.

Requires SQLite ``market_bars_5m`` (same as pattern game). Default: isolated temp JSONL.

  PYTHONPATH=. python3 scripts/prove_context_memory_loop_two_run.py
  PYTHONPATH=. python3 scripts/prove_context_memory_loop_two_run.py --canonical-memory --directive-proof
  PYTHONPATH=. python3 scripts/prove_context_memory_loop_two_run.py --canonical-memory --directive-proof --bar-window-calendar-months 12

``--canonical-memory`` truncates ``context_signature_memory.jsonl`` (canonical store) before run 1.
``--directive-proof`` enforces architect acceptance: run1 learning + save + run2 load + match + bias.
``--bar-window-calendar-months N`` optional replay slice (pattern-game UI equivalent); use when full series yields no strict winner.

Run 1 must select a strict winner over control or nothing is written (``selected_candidate_id``).
On short or degenerate tapes that often yields no write — use full history / a tape where
candidate search beats control, or rely on ``tests/test_context_memory_winner_persist.py`` for
deterministic persist proof.

Exit 0 when run2 meets success criteria (see ``--directive-proof``).
Exit 5 when run1 had no winner (nothing to prove on run 2). Exit 1 when run2 load still empty.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

from renaissance_v4.game_theory.context_signature_memory import default_memory_path  # noqa: E402
from renaissance_v4.game_theory.operator_test_harness_v1 import run_operator_test_harness_v1  # noqa: E402
from renaissance_v4.game_theory.pattern_game import prepare_effective_manifest_for_replay  # noqa: E402
from renaissance_v4.utils.db import DB_PATH  # noqa: E402


def _jsonl_line_count(p: Path) -> int:
    if not p.is_file():
        return 0
    text = p.read_text(encoding="utf-8")
    if not text.strip():
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


@contextlib.contextmanager
def _mute_replay_stdout():
    """Per-bar replay prints millions of lines on full tape; discard during harness only."""
    saved = sys.stdout
    dev = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = dev
    try:
        yield
    finally:
        sys.stdout = saved
        dev.close()


def _print_tape_preflight() -> int:
    """Return market_bars_5m row count; print DB path and scale hint."""
    path = DB_PATH.resolve()
    print("=== Proof environment (tape) ===")
    print("sqlite_path:", path)
    if not path.is_file():
        print("ERROR: database file missing — cannot replay.")
        return -1
    conn = sqlite3.connect(str(path))
    try:
        n = int(conn.execute("select count(*) from market_bars_5m").fetchone()[0])
    finally:
        conn.close()
    print("market_bars_5m count:", n)
    print(
        "scale_note: decision windows are driven by replay bar iteration (warmup may skip some); "
        "larger bar counts increase odds a candidate strictly beats control for the harness goal."
    )
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--canonical-memory",
        action="store_true",
        help="Use canonical context_signature_memory.jsonl (truncated empty before run 1).",
    )
    ap.add_argument(
        "--directive-proof",
        action="store_true",
        help="Require run1 learning_engaged + memory_saved + run2 loaded/match/bias all > 0.",
    )
    ap.add_argument(
        "--verbose-replay",
        action="store_true",
        help="Stream per-bar replay logs to stdout (default: muted for full-tape runs).",
    )
    ap.add_argument(
        "--bar-window-calendar-months",
        type=int,
        default=None,
        metavar="N",
        help="Optional replay slice: last N calendar months of bars (None = full series).",
    )
    args = ap.parse_args()

    bars = _print_tape_preflight()
    if bars < 0:
        return 6
    bw = args.bar_window_calendar_months
    if bw is not None and int(bw) > 0:
        print("bar_window_calendar_months (replay slice):", int(bw))

    manifest = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    tmp: Path | None = None
    if args.canonical_memory:
        mem = default_memory_path().resolve()
        mem.parent.mkdir(parents=True, exist_ok=True)
        mem.write_text("", encoding="utf-8")
        before = ""
        print("canonical_memory_path (cleared):", mem)
    else:
        tmp = Path(tempfile.mkdtemp(prefix="ctx_mem_loop_"))
        mem = tmp / "context_signature_memory.jsonl"
        before = mem.read_text(encoding="utf-8") if mem.is_file() else ""

    quiet_harness = not args.verbose_replay

    def run_once(label: str, mode: str) -> dict:
        prep = prepare_effective_manifest_for_replay(
            manifest,
            atr_stop_mult=None,
            atr_target_mult=None,
            memory_bundle_path=None,
            use_groundhog_auto_resolve=False,
        )
        ctx = _mute_replay_stdout() if quiet_harness else contextlib.nullcontext()
        try:
            with ctx:
                out = run_operator_test_harness_v1(
                    prep.replay_path,
                    test_run_id=f"proof_{label}",
                    source_preset_or_manifest=str(manifest),
                    context_signature_memory_mode=mode,
                    context_signature_memory_path=mem,
                    decision_context_recall_memory_path=mem,
                    bar_window_calendar_months=bw if bw is not None and int(bw) > 0 else None,
                )
        finally:
            prep.cleanup()
        return out

    print("=== Run 1 (READ+WRITE) — expect winner persist when learning_engaged ===")
    try:
        r1 = run_once("r1", "read_write")
    except Exception as e:  # noqa: BLE001
        print("Run 1 failed:", e)
        return 2
    h1 = r1.get("operator_test_harness_v1") or {}
    p1 = h1.get("context_memory_operator_panel_v1") or {}
    proof = (r1.get("context_candidate_search_raw") or {}).get("context_candidate_search_proof") or {}
    sel = proof.get("selected_candidate_id")
    print("selected_candidate_id:", sel)
    print("panel:", json.dumps(p1, indent=2, sort_keys=True))
    la1 = h1.get("learning_run_audit_v1") or {}
    cls1 = str(la1.get("run_classification_v1") or "")
    dw1 = int((h1.get("replay_attempt_aggregates_v1") or {}).get("decision_windows_total") or 0)
    print("run_classification_v1:", cls1)
    print("decision_windows_total (run1 control):", dw1)
    after_r1 = mem.read_text(encoding="utf-8") if mem.is_file() else ""
    lines_r1 = _jsonl_line_count(mem)
    if not sel:
        print(
            "\nNo winner on run 1 — no JSONL write (expected on some tapes). "
            "Exit 5. For CI-grade proof see tests/test_context_memory_winner_persist.py."
        )
        return 5
    if args.directive_proof:
        if cls1 != "learning_engaged":
            print("FAIL directive: run1 run_classification_v1 must be learning_engaged, got:", cls1)
            return 7
        if not p1.get("memory_saved_this_run"):
            print("FAIL directive: run1 memory_saved_this_run must be true")
            return 8
        if lines_r1 < 1:
            print("FAIL directive: JSONL must have >=1 line after run1, got", lines_r1)
            return 9
    print("jsonl_line_count_after_run1:", lines_r1)
    print("--- JSONL after run1 (tail) ---")
    print(after_r1[-2000:] if len(after_r1) > 2000 else after_r1)

    print("\n=== Run 2 (READ) — same file; expect load + recall counters ===")
    try:
        r2 = run_once("r2", "read")
    except Exception as e:  # noqa: BLE001
        print("Run 2 failed:", e)
        return 3
    raw2 = r2.get("context_candidate_search_raw") or {}
    cr2 = raw2.get("control_replay") or {}
    ra2 = cr2.get("replay_attempt_aggregates_v1") or {}
    dcr2 = cr2.get("decision_context_recall_stats") or {}
    h2 = r2.get("operator_test_harness_v1") or {}
    p2 = h2.get("context_memory_operator_panel_v1") or {}
    print("replay_attempt_aggregates_v1:", json.dumps(ra2, indent=2, sort_keys=True))
    print("decision_context_recall_stats:", json.dumps(dcr2, indent=2, sort_keys=True))
    print("panel run2:", json.dumps(p2, indent=2, sort_keys=True))

    loaded = int(ra2.get("memory_records_loaded_count") or dcr2.get("memory_records_loaded_count") or 0)
    matches = int(ra2.get("recall_match_windows_total") or 0)
    bias = int(ra2.get("recall_bias_applied_total") or 0)
    print("\n=== Proof checklist ===")
    print("memory_file:", mem.resolve())
    print("memory_records_loaded:", loaded)
    print("recall_match_windows_total:", matches)
    print("recall_bias_applied_total:", bias)
    print("jsonl_grew:", len(after_r1) > len(before))

    ok = loaded > 0
    if not ok:
        print(
            "FAIL: no memory records loaded on run 2 (no lines in JSONL or read path mismatch). "
            "If run 1 had a winner, check ``canonical_memory_path`` in the panel vs run 2."
        )
        return 1
    if args.directive_proof:
        if matches <= 0:
            print("FAIL directive: recall_match_windows_total must be > 0, got", matches)
            return 10
        if bias <= 0:
            print("FAIL directive: recall_bias_applied_total must be > 0, got", bias)
            return 11
    else:
        if matches <= 0:
            print("NOTE: no signature match windows on this tape (still loaded store).")
        if bias <= 0:
            print("NOTE: zero fusion bias applications (matches may be empty or priors did not nudge thresholds).")
    print("OK: two-run contextual memory loop exercised; see panel narratives and JSONL diff above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
