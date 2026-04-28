#!/usr/bin/env python3
"""
Engineering entry point for student_test_mode_v1 — isolated Student memory under
``runtime/student_test/<job_id>/``, read-only market SQLite for anchors, exactly **10** seam trades.

Trade rows are **deterministic DB-anchor shells** (latest 10 ``market_bars_5m`` open times for the scenario
manifest symbol — same family as the Student behavior probe). This guarantees 10 ``replay_outcomes_json``
entries without depending on Referee replay producing closed trades.

Usage::

    python3 scripts/run_student_test_mode_v1.py --recipe-id pattern_learning

Use ``pattern_learning`` (single scenario) unless you know what you are doing; multi-scenario recipes
attach 10 trades only to scenario index 0.

Environment for isolation is applied before importing pattern-game modules (paths resolve under the job dir).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    repo = _repo_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    parser = argparse.ArgumentParser(description="student_test_mode_v1 — isolated 10-trade seam dry run")
    parser.add_argument("--recipe-id", default="pattern_learning", help="Operator recipe id (default: pattern_learning)")
    parser.add_argument("--job-id", default="", help="Optional job id (default: UUID)")
    parser.add_argument("--evaluation-window-mode", default="12", help="12 | 18 | 24 | custom")
    parser.add_argument("--evaluation-window-custom-months", default=None, help="When mode=custom")
    parser.add_argument("--trade-window-mode", default="5m", help="Trade window mode (default 5m)")
    parser.add_argument(
        "--student-profile",
        default="memory_context_llm_student",
        help="student_brain_profile_v1 for exam contract",
    )
    args = parser.parse_args()

    job_id = (args.job_id or "").strip() or str(uuid.uuid4())

    from renaissance_v4.game_theory.student_test_mode_v1 import (
        STUDENT_TEST_INSUFFICIENT_DB_ANCHOR_TIMES_V1,
        apply_student_test_mode_env_v1,
        build_student_test_mode_parallel_results_from_db_anchors_v1,
        student_test_job_runtime_root_v1,
    )

    os.environ.update(apply_student_test_mode_env_v1(job_id))
    # Belt-and-suspenders: no Groundhog bundle merge from canonical state/.
    os.environ.setdefault("PATTERN_GAME_GROUNDHOG_BUNDLE", "0")

    from renaissance_v4.game_theory.candle_timeframe_runtime import (
        annotate_scenarios_with_candle_timeframe,
        resolve_ui_trade_window,
    )
    from renaissance_v4.game_theory.evaluation_window_runtime import (
        annotate_scenarios_with_window_and_recipe,
        resolve_ui_evaluation_window,
    )
    from renaissance_v4.game_theory.exam_run_contract_v1 import parse_exam_run_contract_request_v1
    from renaissance_v4.game_theory.operator_recipes import build_scenarios_for_recipe, recipe_meta_by_id
    from renaissance_v4.game_theory.policy_framework import attach_policy_framework_audits
    from renaissance_v4.game_theory.scenario_contract import validate_scenarios
    from renaissance_v4.game_theory.rm_preflight_wiring_v1 import run_rm_preflight_wiring_v1
    from renaissance_v4.game_theory.student_behavior_probe_v1 import finalize_seam_audit_authority_seal_contract_v1
    from renaissance_v4.game_theory.student_proctor.student_proctor_operator_runtime_v1 import (
        student_loop_seam_after_parallel_batch_v1,
    )
    from renaissance_v4.game_theory.student_test_decision_fingerprint_report_v1 import (
        write_student_test_decision_fingerprint_report_md_v1,
    )

    recipe_id_in = str(args.recipe_id).strip()
    meta = recipe_meta_by_id(recipe_id_in)
    if not meta:
        print(
            f"Unknown recipe_id: {recipe_id_in!r}. "
            f"Use an id from operator recipes (default: pattern_learning).",
            file=sys.stderr,
        )
        return 2

    try:
        resolved = resolve_ui_evaluation_window(
            str(args.evaluation_window_mode),
            args.evaluation_window_custom_months,
        )
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    try:
        tw_resolved = resolve_ui_trade_window(str(args.trade_window_mode))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    scenarios = build_scenarios_for_recipe(recipe_id_in)
    recipe_default_months = int(meta.get("default_evaluation_window_months") or 12)
    recipe_label = str(meta.get("operator_label") or recipe_id_in)

    annotate_scenarios_with_window_and_recipe(
        scenarios,
        recipe_id=recipe_id_in,
        recipe_label=recipe_label,
        recipe_default_calendar_months=recipe_default_months,
        resolved=resolved,
    )
    annotate_scenarios_with_candle_timeframe(scenarios, resolved=tw_resolved)

    for s in scenarios:
        s["skip_groundhog_bundle"] = True

    fw_ok, fw_msgs = attach_policy_framework_audits(scenarios)
    if not fw_ok:
        print(fw_msgs[0] if fw_msgs else "policy framework attach failed", file=sys.stderr)
        return 2

    ok_val, val_msgs = validate_scenarios(scenarios, require_hypothesis=False)
    if not ok_val:
        print(val_msgs[0] if val_msgs else "scenario validation failed", file=sys.stderr)
        return 2

    op_tf = int(tw_resolved["candle_timeframe_minutes"])
    req_body: dict[str, Any] = {
        "student_brain_profile_v1": str(args.student_profile),
        "student_test_mode_v1": True,
        "candle_timeframe_minutes": op_tf,
    }
    ex_req, ex_err = parse_exam_run_contract_request_v1(req_body)
    if ex_err or not ex_req:
        print(ex_err or "exam contract parse failed", file=sys.stderr)
        return 2

    operator_batch_audit: dict[str, Any] = {
        "operator_recipe_id": recipe_id_in,
        "operator_recipe_label": recipe_label,
        "evaluation_window_mode": resolved["evaluation_window_mode"],
        "evaluation_window_effective_calendar_months": int(resolved["effective_calendar_months"]),
        "recipe_default_calendar_months": recipe_default_months,
        "manifest_path_primary": scenarios[0].get("manifest_path") if scenarios else None,
        "policy_framework_path": scenarios[0].get("policy_framework_path") if scenarios else None,
        "policy_framework_audit": scenarios[0].get("policy_framework_audit") if scenarios else None,
        "context_signature_memory_mode": "read_write",
        "trade_window_mode": tw_resolved["trade_window_mode"],
        "candle_timeframe_minutes": op_tf,
        "candle_timeframe_label": tw_resolved.get("candle_timeframe_label"),
        "exam_run_contract_request_v1": ex_req,
    }
    for s in scenarios:
        s["context_signature_memory_mode"] = "read_write"

    pf = run_rm_preflight_wiring_v1(
        scenarios=scenarios,
        job_id=job_id,
        exam_run_contract_request_v1=ex_req,
        operator_batch_audit=operator_batch_audit,
        cancel_check=lambda: False,
        progress_cb=None,
    )
    if not pf.get("ok_v1"):
        print(json.dumps({"rm_preflight_failed": True, "audit": pf}, indent=2))
        return 3

    results, bench_err = build_student_test_mode_parallel_results_from_db_anchors_v1(scenarios=scenarios)
    if bench_err or not results:
        out_path = student_test_job_runtime_root_v1(job_id) / "student_test_failure_v1.json"
        reason = STUDENT_TEST_INSUFFICIENT_DB_ANCHOR_TIMES_V1
        if bench_err and STUDENT_TEST_INSUFFICIENT_DB_ANCHOR_TIMES_V1 not in str(bench_err):
            reason = "student_test_mode_build_failed_v1"
        payload = {
            "schema": "student_test_mode_failure_v1",
            "failure_reason": reason,
            "detail": bench_err or "build_student_test_mode_parallel_results_from_db_anchors_v1 returned empty",
            "hint_v1": (
                "Ingest or restore market_bars_5m so at least 10 rows exist for the manifest symbol, "
                "or run on the lab host with a populated bars DB."
            ),
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 4

    op_rid = str(operator_batch_audit.get("operator_recipe_id") or "").strip() or None
    seam = student_loop_seam_after_parallel_batch_v1(
        results=results,
        run_id=job_id,
        strategy_id=op_rid,
        exam_run_contract_request_v1=ex_req,
        operator_batch_audit=operator_batch_audit,
    )
    seam = finalize_seam_audit_authority_seal_contract_v1(job_id, seam)

    root = student_test_job_runtime_root_v1(job_id)
    acceptance = {
        "schema": "student_test_mode_acceptance_v1",
        "job_id": job_id,
        "student_test_mode_v1": True,
        "replay_trade_count_v1": 10,
        "seam_audit_v1": seam,
        "operator_batch_audit_v1": operator_batch_audit,
        "rm_preflight_audit_v1": pf,
    }
    acc_path = root / "student_test_acceptance_v1.json"
    acc_path.write_text(json.dumps(acceptance, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path = write_student_test_decision_fingerprint_report_md_v1(job_id, seam_audit=seam)
    trace_jsonl = (root / "learning_trace_events_v1.jsonl").resolve()
    print(
        json.dumps(
            {
                "ok": True,
                "job_id": job_id,
                "student_test_runtime_root": str(root),
                "learning_trace_events_v1_jsonl": str(trace_jsonl),
                "acceptance_path": str(acc_path),
                "decision_fingerprint_report_md": str(report_path),
            },
            indent=2,
        )
    )
    if seam.get("fatal_authority_seal_mismatch_v1"):
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
