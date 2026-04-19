#!/usr/bin/env python3
"""
Two-run proof: harness winner → contextual JSONL → next harness reads / matches / bias counters.

Requires SQLite ``market_bars_5m`` (same as pattern game). Uses an isolated temp JSONL path.

  PYTHONPATH=. python3 scripts/prove_context_memory_loop_two_run.py

Run 1 must select a strict winner over control or nothing is written (``selected_candidate_id``).
On short or degenerate tapes that often yields no write — use full history / a tape where
candidate search beats control, or rely on ``tests/test_context_memory_winner_persist.py`` for
deterministic persist proof.

Exit 0 when run2 shows ``memory_records_loaded_count > 0`` after run1 wrote at least one line.
Exit 5 when run1 had no winner (nothing to prove on run 2). Exit 1 when run2 load still empty.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

from renaissance_v4.game_theory.operator_test_harness_v1 import run_operator_test_harness_v1  # noqa: E402
from renaissance_v4.game_theory.pattern_game import prepare_effective_manifest_for_replay  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="ctx_mem_loop_"))
    mem = tmp / "context_signature_memory.jsonl"
    manifest = _REPO / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"
    before = ""
    if mem.is_file():
        before = mem.read_text(encoding="utf-8")

    def run_once(label: str, mode: str) -> dict:
        prep = prepare_effective_manifest_for_replay(
            manifest,
            atr_stop_mult=None,
            atr_target_mult=None,
            memory_bundle_path=None,
            use_groundhog_auto_resolve=False,
        )
        try:
            out = run_operator_test_harness_v1(
                prep.replay_path,
                test_run_id=f"proof_{label}",
                source_preset_or_manifest=str(manifest),
                context_signature_memory_mode=mode,
                context_signature_memory_path=mem,
                decision_context_recall_memory_path=mem,
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
    after_r1 = mem.read_text(encoding="utf-8") if mem.is_file() else ""
    if not sel:
        print(
            "\nNo winner on run 1 — no JSONL write (expected on some tapes). "
            "Exit 5. For CI-grade proof see tests/test_context_memory_winner_persist.py."
        )
        return 5
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
    if matches <= 0:
        print("NOTE: no signature match windows on this tape (still loaded store).")
    if bias <= 0:
        print("NOTE: zero fusion bias applications (matches may be empty or priors did not nudge thresholds).")
    print("OK: two-run contextual memory loop exercised; see panel narratives and JSONL diff above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
