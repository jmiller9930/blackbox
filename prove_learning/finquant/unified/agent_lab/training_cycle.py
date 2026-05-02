"""
FinQuant Unified Agent Lab — observable training cycle harness.

Cycle:
  1. seed/training run produces governed memory
  2. control run executes without memory
  3. candidate run executes with memory/context
  4. referee report compares control vs candidate
"""

from __future__ import annotations

import argparse
import copy
import datetime
from datetime import timezone
import json
import sys
import uuid
from pathlib import Path
from typing import Any

_LAB_ROOT = Path(__file__).parent
sys.path.insert(0, str(_LAB_ROOT))


def run_training_cycle(
    *,
    seed_case_path: str,
    candidate_case_path: str,
    config_path: str,
    output_dir: str,
    data_window_months: int | None = None,
    interval: str | None = None,
) -> dict[str, Any]:
    from config import load_config
    from execution_flow import execute_case
    from runtime_flags import apply_runtime_overrides_v1
    from learning.learning_unit_store import LearningUnitStore

    cycle_id = (
        f"cycle_{datetime.datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"_{uuid.uuid4().hex[:8]}"
    )
    cycle_dir = Path(output_dir) / cycle_id
    runs_dir = cycle_dir / "runs"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    governed_store = cycle_dir / "shared_learning_records.jsonl"
    learning_units_dir = cycle_dir / "learning_units"
    learning_store = LearningUnitStore(learning_units_dir)

    base_config = load_config(config_path)
    base_config = apply_runtime_overrides_v1(
        base_config,
        data_window_months=data_window_months,
        interval=interval,
    )
    base_config["memory_store_path"] = str(governed_store)

    seed_config = copy.deepcopy(base_config)
    seed_config["retrieval_enabled_default_v1"] = False
    seed_config["auto_promote_learning_v1"] = True

    control_config = copy.deepcopy(base_config)
    control_config["retrieval_enabled_default_v1"] = False
    control_config["auto_promote_learning_v1"] = False

    candidate_config = copy.deepcopy(base_config)
    candidate_config["retrieval_enabled_default_v1"] = True
    candidate_config["auto_promote_learning_v1"] = False

    # Seed: build memory AND build learning units
    seed_result = execute_case(
        case_path=seed_case_path,
        config=seed_config,
        output_dir=str(runs_dir),
        learning_store=learning_store,
    )
    # Control: fresh student, NO learning store query (control of memory)
    control_result = execute_case(
        case_path=candidate_case_path,
        config=control_config,
        output_dir=str(runs_dir),
        learning_store=None,
    )
    # Candidate: same case but learning store is queried + observed
    candidate_result = execute_case(
        case_path=candidate_case_path,
        config=candidate_config,
        output_dir=str(runs_dir),
        learning_store=learning_store,
    )

    report = build_referee_report(
        seed_result=seed_result,
        control_result=control_result,
        candidate_result=candidate_result,
    )

    report_path = cycle_dir / "student_learning_referee_report_v1.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    learning_summary = learning_store.summary_stats()
    manifest = {
        "schema": "finquant_training_cycle_manifest_v1",
        "cycle_id": cycle_id,
        "seed_run_id": seed_result["run_id"],
        "control_run_id": control_result["run_id"],
        "candidate_run_id": candidate_result["run_id"],
        "report_path": str(report_path),
        "shared_learning_store_path": str(governed_store),
        "learning_units_dir_v1": str(learning_units_dir),
        "learning_units_summary_v1": learning_summary,
    }
    with open(cycle_dir / "training_cycle_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return {
        "cycle_id": cycle_id,
        "cycle_dir": str(cycle_dir),
        "seed_result": seed_result,
        "control_result": control_result,
        "candidate_result": candidate_result,
        "report": report,
        "report_path": str(report_path),
        "learning_store_summary_v1": learning_summary,
    }


def build_referee_report(
    *,
    seed_result: dict[str, Any],
    control_result: dict[str, Any],
    candidate_result: dict[str, Any],
) -> dict[str, Any]:
    control_eval = control_result["evaluation"]
    candidate_eval = candidate_result["evaluation"]
    control_decisions = control_result["decisions"]
    candidate_decisions = candidate_result["decisions"]

    control_actions = [d.get("action") for d in control_decisions]
    candidate_actions = [d.get("action") for d in candidate_decisions]
    control_entry = _first_entry_action(control_actions)
    candidate_entry = _first_entry_action(candidate_actions)
    control_conf = _first_confidence(control_decisions)
    candidate_conf = _first_confidence(candidate_decisions)
    retrieval_match_count = len(candidate_result.get("prior_records") or [])
    store_writes_count = 1 if seed_result.get("learning_record") else 0

    action_changed = control_entry != candidate_entry
    confidence_changed = control_conf != candidate_conf
    thesis_changed = _first_thesis(control_decisions) != _first_thesis(candidate_decisions)
    exit_behavior_changed = ("EXIT" in control_actions) != ("EXIT" in candidate_actions)
    retrieval_attributed = retrieval_match_count > 0 and (
        action_changed or confidence_changed or thesis_changed or exit_behavior_changed
    )

    improved = _status_rank(candidate_eval.get("final_status_v1")) > _status_rank(control_eval.get("final_status_v1"))
    abstention_improved = (
        control_eval.get("entry_quality_v1") == "missed_entry"
        and candidate_eval.get("entry_quality_v1") == "entered_as_expected"
    )

    if retrieval_match_count == 0:
        verdict = "MEMORY_AVAILABLE_NO_MATCH"
    elif retrieval_attributed and (improved or abstention_improved):
        verdict = "LEARNED_BEHAVIOR_PROVEN"
    elif action_changed or confidence_changed or thesis_changed or exit_behavior_changed:
        verdict = "BEHAVIOR_CHANGED_NOT_PROVEN_BETTER"
    else:
        verdict = "MEMORY_MATCH_NO_IMPACT"

    checks = [
        _check("seed_run_present", True, seed_result["run_id"]),
        _check("control_run_present", True, control_result["run_id"]),
        _check("candidate_run_present", True, candidate_result["run_id"]),
        _check("same_scenario_family", control_result["case"]["case_id"] == candidate_result["case"]["case_id"], control_result["case"]["case_id"]),
        _check("causal_packet_only", all(d.get("causal_context_only_v1", True) for d in candidate_decisions), None),
        _check("eligible_memory_exists", store_writes_count > 0 and bool(seed_result["learning_record"].get("retrieval_enabled_v1")), store_writes_count),
        _check("retrieval_match_present", retrieval_match_count > 0, retrieval_match_count),
        _check("behavior_delta_present", action_changed or confidence_changed or thesis_changed or exit_behavior_changed, {
            "action_changed": action_changed,
            "confidence_changed": confidence_changed,
            "thesis_changed": thesis_changed,
            "exit_behavior_changed": exit_behavior_changed,
        }),
        _check("retrieval_attribution_supported", retrieval_attributed, retrieval_match_count),
        _check("outcome_or_process_improved", improved or abstention_improved, {
            "control_status": control_eval.get("final_status_v1"),
            "candidate_status": candidate_eval.get("final_status_v1"),
        }),
    ]

    return {
        "schema": "student_learning_referee_report_v1",
        "created_at_utc": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scenario_id": candidate_result["case"]["case_id"],
        "student_id": candidate_result["config"].get("agent_id"),
        "seed_run_id": seed_result["run_id"],
        "control_run_id": control_result["run_id"],
        "candidate_run_id": candidate_result["run_id"],
        "control_profile_v1": "baseline_no_memory_no_context",
        "candidate_profile_v1": "memory_context_reasoning",
        "model_requested_v1": candidate_result["config"].get("llm_model_v1"),
        "model_resolved_v1": candidate_result["config"].get("llm_model_v1"),
        "ollama_base_url_used_v1": candidate_result["config"].get("ollama_base_url_v1"),
        "retrieval_enabled_v1": candidate_result["config"].get("retrieval_enabled_default_v1"),
        "retrieval_match_count_v1": retrieval_match_count,
        "retrieved_record_ids_v1": [str(r.get("record_id")) for r in candidate_result.get("prior_records") or []],
        "store_writes_count_v1": store_writes_count,
        "memory_impact_class_v1": "behavior_changed" if retrieval_attributed else "no_material_impact",
        "behavior_delta_v1": {
            "action_changed_v1": action_changed,
            "control_action_v1": control_entry,
            "candidate_action_v1": candidate_entry,
            "confidence_changed_v1": confidence_changed,
            "control_confidence_v1": control_conf,
            "candidate_confidence_v1": candidate_conf,
            "thesis_changed_v1": thesis_changed,
            "abstention_changed_v1": control_entry == "NO_TRADE" and candidate_entry != "NO_TRADE",
            "exit_behavior_changed_v1": exit_behavior_changed,
            "retrieval_attributed_v1": retrieval_attributed,
        },
        "outcome_delta_v1": {
            "exam_result_changed_v1": control_eval.get("final_status_v1") != candidate_eval.get("final_status_v1"),
            "control_final_status_v1": control_eval.get("final_status_v1"),
            "candidate_final_status_v1": candidate_eval.get("final_status_v1"),
            "economic_score_delta_v1": None,
            "process_score_delta_v1": None,
            "abstention_quality_improved_v1": abstention_improved,
            "notes_v1": "Candidate compared against control after seed memory was written.",
        },
        "proof_checks_v1": checks,
        "verdict_v1": verdict,
        "operator_summary_v1": _operator_summary(verdict, retrieval_match_count, control_entry, candidate_entry),
    }


def _first_entry_action(actions: list[str]) -> str:
    for action in actions:
        if action in {"ENTER_LONG", "ENTER_SHORT"}:
            return action
    return "NO_TRADE"


def _first_confidence(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return "low"
    return str(decisions[0].get("confidence_band_v1") or "low")


def _first_thesis(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return ""
    return str(decisions[0].get("thesis_v1") or "")


def _check(check_id: str, passed: bool, detail: Any) -> dict[str, Any]:
    return {"id": check_id, "pass": passed, "detail": detail}


def _status_rank(status: str | None) -> int:
    if status == "PASS":
        return 2
    if status == "INFO":
        return 1
    return 0


def _operator_summary(verdict: str, retrieval_match_count: int, control_entry: str, candidate_entry: str) -> str:
    return (
        f"Verdict={verdict}. Retrieval matches={retrieval_match_count}. "
        f"Control entry={control_entry}. Candidate entry={candidate_entry}."
    )


def run_progressive_cycle(
    *,
    seed_case_path: str,
    candidate_case_paths: list[str],
    config_path: str,
    output_dir: str,
    data_window_months: int | None = None,
    interval: str | None = None,
    n_passes: int = 3,
) -> dict[str, Any]:
    """
    Progressive multi-run learning cycle.

    Structure:
      1. Seed run   — builds initial governed memory (auto_promote=True)
      2. Control run — first candidate case, no memory (baseline)
      3. Pass 1..N  — same or held-out candidate case(s), each accumulating
                       promoted memory from all prior passes

    Returns a summary dict with all cycle results and a comparison table.

    candidate_case_paths: list of case paths for each pass.
      - If one path is given, it is used for all N passes.
      - If N paths are given, each pass uses a different held-out case.
    """
    from config import load_config
    from execution_flow import execute_case
    from runtime_flags import apply_runtime_overrides_v1
    from learning.learning_unit_store import LearningUnitStore

    cycle_id = (
        f"progressive_{datetime.datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"_{uuid.uuid4().hex[:8]}"
    )
    cycle_dir = Path(output_dir) / cycle_id
    runs_dir = cycle_dir / "runs"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    governed_store = cycle_dir / "shared_learning_records.jsonl"
    learning_units_dir = cycle_dir / "learning_units"
    learning_store = LearningUnitStore(learning_units_dir)

    base_config = load_config(config_path)
    base_config = apply_runtime_overrides_v1(
        base_config,
        data_window_months=data_window_months,
        interval=interval,
    )
    base_config["memory_store_path"] = str(governed_store)

    # -- Seed run --
    seed_config = copy.deepcopy(base_config)
    seed_config["retrieval_enabled_default_v1"] = False
    seed_config["auto_promote_learning_v1"] = True

    seed_result = execute_case(
        case_path=seed_case_path,
        config=seed_config,
        output_dir=str(runs_dir),
        learning_store=learning_store,
    )

    # -- Control run (no memory, no learning store) --
    control_path = candidate_case_paths[0] if candidate_case_paths else seed_case_path
    control_config = copy.deepcopy(base_config)
    control_config["retrieval_enabled_default_v1"] = False
    control_config["auto_promote_learning_v1"] = False

    control_result = execute_case(
        case_path=control_path,
        config=control_config,
        output_dir=str(runs_dir),
        learning_store=None,
    )

    # -- Progressive passes (each accumulates learning) --
    pass_results: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    learning_snapshots: list[dict[str, Any]] = []

    for pass_idx in range(n_passes):
        pass_case_path = (
            candidate_case_paths[pass_idx]
            if pass_idx < len(candidate_case_paths)
            else candidate_case_paths[-1]
        )
        pass_config = copy.deepcopy(base_config)
        pass_config["retrieval_enabled_default_v1"] = True
        pass_config["auto_promote_learning_v1"] = True

        pass_result = execute_case(
            case_path=pass_case_path,
            config=pass_config,
            output_dir=str(runs_dir),
            learning_store=learning_store,
        )
        pass_results.append(pass_result)

        learning_snapshots.append({
            "pass_index_v1": pass_idx + 1,
            "summary_v1": learning_store.summary_stats(),
        })

        report = build_referee_report(
            seed_result=seed_result,
            control_result=control_result,
            candidate_result=pass_result,
        )
        report["pass_index_v1"] = pass_idx + 1
        report["retrieval_match_count_at_pass_v1"] = report["retrieval_match_count_v1"]
        report["learning_units_summary_v1"] = learning_store.summary_stats()
        reports.append(report)

    # -- Write all pass reports --
    report_paths: list[str] = []
    for i, report in enumerate(reports):
        rpath = cycle_dir / f"referee_report_pass_{i + 1}.json"
        with open(rpath, "w") as f:
            json.dump(report, f, indent=2)
        report_paths.append(str(rpath))

    # -- Comparison table --
    comparison = _build_comparison_table(
        control_result=control_result,
        pass_results=pass_results,
        reports=reports,
    )

    manifest = {
        "schema": "finquant_progressive_cycle_manifest_v1",
        "cycle_id": cycle_id,
        "n_passes": n_passes,
        "seed_run_id": seed_result["run_id"],
        "control_run_id": control_result["run_id"],
        "pass_run_ids": [r["run_id"] for r in pass_results],
        "report_paths": report_paths,
        "shared_learning_store_path": str(governed_store),
        "learning_units_dir_v1": str(learning_units_dir),
        "learning_snapshots_v1": learning_snapshots,
        "final_learning_summary_v1": learning_store.summary_stats(),
        "comparison_table_v1": comparison,
    }
    with open(cycle_dir / "progressive_cycle_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return {
        "cycle_id": cycle_id,
        "cycle_dir": str(cycle_dir),
        "seed_result": seed_result,
        "control_result": control_result,
        "pass_results": pass_results,
        "reports": reports,
        "report_paths": report_paths,
        "comparison": comparison,
        "learning_snapshots": learning_snapshots,
        "manifest_path": str(cycle_dir / "progressive_cycle_manifest.json"),
    }


def _build_comparison_table(
    *,
    control_result: dict[str, Any],
    pass_results: list[dict[str, Any]],
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a row-per-run comparison table for operator inspection."""
    rows: list[dict[str, Any]] = []

    # Control row
    rows.append({
        "run": "control",
        "memory_enabled": False,
        "final_status": control_result["evaluation"].get("final_status_v1"),
        "actions": control_result["evaluation"].get("actions_taken", []),
        "entry_action": _first_entry(control_result["evaluation"].get("actions_taken", [])),
        "retrieval_matches": 0,
        "verdict": "N/A (baseline)",
    })

    # Pass rows
    for i, (pass_result, report) in enumerate(zip(pass_results, reports)):
        rows.append({
            "run": f"pass_{i + 1}",
            "memory_enabled": True,
            "final_status": pass_result["evaluation"].get("final_status_v1"),
            "actions": pass_result["evaluation"].get("actions_taken", []),
            "entry_action": _first_entry(pass_result["evaluation"].get("actions_taken", [])),
            "retrieval_matches": report.get("retrieval_match_count_v1", 0),
            "verdict": report.get("verdict_v1", "UNKNOWN"),
        })

    return rows


def _first_entry(actions: list[str]) -> str:
    for a in actions:
        if a in {"ENTER_LONG", "ENTER_SHORT"}:
            return a
    return "NO_TRADE"


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant isolated training cycle")
    parser.add_argument("--seed-case", required=True, type=str)
    parser.add_argument("--candidate-case", required=True, type=str)
    parser.add_argument("--config", required=False, type=str, default=str(_LAB_ROOT / "configs" / "default_lab_config.json"))
    parser.add_argument("--output-dir", required=False, type=str, default=str(_LAB_ROOT / "outputs"))
    parser.add_argument("--data-window-months", type=int, default=None)
    parser.add_argument("--interval", type=str, default=None)
    args = parser.parse_args()

    result = run_training_cycle(
        seed_case_path=args.seed_case,
        candidate_case_path=args.candidate_case,
        config_path=args.config,
        output_dir=args.output_dir,
        data_window_months=args.data_window_months,
        interval=args.interval,
    )
    print(json.dumps({
        "cycle_id": result["cycle_id"],
        "report_path": result["report_path"],
        "verdict_v1": result["report"]["verdict_v1"],
    }, indent=2))


if __name__ == "__main__":
    main()
