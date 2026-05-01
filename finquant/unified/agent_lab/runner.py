"""
FinQuant Unified Agent Lab — Runner

Entry point for the isolated agent lab. Orchestrates:
  case loading → lifecycle engine → evaluation → output writes

No app imports. No Flask. No dashboard. No services required.

Usage:
  python finquant/unified/agent_lab/runner.py --scaffold-check
  python finquant/unified/agent_lab/runner.py \\
      --case-pack finquant/unified/agent_lab/cases/lifecycle_basic_v1.json \\
      --config finquant/unified/agent_lab/configs/agent_lab_config_v1.json \\
      --output-dir finquant/unified/agent_lab/outputs
"""

import argparse
import json
import sys
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Scaffold guard — no production app imports allowed here
# ---------------------------------------------------------------------------
_LAB_ROOT = Path(__file__).parent
_REPO_ROOT = _LAB_ROOT.parents[2]


def _scaffold_check() -> None:
    required = [
        _LAB_ROOT / "case_loader.py",
        _LAB_ROOT / "lifecycle_engine.py",
        _LAB_ROOT / "decision_contracts.py",
        _LAB_ROOT / "evaluation.py",
        _LAB_ROOT / "memory_store.py",
        _LAB_ROOT / "retrieval.py",
        _LAB_ROOT / "schemas" / "finquant_lifecycle_case_v1.schema.json",
        _LAB_ROOT / "schemas" / "finquant_decision_v1.schema.json",
        _LAB_ROOT / "schemas" / "finquant_learning_record_v1.schema.json",
        _LAB_ROOT / "cases" / "lifecycle_basic_v1.json",
        _LAB_ROOT / "cases" / "trend_entry_exit_v1.json",
        _LAB_ROOT / "cases" / "chop_no_trade_v1.json",
        _LAB_ROOT / "cases" / "false_breakout_exit_v1.json",
        _LAB_ROOT / "configs" / "agent_lab_config_v1.json",
        _LAB_ROOT / "outputs" / ".gitkeep",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("[SCAFFOLD FAIL] Missing files:")
        for m in missing:
            print(f"  - {m}")
        sys.exit(1)
    print("[SCAFFOLD PASS] All required lab files present.")
    print(f"  lab root : {_LAB_ROOT}")
    print(f"  files    : {len(required)} checked, 0 missing")
    print()
    print("lab scaffold ready")


def _load_json(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def run(case_pack_path: str, config_path: str, output_dir: str) -> None:
    from case_loader import load_cases
    from lifecycle_engine import LifecycleEngine
    from evaluation import evaluate_lifecycle
    from memory_store import MemoryStore
    from retrieval import retrieve_eligible

    print(f"[runner] loading config: {config_path}")
    config = _load_json(config_path)

    print(f"[runner] loading cases: {case_pack_path}")
    cases = load_cases(case_pack_path)
    print(f"[runner] cases loaded: {len(cases)}")

    store = MemoryStore(output_dir=output_dir)
    engine = LifecycleEngine(config=config)

    results = []
    for case in cases:
        case_id = case.get("case_id", "unknown")
        print(f"[runner] started lifecycle case: {case_id}")

        prior_records = retrieve_eligible(store, case)
        decisions = engine.run_case(case, prior_records=prior_records)

        print(f"[runner] decisions emitted: {len(decisions)}")

        result = evaluate_lifecycle(case=case, decisions=decisions)
        print(f"[runner] outcome graded: {result['grade_v1']}")

        record = store.write_learning_record(case=case, result=result)
        print(f"[runner] learning record written: {record['record_id']}")

        results.append({"case_id": case_id, "result": result})

    run_id = store.finalize(results)
    print(f"[runner] output paths written: {output_dir}/{run_id}/")

    passed = all(r["result"].get("pass", False) for r in results)
    summary = "PASS" if passed else "FAIL"
    print(f"\n[runner] final summary: {summary}")
    print(f"  cases_processed          : {len(cases)}")
    print(f"  learning_records_written : {len(results)}")
    sys.exit(0 if passed else 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="runner.py",
        description="FinQuant Unified Agent Lab — isolated lifecycle runner",
    )
    parser.add_argument(
        "--case-pack",
        type=str,
        help="Path to case pack JSON file",
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to agent_lab_config JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(_LAB_ROOT / "outputs"),
        help="Base output directory for run artifacts",
    )
    parser.add_argument(
        "--scaffold-check",
        action="store_true",
        help="Verify all scaffold files exist and exit",
    )
    args = parser.parse_args()

    if args.scaffold_check:
        _scaffold_check()
        return

    if not args.case_pack or not args.config:
        parser.error("--case-pack and --config are required unless --scaffold-check is used")

    # Add lab dir to path so sibling modules resolve without package install
    sys.path.insert(0, str(_LAB_ROOT))
    run(
        case_pack_path=args.case_pack,
        config_path=args.config,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
