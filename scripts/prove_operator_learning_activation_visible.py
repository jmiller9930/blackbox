#!/usr/bin/env python3
"""
Proof: operator-visible learning audit and status line for (1) parallel recipe run and
(2) operator test harness (candidate search path).

Run from repo root (requires SQLite market_bars_5m like other replays):

  PYTHONPATH=. python3 scripts/prove_operator_learning_activation_visible.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from renaissance_v4.game_theory.hunter_planner import resolve_repo_root  # noqa: E402
from renaissance_v4.game_theory.learning_run_audit import aggregate_batch_learning_run_audit_v1  # noqa: E402
from renaissance_v4.game_theory.operator_recipes import build_scenarios_for_recipe  # noqa: E402
from renaissance_v4.game_theory.operator_test_harness_v1 import run_operator_test_harness_v1  # noqa: E402
from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel  # noqa: E402
from renaissance_v4.game_theory.policy_framework import attach_policy_framework_audits  # noqa: E402


def main() -> int:
    root = resolve_repo_root(_REPO)
    manifest = root / "renaissance_v4/configs/manifests/baseline_v1_recipe.json"
    if not manifest.is_file():
        print("SKIP: manifest missing", manifest)
        return 0

    print("=== A) Parallel operator-style batch (1 scenario) ===")
    scenarios = build_scenarios_for_recipe("pattern_learning")
    for s in scenarios:
        s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())
    fw_ok, fw_msg = attach_policy_framework_audits(scenarios)
    if not fw_ok:
        print("framework attach failed", fw_msg)
        return 1
    results = run_scenarios_parallel(
        scenarios,
        max_workers=1,
        write_session_logs=False,
        experience_log_path=None,
        run_memory_log_path=None,
    )
    batch = aggregate_batch_learning_run_audit_v1(results)
    r0 = results[0]
    audit = r0.get("learning_run_audit_v1")
    print("per_scenario_learning_run_audit_v1:", json.dumps(audit, indent=2, sort_keys=True))
    print("operator_learning_status_line_v1:", audit.get("operator_learning_status_line_v1"))
    print("aggregate_batch_learning_run_audit_v1:", json.dumps(batch, indent=2, sort_keys=True))

    print("\n=== B) Operator test harness (control + candidate search) ===")
    ho = run_operator_test_harness_v1(manifest, decision_context_recall_drill_matched_max=0)
    h = ho["operator_test_harness_v1"]
    hla = h.get("learning_run_audit_v1")
    print("harness.learning_run_audit_v1:", json.dumps(hla, indent=2, sort_keys=True))
    print("harness.operator_learning_status_line_v1:", h.get("operator_learning_status_line_v1"))

    print("\nPROOF_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
