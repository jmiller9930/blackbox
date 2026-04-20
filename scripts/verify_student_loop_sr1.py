#!/usr/bin/env python3
"""
E2E roadmap v2.1 — **SR-1** (strict): deterministic **one-command** proof of ≥1 closed trade.

* **Database:** ``runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3`` (built by ``build_sr1_deterministic_fixture.py`` — fixed algorithm, repeatable bytes).
* **Manifest:** ``renaissance_v4/configs/manifests/sr1_deterministic_trade_proof_v1.json`` (``fusion_min_score=0.10`` — proof-only floor so trend_uptime fusion clears; **not** a production objective).
* **Scenarios:** ``runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json``

Sets ``RENAISSANCE_V4_DB_PATH`` **before** importing replay/parallel so workers see the same DB.

Usage::

  PYTHONPATH=. python3 scripts/verify_student_loop_sr1.py

Optional::

  --write-proof PATH   Write JSON with replay_outcomes_json length and paths used.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_fixture(repo: Path) -> Path:
    db = repo / "runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3"
    if not db.is_file():
        build = repo / "scripts/build_sr1_deterministic_fixture.py"
        r = subprocess.run(
            [sys.executable, str(build)],
            cwd=str(repo),
            check=False,
        )
        if r.returncode != 0 or not db.is_file():
            print("verify_student_loop_sr1: failed to build fixture DB", file=sys.stderr)
            sys.exit(2)
    return db


def main() -> int:
    repo = _repo_root()
    ap = argparse.ArgumentParser(description="SR-1 deterministic closed-trade proof")
    ap.add_argument(
        "--scenarios",
        type=Path,
        default=repo / "runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json",
        help="Scenario list JSON",
    )
    ap.add_argument("--write-proof", type=Path, default=None, help="Write proof JSON here")
    args = ap.parse_args()

    db = _ensure_fixture(repo)
    db_abs = str(db.resolve())
    os.environ["RENAISSANCE_V4_DB_PATH"] = db_abs

    if not args.scenarios.is_file():
        print(f"verify_student_loop_sr1: missing scenarios: {args.scenarios}", file=sys.stderr)
        return 2

    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))
    if not isinstance(scenarios, list) or not scenarios:
        print("verify_student_loop_sr1: scenarios must be a non-empty list", file=sys.stderr)
        return 2

    # Import **after** env so ``renaissance_v4.utils.db`` resolves fixture path.
    sys.path.insert(0, str(repo))
    from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel

    results = run_scenarios_parallel(scenarios, max_workers=1, experience_log_path=None)
    if sum(1 for r in results if r.get("ok")) != len(results):
        print("verify_student_loop_sr1: scenario failure", file=sys.stderr)
        for r in results:
            if not r.get("ok"):
                print(json.dumps(r, default=str, indent=2)[:2500], file=sys.stderr)
        return 2

    row = results[0]
    rx = row.get("replay_outcomes_json")
    n_out = len(rx) if isinstance(rx, list) else -1
    summ = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    btr = int(summ.get("trades") or 0) if isinstance(summ, dict) else 0

    try:
        db_rel = os.path.relpath(db_abs, str(repo))
    except ValueError:
        db_rel = db_abs
    proof = {
        "schema": "sr1_verify_proof_v1",
        "renaissance_v4_db_path": db_rel,
        "manifest_path": scenarios[0].get("manifest_path"),
        "replay_outcomes_json_length": n_out,
        "summary_trades": btr,
        "ok": n_out >= 1 or btr >= 1,
    }

    if args.write_proof:
        args.write_proof.parent.mkdir(parents=True, exist_ok=True)
        args.write_proof.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        print(f"verify_student_loop_sr1: wrote proof {args.write_proof}")

    if n_out >= 1:
        print(
            f"verify_student_loop_sr1: OK — replay_outcomes_json length={n_out} "
            f"(fixture {db.name}, manifest {proof['manifest_path']})"
        )
        return 0

    if btr >= 1 and n_out < 1:
        print(
            "verify_student_loop_sr1: INTERNAL — summary.trades > 0 but replay_outcomes_json empty; "
            "check parallel_runner.",
            file=sys.stderr,
        )
        return 2

    print(
        "verify_student_loop_sr1: FAIL — zero outcomes (fixture/manifest regression).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
