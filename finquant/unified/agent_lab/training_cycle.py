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

    cycle_id = (
        f"cycle_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
        f"_{uuid.uuid4().hex[:8]}"
    )
    cycle_dir = Path(output_dir) / cycle_id
    runs_dir = cycle_dir / "runs"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    governed_store = cycle_dir / "shared_learning_records.jsonl"

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

    seed_result = execute_case(
        case_path=seed_case_path,
        config=seed_config,
        output_dir=str(runs_dir),
    )
    control_result = execute_case(
        case_path=candidate_case_path,
        config=control_config,
        output_dir=str(runs_dir),
    )
    candidate_result = execute_case(
        case_path=candidate_case_path,
        config=candidate_config,
        output_dir=str(runs_dir),
    )

    report = build_referee_report(
        seed_result=seed_result,
        control_result=control_result,
        candidate_result=candidate_result,
    )

    report_path = cycle_dir / "student_learning_referee_report_v1.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    manifest = {
        "schema": "finquant_training_cycle_manifest_v1",
        "cycle_id": cycle_id,
        "seed_run_id": seed_result["run_id"],
        "control_run_id": control_result["run_id"],
        "candidate_run_id": candidate_result["run_id"],
        "report_path": str(report_path),
        "shared_learning_store_path": str(governed_store),
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
        "created_at_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
