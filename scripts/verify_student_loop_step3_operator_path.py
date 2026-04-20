#!/usr/bin/env python3
"""
E2E roadmap **Step 3** — cross-run proof on the **real** Pattern Game API path (AC-2).

Runs **Run A → Run B → clear Student store → Run C** using the same blocking endpoint as scripted
operators: ``POST /api/run-parallel`` (identical work to ``/api/run-parallel/start`` + poll).

Uses the **pinned SR-1** fixture DB + scenarios. Isolates the Student learning JSONL via
``PATTERN_GAME_STUDENT_LEARNING_STORE`` (does not touch the default operator store).

Validates **SR-2** (A vs B primary seam fields differ), **SR-3** (C matches A after reset), and
**AC-2** (fields present on HTTP JSON — operator-visible).

Usage::

  PYTHONPATH=. python3 scripts/verify_student_loop_step3_operator_path.py

Optional::

  --write-proof PATH   Write gate summary JSON

Exit **0** only if all gates pass.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_fixture_db(repo: Path) -> Path:
    db = repo / "runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3"
    if not db.is_file():
        r = subprocess.run(
            [sys.executable, str(repo / "scripts/build_sr1_deterministic_fixture.py")],
            cwd=str(repo),
            check=False,
        )
        if r.returncode != 0 or not db.is_file():
            print("step3_operator_path: failed to build fixture DB", file=sys.stderr)
            sys.exit(2)
    return db


def _primary_slice(body: dict[str, Any]) -> dict[str, Any]:
    seam = body.get("student_loop_directive_09_v1") or {}
    if not isinstance(seam, dict):
        seam = {}
    pt = seam.get("primary_trade_shadow_student_v1")
    if not isinstance(pt, dict):
        pt = {}
    return {
        "student_output_fingerprint": seam.get("student_output_fingerprint"),
        "pattern_recipe_ids": pt.get("pattern_recipe_ids"),
        "confidence_01": pt.get("confidence_01"),
        "student_decision_ref": pt.get("student_decision_ref"),
    }


def _sr2_diff(a: dict[str, Any], b: dict[str, Any]) -> bool:
    for k in ("student_output_fingerprint", "pattern_recipe_ids", "confidence_01", "student_decision_ref"):
        if a.get(k) != b.get(k):
            return True
    return False


def _sr3_ok(a: dict[str, Any], c: dict[str, Any]) -> bool:
    for k in ("student_output_fingerprint", "pattern_recipe_ids", "confidence_01"):
        if a.get(k) != c.get(k):
            return False
    return True


def main() -> int:
    repo = _repo_root()
    ap = argparse.ArgumentParser(description="Step 3 — operator API path SR-2/SR-3/AC-2")
    ap.add_argument(
        "--scenarios",
        type=Path,
        default=repo / "runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json",
    )
    ap.add_argument("--write-proof", type=Path, default=None)
    args = ap.parse_args()

    db = _ensure_fixture_db(repo)
    proof_dir = repo / "runtime/student_loop_lab_proof_v1/step3_operator_path_proof"
    proof_dir.mkdir(parents=True, exist_ok=True)
    store = proof_dir / "student_learning_store_step3.jsonl"

    os.environ["RENAISSANCE_V4_DB_PATH"] = str(db.resolve())
    os.environ["PATTERN_GAME_STUDENT_LEARNING_STORE"] = str(store.resolve())
    os.environ["PATTERN_GAME_NO_SESSION_LOG"] = "1"
    os.environ.setdefault("PATTERN_GAME_STUDENT_LOOP_SEAM", "1")

    if not args.scenarios.is_file():
        print(f"step3_operator_path: missing scenarios {args.scenarios}", file=sys.stderr)
        return 2

    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))
    if not isinstance(scenarios, list) or not scenarios:
        print("step3_operator_path: invalid scenarios list", file=sys.stderr)
        return 2

    if store.is_file():
        store.unlink()

    sys.path.insert(0, str(repo))
    from renaissance_v4.game_theory.student_proctor.student_learning_operator_v1 import (
        RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM,
    )
    from renaissance_v4.game_theory.web_app import create_app

    app = create_app()
    client = app.test_client()

    payload_base: dict[str, Any] = {
        "operator_recipe_id": "custom",
        "scenarios_json": json.dumps(scenarios, ensure_ascii=False),
        "max_workers": 1,
        "use_operator_uploaded_strategy": False,
    }

    def _post_batch() -> dict[str, Any]:
        rv = client.post(
            "/api/run-parallel",
            data=json.dumps(payload_base),
            content_type="application/json",
        )
        data = rv.get_json(silent=True)
        if rv.status_code != 200 or not isinstance(data, dict):
            print(f"step3_operator_path: HTTP {rv.status_code} {data!r}", file=sys.stderr)
            return {}
        if not data.get("ok"):
            print(f"step3_operator_path: batch failed {json.dumps(data, default=str)[:2000]}", file=sys.stderr)
            return {}
        return data

    run_a = _post_batch()
    run_b = _post_batch()
    clr = client.post(
        "/api/student-proctor/learning-store/clear",
        data=json.dumps({"confirm": RESET_STUDENT_PROCTOR_LEARNING_STORE_CONFIRM}),
        content_type="application/json",
    )
    clr_j = clr.get_json(silent=True)
    if clr.status_code != 200 or not isinstance(clr_j, dict) or not clr_j.get("ok"):
        print(f"step3_operator_path: clear store failed {clr.status_code} {clr_j!r}", file=sys.stderr)
        return 2
    run_c = _post_batch()

    pa = _primary_slice(run_a)
    pb = _primary_slice(run_b)
    pc = _primary_slice(run_c)

    seam_a = run_a.get("student_loop_directive_09_v1") if isinstance(run_a, dict) else {}
    seam_b = run_b.get("student_loop_directive_09_v1") if isinstance(run_b, dict) else {}
    if not isinstance(seam_a, dict):
        seam_a = {}
    if not isinstance(seam_b, dict):
        seam_b = {}

    errs: list[str] = []
    for label, body in ("A", run_a), ("B", run_b), ("C", run_c):
        rows = body.get("results") if isinstance(body.get("results"), list) else []
        n = 0
        for row in rows:
            if row.get("ok") and isinstance(row.get("replay_outcomes_json"), list):
                n = max(n, len(row["replay_outcomes_json"]))
        if n < 1:
            errs.append(f"SR-1: run_{label} replay_outcomes_json length < 1 on API results")

    if int(seam_a.get("student_learning_rows_appended") or 0) < 1:
        errs.append("run_A: expected student_learning_rows_appended >= 1")
    if int(seam_b.get("student_retrieval_matches") or 0) < 1:
        errs.append("run_B: expected student_retrieval_matches >= 1 (cross-run retrieval)")
    if not _sr2_diff(pa, pb):
        errs.append(f"SR-2: A vs B primary fields should differ (A={pa!r} B={pb!r})")
    if not _sr3_ok(pa, pc):
        errs.append(f"SR-3: C should match A on fp/pattern_recipe_ids/confidence (A={pa!r} C={pc!r})")

    ac2 = all(
        k in run_a
        for k in (
            "student_learning_rows_appended",
            "student_retrieval_matches",
            "student_output_fingerprint",
            "shadow_student_enabled",
        )
    )
    if not ac2:
        errs.append("AC-2: missing observability keys on /api/run-parallel response")

    def _replay_max(body: dict[str, Any]) -> int:
        n = 0
        for row in body.get("results") or []:
            if row.get("ok") and isinstance(row.get("replay_outcomes_json"), list):
                n = max(n, len(row["replay_outcomes_json"]))
        return n

    def _top4(body: dict[str, Any]) -> dict[str, Any]:
        return {
            "student_learning_rows_appended": body.get("student_learning_rows_appended"),
            "student_retrieval_matches": body.get("student_retrieval_matches"),
            "student_output_fingerprint": body.get("student_output_fingerprint"),
            "shadow_student_enabled": body.get("shadow_student_enabled"),
        }

    out_proof = {
        "schema": "step3_operator_path_proof_v2",
        "path": "POST /api/run-parallel (blocking) + POST /api/student-proctor/learning-store/clear",
        "renaissance_v4_db_path": str(db),
        "pattern_game_student_learning_store": str(store),
        "narrative": {
            "run_A": "Empty Student store before batch; closed trades from replay; baseline shadow (no priors); retrieval_matches=0.",
            "run_B": "Store contains Run A learning rows; first-trade retrieval informs shadow; differs from Run A (SR-2).",
            "run_C": "Store cleared via Operator API; shadow matches Run A on primary fields (SR-3).",
        },
        "per_run": {
            "run_A": {
                "replay_outcomes_json_max_len": _replay_max(run_a),
                **_top4(run_a),
                "primary_trade_shadow_student_v1": (run_a.get("student_loop_directive_09_v1") or {}).get(
                    "primary_trade_shadow_student_v1"
                ),
            },
            "run_B": {
                "replay_outcomes_json_max_len": _replay_max(run_b),
                **_top4(run_b),
                "primary_trade_shadow_student_v1": (run_b.get("student_loop_directive_09_v1") or {}).get(
                    "primary_trade_shadow_student_v1"
                ),
            },
            "run_C": {
                "replay_outcomes_json_max_len": _replay_max(run_c),
                **_top4(run_c),
                "primary_trade_shadow_student_v1": (run_c.get("student_loop_directive_09_v1") or {}).get(
                    "primary_trade_shadow_student_v1"
                ),
            },
        },
        "primary_fields": {"run_A": pa, "run_B": pb, "run_C": pc},
        "student_retrieval_matches": {
            "run_A": int(seam_a.get("student_retrieval_matches") or 0),
            "run_B": int(seam_b.get("student_retrieval_matches") or 0),
        },
        "gates": {
            "sr2_cross_run_difference": _sr2_diff(pa, pb),
            "sr3_reset_matches_run_a": _sr3_ok(pa, pc),
            "ac2_observability_keys": ac2,
        },
        "ok": not errs,
        "errors": errs,
    }

    if args.write_proof:
        args.write_proof.parent.mkdir(parents=True, exist_ok=True)
        args.write_proof.write_text(json.dumps(out_proof, indent=2), encoding="utf-8")
        print(f"step3_operator_path: wrote proof {args.write_proof}")

    if errs:
        print("step3_operator_path: FAIL", file=sys.stderr)
        for e in errs:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(
        "step3_operator_path: OK — SR-2/SR-3/AC-2 on /api/run-parallel "
        f"(retrieval_matches run_B={seam_b.get('student_retrieval_matches')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
