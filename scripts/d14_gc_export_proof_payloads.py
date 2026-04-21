#!/usr/bin/env python3
"""
D14.GC.2 — Emit proof JSON samples for L1 run row, L2 selected run, L3 decision record (when trades exist).

Fills ``@@FIXTURE_BATCH_ABS@@`` in
``renaissance_v4/game_theory/docs/proof/d14_gc/memory_root/batch_scorecard.jsonl.template``,
writes ``memory_root/batch_scorecard.jsonl``, sets ``PATTERN_GAME_MEMORY_ROOT``, then calls the same
builders as the Flask routes.

Usage (from repo root):

  python3 scripts/d14_gc_export_proof_payloads.py

Optional:

  python3 scripts/d14_gc_export_proof_payloads.py --repo-root . --job-id d14_gc_fixture_job

Requires: ``docs/proof/d14_gc/fixture_batch/batch_parallel_results_v1.json`` (copy of a real batch).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _repo_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", type=Path, default=None, help="Repository root (default: parent of scripts/)")
    p.add_argument(
        "--job-id",
        default="d14_gc_fixture_job",
        help="job_id in the fixture scorecard (default: d14_gc_fixture_job)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for samples (default: docs/proof/d14_gc under repo)",
    )
    args = p.parse_args()
    repo = (args.repo_root or _repo_from_script()).resolve()
    jid = str(args.job_id).strip()
    proof = (
        args.out_dir
        if args.out_dir is not None
        else repo / "renaissance_v4/game_theory/docs/proof/d14_gc"
    ).resolve()
    memory_root = proof / "memory_root"
    template = memory_root / "batch_scorecard.jsonl.template"
    fixture_batch = proof / "fixture_batch"
    if not fixture_batch.is_dir():
        print(f"error: missing fixture_batch at {fixture_batch}", file=sys.stderr)
        sys.exit(1)
    if not template.is_file():
        print(f"error: missing template {template}", file=sys.stderr)
        sys.exit(1)

    batch_abs = str(fixture_batch.resolve())
    raw = template.read_text(encoding="utf-8").strip()
    line = raw.replace("@@FIXTURE_BATCH_ABS@@", batch_abs)
    memory_root.mkdir(parents=True, exist_ok=True)
    scorecard_path = memory_root / "batch_scorecard.jsonl"
    scorecard_path.write_text(line + "\n", encoding="utf-8")

    os.environ["PATTERN_GAME_MEMORY_ROOT"] = str(memory_root)
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    os.environ.setdefault("PYTHONPATH", str(repo))

    # Imports after MEMORY_ROOT — default_batch_scorecard_jsonl() must see fixture root
    from renaissance_v4.game_theory.student_panel_d11 import build_d11_run_rows_v1
    from renaissance_v4.game_theory.student_panel_d13 import build_d13_selected_run_payload_v1
    from renaissance_v4.game_theory.student_panel_d14 import (
        build_student_decision_record_v1,
        enrich_student_panel_run_rows_d14,
    )
    from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent
    from renaissance_v4.game_theory.memory_paths import default_batch_scorecard_jsonl

    sc_path = default_batch_scorecard_jsonl()
    rows = read_batch_scorecard_recent(500, path=sc_path)
    hit = next((x for x in rows if str(x.get("job_id")) == jid), None)
    if not hit:
        print(f"error: job_id {jid!r} not found in {sc_path}", file=sys.stderr)
        sys.exit(1)

    enriched = enrich_student_panel_run_rows_d14(build_d11_run_rows_v1([hit]))
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "sample_get_student_panel_runs_row.json").write_text(
        json.dumps(enriched[0] if enriched else {}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sel = build_d13_selected_run_payload_v1(jid)
    (proof / "sample_get_student_panel_selected_run.json").write_text(
        json.dumps(sel, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    tid = None
    slices = (sel.get("slices") or []) if isinstance(sel, dict) else []
    if slices:
        tid = str((slices[0] or {}).get("trade_id") or "").strip() or None

    dec = None
    if tid:
        dec = build_student_decision_record_v1(jid, tid)

    fixture_note = {
        "proof_fixture": True,
        "fixture_batch_dir": batch_abs,
        "sqlite_sol_usdt_bars": (
            "Developer DB (renaissance_v4.sqlite3) currently ships ~60 SOLUSDT bars; baseline replay "
            "often yields zero closed trades, so replay_outcomes_json may be empty. A full "
            "student_decision_record_v1 sample with real trade_id requires a dataset/manifest run "
            "where the Referee closes ≥1 trade."
        ),
    }
    if dec is not None:
        decision_payload = dec
    else:
        decision_payload = {
            "note": (
                "No trade_id in carousel for this fixture batch — replay_outcomes_json is empty "
                "(see batch_parallel_results_v1.json). Re-run export after a batch with ≥1 closed trade."
            ),
            "job_id": jid,
            **fixture_note,
        }
    (proof / "sample_student_decision_record_v1.json").write_text(
        json.dumps(decision_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    carousel_proof = {
        "job_id": jid,
        "slices_keyed_by_trade_id": [
            {"index": i, "trade_id": str((s or {}).get("trade_id") or "")}
            for i, s in enumerate(slices)
        ],
        "all_slice_ids_are_trade_grain": all(
            str((s or {}).get("trade_id") or "").strip() for s in slices
        )
        if slices
        else True,
    }
    (proof / "sample_carousel_trade_id_keys.json").write_text(
        json.dumps(carousel_proof, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    (proof / "CAPTURE_README.txt").write_text(
        "Generated by scripts/d14_gc_export_proof_payloads.py\n"
        f"PATTERN_GAME_MEMORY_ROOT={memory_root}\n"
        f"job_id={jid}\n"
        f"trade_id_used={tid}\n"
        "API routes:\n"
        "  GET /api/student-panel/runs?limit=50\n"
        f"  GET /api/student-panel/run/{jid}/decisions\n"
        f"  GET /api/student-panel/decision?job_id={jid}&trade_id=<trade_id>\n",
        encoding="utf-8",
    )
    print(f"Wrote samples under {proof}")


if __name__ == "__main__":
    main()
