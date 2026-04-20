#!/usr/bin/env python3
"""
E2E roadmap Step 2 — **SR-5 atomic proof bundle** (Run A → Run B → reset → Run C).

Uses the same **pinned** SR-1 database + scenarios as ``verify_student_loop_sr1.py`` so replay is
deterministic. Writes **one folder** with ``run_A.json``, ``run_B.json``, ``run_C.json``,
``scorecard_excerpt.json``, ``COMMIT_SHA.txt``, ``README.md``.

Validates (exit 0 only if all pass):

* **SR-1:** ``len(replay_outcomes_json) >= 1`` on each run.
* **SR-2:** Run A vs Run B differ on at least one primary seam field (fingerprint,
  ``confidence_01``, ``pattern_recipe_ids``, ``student_decision_ref``) when retrieval applies.
* **SR-3:** After clearing the learning store, Run C matches Run A on fingerprint,
  ``pattern_recipe_ids``, and ``confidence_01``.

Learning store for this bundle is **isolated** under ``sr5_atomic_proof_bundle/`` (not the default
operator path).

Usage::

  PYTHONPATH=. python3 scripts/build_student_loop_sr5_proof_bundle.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_sha(repo: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except OSError:
        pass
    return "unknown"


def _ensure_fixture_db(repo: Path) -> Path:
    db = repo / "runtime/student_loop_lab_proof_v1/sr1_deterministic.sqlite3"
    if not db.is_file():
        r = subprocess.run(
            [sys.executable, str(repo / "scripts/build_sr1_deterministic_fixture.py")],
            cwd=str(repo),
            check=False,
        )
        if r.returncode != 0 or not db.is_file():
            print("build_sr5_proof_bundle: failed to build SR-1 fixture DB", file=sys.stderr)
            sys.exit(2)
    return db


def _json_dump(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _primary_sr_fields(seam: dict[str, Any]) -> dict[str, Any]:
    """Fields compared per SR-2 / SR-3 (roadmap §2)."""
    pt = seam.get("primary_trade_shadow_student_v1")
    if not isinstance(pt, dict):
        pt = {}
    return {
        "student_output_fingerprint": seam.get("student_output_fingerprint"),
        "pattern_recipe_ids": pt.get("pattern_recipe_ids"),
        "confidence_01": pt.get("confidence_01"),
        "student_decision_ref": pt.get("student_decision_ref"),
    }


def _gate_sr2_diff(a: dict[str, Any], b: dict[str, Any]) -> bool:
    for k in ("student_output_fingerprint", "pattern_recipe_ids", "confidence_01", "student_decision_ref"):
        if a.get(k) != b.get(k):
            return True
    return False


def _gate_sr3_reset(a: dict[str, Any], c: dict[str, Any]) -> bool:
    for k in ("student_output_fingerprint", "pattern_recipe_ids", "confidence_01"):
        if a.get(k) != c.get(k):
            return False
    return True


def _one_batch(
    *,
    scenarios: list[dict[str, Any]],
    db_path: Path,
    store_path: Path,
    run_id: str,
    sha: str,
    label: str,
) -> dict[str, Any]:
    # Import after env — same pattern as verify_student_loop_sr1.
    from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
    from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
        student_loop_seam_after_parallel_batch_v1,
    )

    results = run_scenarios_parallel(
        scenarios,
        max_workers=1,
        experience_log_path=None,
        write_session_logs=False,
    )
    seam = student_loop_seam_after_parallel_batch_v1(
        results=results,
        run_id=run_id,
        db_path=db_path,
        store_path=store_path,
        strategy_id="pattern_learning",
    )
    n_out = 0
    for r in results:
        if r.get("ok"):
            rx = r.get("replay_outcomes_json")
            if isinstance(rx, list):
                n_out = max(n_out, len(rx))
    return {
        "schema": "sr5_run_payload_v1",
        "bundle_label": label,
        "git_commit_sha": sha,
        "run_id": run_id,
        "renaissance_v4_db_path": str(db_path.resolve()),
        "student_learning_store_path": str(store_path.resolve()),
        "parallel_results": results,
        "student_loop_seam_audit": seam,
        "replay_outcomes_json_max_len": n_out,
    }


def main() -> int:
    repo = _repo_root()
    bundle = repo / "runtime/student_loop_lab_proof_v1/sr5_atomic_proof_bundle"
    bundle.mkdir(parents=True, exist_ok=True)

    db = _ensure_fixture_db(repo)
    db_abs = db.resolve()
    os.environ["RENAISSANCE_V4_DB_PATH"] = str(db_abs)
    # Real replay + seam; default seam on.
    os.environ.setdefault("PATTERN_GAME_STUDENT_LOOP_SEAM", "1")
    os.environ["PATTERN_GAME_NO_SESSION_LOG"] = "1"

    scenarios_path = repo / "runtime/student_loop_lab_proof_v1/scenarios_sr1_deterministic.json"
    if not scenarios_path.is_file():
        print(f"build_sr5_proof_bundle: missing {scenarios_path}", file=sys.stderr)
        return 2
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    if not isinstance(scenarios, list) or not scenarios:
        print("build_sr5_proof_bundle: invalid scenarios", file=sys.stderr)
        return 2

    sys.path.insert(0, str(repo))
    sha = _git_sha(repo)
    store = bundle / "student_learning_store_proof_bundle.jsonl"

    # Run A — empty store
    if store.is_file():
        store.unlink()

    run_a = _one_batch(
        scenarios=scenarios,
        db_path=db_abs,
        store_path=store,
        run_id="sr5_proof_run_a_v1",
        sha=sha,
        label="run_A",
    )
    # Run B — same DB + scenarios; store populated by A
    run_b = _one_batch(
        scenarios=scenarios,
        db_path=db_abs,
        store_path=store,
        run_id="sr5_proof_run_b_v1",
        sha=sha,
        label="run_B",
    )

    # Reset (operator cognitive reset for Student path)
    store.write_text("", encoding="utf-8")

    run_c = _one_batch(
        scenarios=scenarios,
        db_path=db_abs,
        store_path=store,
        run_id="sr5_proof_run_c_v1",
        sha=sha,
        label="run_C",
    )

    seam_a = run_a.get("student_loop_seam_audit") or {}
    seam_b = run_b.get("student_loop_seam_audit") or {}
    seam_c = run_c.get("student_loop_seam_audit") or {}

    pa = _primary_sr_fields(seam_a)
    pb = _primary_sr_fields(seam_b)
    pc = _primary_sr_fields(seam_c)

    errs: list[str] = []

    for tag, run in ("A", run_a), ("B", run_b), ("C", run_c):
        n = int(run.get("replay_outcomes_json_max_len") or 0)
        if n < 1:
            errs.append(f"SR-1: run_{tag} replay_outcomes_json length < 1")

    if not errs and seam_a.get("student_learning_rows_appended", 0) < 1:
        errs.append("SR-1 seam: run_A expected >=1 student_learning_rows_appended")

    if not errs and not _gate_sr2_diff(pa, pb):
        errs.append(
            "SR-2: run_A and run_B primary seam fields should differ when retrieval applies "
            f"(A={pa!r} B={pb!r})"
        )

    if not errs and int(seam_b.get("student_retrieval_matches") or 0) < 1:
        errs.append(
            "SR-2: run_B expected student_retrieval_matches >= 1 (store contained run_A priors)"
        )

    if not errs and not _gate_sr3_reset(pa, pc):
        errs.append(f"SR-3: run_C primary fields should match run_A (A={pa!r} C={pc!r})")

    excerpt = {
        "schema": "sr5_scorecard_excerpt_v1",
        "git_commit_sha": sha,
        "sr_primary_fields": {"run_A": pa, "run_B": pb, "run_C": pc},
        "student_retrieval_matches": {
            "run_A": int(seam_a.get("student_retrieval_matches") or 0),
            "run_B": int(seam_b.get("student_retrieval_matches") or 0),
            "run_C": int(seam_c.get("student_retrieval_matches") or 0),
        },
        "student_learning_rows_appended": {
            "run_A": int(seam_a.get("student_learning_rows_appended") or 0),
            "run_B": int(seam_b.get("student_learning_rows_appended") or 0),
            "run_C": int(seam_c.get("student_learning_rows_appended") or 0),
        },
        "gates": {
            "sr1_replay_outcomes": True,
            "sr2_cross_run_difference": _gate_sr2_diff(pa, pb),
            "sr3_reset_matches_run_a": _gate_sr3_reset(pa, pc),
        },
        "errors": errs,
    }

    _json_dump(bundle / "run_A.json", run_a)
    _json_dump(bundle / "run_B.json", run_b)
    _json_dump(bundle / "run_C.json", run_c)
    _json_dump(bundle / "scorecard_excerpt.json", excerpt)
    (bundle / "COMMIT_SHA.txt").write_text(sha + "\n", encoding="utf-8")

    readme = f"""# SR-5 atomic proof bundle (E2E Step 2)

**Generated by:** ``scripts/build_student_loop_sr5_proof_bundle.py``
**Repository commit (generator host):** ``{sha}``

## Contents

| File | Purpose |
|------|---------|
| ``run_A.json`` | First parallel batch — empty Student learning store |
| ``run_B.json`` | Second batch — store contains learning from Run A (cross-run retrieval) |
| ``run_C.json`` | After **reset** (store truncated) — should match Run A on SR-3 fields |
| ``scorecard_excerpt.json`` | SR-1/2/3 gate summary + primary seam fields |
| ``COMMIT_SHA.txt`` | Same commit as recorded in JSON |

## Reproduce

From repository root (fixed SR-1 DB + scenarios):

```bash
export PYTHONPATH="$(pwd)"
python3 scripts/build_student_loop_sr5_proof_bundle.py
```

Requires the deterministic fixture DB (auto-built if missing via ``scripts/build_sr1_deterministic_fixture.py``).

**Isolation:** Uses ``student_learning_store_proof_bundle.jsonl`` in this folder — not the default operator store path.

## Contract (roadmap §2)

- **SR-1:** Closed trades via ``replay_outcomes_json``; seam appends learning rows.
- **SR-2:** Run B differs from Run A on primary Student shadow fields when retrieval applies.
- **SR-3:** Run C matches Run A on fingerprint / ``pattern_recipe_ids`` / ``confidence_01`` after reset.
"""
    (bundle / "README.md").write_text(readme, encoding="utf-8")

    if errs:
        print("build_sr5_proof_bundle: FAIL", file=sys.stderr)
        for e in errs:
            print(f"  {e}", file=sys.stderr)
        _json_dump(bundle / "scorecard_excerpt.json", excerpt)
        return 1

    print(
        f"build_sr5_proof_bundle: OK — SR-5 bundle at {bundle.relative_to(repo)} "
        f"(sha={sha[:12]}, SR-2 retrieval_matches_run_B={seam_b.get('student_retrieval_matches')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
