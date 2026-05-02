"""
FinQuant Unified Agent Lab — Runner.

Entry point. Orchestrates:
  config → case load → retrieval → lifecycle engine → evaluation → outputs

No app imports. No Flask. No dashboard. No services required.

Usage:
  python finquant/unified/agent_lab/runner.py \\
      --case finquant/unified/agent_lab/cases/lifecycle_basic_v1.json \\
      --config finquant/unified/agent_lab/configs/default_lab_config.json

  python finquant/unified/agent_lab/runner.py --scaffold-check
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

_LAB_ROOT = Path(__file__).parent
_REPO_ROOT = _LAB_ROOT.parents[2]

# Add lab dir to sys.path so sibling modules resolve without install
sys.path.insert(0, str(_LAB_ROOT))


def _scaffold_check() -> None:
    required = [
        _LAB_ROOT / "schemas.py",
        _LAB_ROOT / "config.py",
        _LAB_ROOT / "case_loader.py",
        _LAB_ROOT / "data_contracts.py",
        _LAB_ROOT / "decision_contracts.py",
        _LAB_ROOT / "lifecycle_engine.py",
        _LAB_ROOT / "execution_flow.py",
        _LAB_ROOT / "evaluation.py",
        _LAB_ROOT / "learning_governance.py",
        _LAB_ROOT / "memory_store.py",
        _LAB_ROOT / "retrieval.py",
        _LAB_ROOT / "training_cycle.py",
        _LAB_ROOT / "test_framework.py",
        _LAB_ROOT / "llm_adapter.py",
        _LAB_ROOT / "prompt_builder.py",
        _LAB_ROOT / "market_data_bridge.py",
        _LAB_ROOT / "operator_report.py",
        _LAB_ROOT / "learning" / "__init__.py",
        _LAB_ROOT / "learning" / "pattern_signature.py",
        _LAB_ROOT / "learning" / "learning_unit.py",
        _LAB_ROOT / "learning" / "learning_unit_store.py",
        _LAB_ROOT / "learning" / "falsification_engine.py",
        _LAB_ROOT / "learning" / "promotion_engine.py",
        _LAB_ROOT / "learning" / "pattern_competition.py",
        _LAB_ROOT / "learning" / "decision_explainer.py",
        _LAB_ROOT / "configs" / "default_lab_config.json",
        _LAB_ROOT / "cases" / "lifecycle_basic_v1.json",
        _LAB_ROOT / "cases" / "trend_entry_exit_v1.json",
        _LAB_ROOT / "cases" / "chop_no_trade_v1.json",
        _LAB_ROOT / "cases" / "false_breakout_exit_v1.json",
        _LAB_ROOT / "cases" / "memory_candidate_threshold_v1.json",
        _LAB_ROOT / "test_packs" / "learning_smoke_v1.json",
        _LAB_ROOT / "outputs" / ".gitkeep",
        _LAB_ROOT / "tests" / "test_case_loader.py",
        _LAB_ROOT / "tests" / "test_data_contracts.py",
        _LAB_ROOT / "tests" / "test_memory_store.py",
        _LAB_ROOT / "tests" / "test_retrieval_filter.py",
        _LAB_ROOT / "tests" / "test_lifecycle_engine_smoke.py",
        _LAB_ROOT / "tests" / "test_training_cycle.py",
        _LAB_ROOT / "tests" / "test_test_framework.py",
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


def run(
    case_path: str,
    config_path: str,
    output_dir: str,
    *,
    data_window_months: int | None = None,
    interval: str | None = None,
) -> int:
    from config import load_config
    from execution_flow import execute_case
    from runtime_flags import apply_runtime_overrides_v1

    print(f"[runner] loading config      : {config_path}")
    config = load_config(config_path)
    config = apply_runtime_overrides_v1(
        config,
        data_window_months=data_window_months,
        interval=interval,
    )
    req = config.get("runtime_request_v1") if isinstance(config.get("runtime_request_v1"), dict) else {}
    if req:
        print(
            "[runner] runtime request    : "
            f"months={req.get('data_window_months_v1')} "
            f"interval={req.get('interval_v1')} "
            f"interval_minutes={req.get('interval_minutes_v1')}"
        )

    print(f"[runner] loading case        : {case_path}")
    result = execute_case(
        case_path=case_path,
        config=config,
        output_dir=output_dir,
    )
    case = result["case"]
    print(f"[runner] case loaded         : {case['case_id']} ({case['symbol']})")
    print(f"[runner] retrieval check     : enabled={config.get('retrieval_enabled_default_v1')}")
    print(f"[runner] prior records used  : {len(result['prior_records'])}")
    print(f"[runner] started lifecycle   : {case['case_id']}")
    print(f"[runner] decisions emitted   : {len(result['decisions'])}")
    evaluation = result["evaluation"]
    print(f"[runner] outcome graded      : {evaluation['final_status_v1']}")
    record = result["learning_record"]
    print(f"[runner] learning record     : {record['record_id']}")
    run_id = result["run_id"]
    run_dir = Path(result["run_dir"])
    print(f"[runner] output dir          : {run_dir}")
    print(f"[runner] artifacts written   : {', '.join(evaluation.get('notes', [])[:0] or ['decision_trace.json', 'learning_records.jsonl', 'retrieval_trace.json', 'evaluation.json', 'run_summary.json'])}")

    # Print final decision summary
    print()
    print("─" * 60)
    print(f"  case     : {case['case_id']}")
    print(f"  symbol   : {case['symbol']}")
    print(f"  status   : {evaluation['final_status_v1']}")
    print(f"  actions  : {evaluation['actions_taken']}")
    print(f"  run_id   : {run_id}")
    print("─" * 60)

    status = evaluation["final_status_v1"]
    if status == "FAIL":
        print("\n[runner] FAIL")
        return 1
    print(f"\n[runner] {status}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="runner.py",
        description="FinQuant Unified Agent Lab — isolated lifecycle runner",
    )
    parser.add_argument("--case", type=str, help="Path to a single case JSON file")
    parser.add_argument(
        "--case-pack",
        type=str,
        help="Path to a case pack JSON file (list or wrapper with 'cases' key)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(_LAB_ROOT / "configs" / "default_lab_config.json"),
        help="Path to agent lab config JSON (default: configs/default_lab_config.json)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(_LAB_ROOT / "outputs"),
        help="Base output directory (default: agent_lab/outputs/)",
    )
    parser.add_argument(
        "--data-window-months",
        type=int,
        default=None,
        help="Runtime data window in months (examples: 12, 18, 25). Persisted into run artifacts.",
    )
    parser.add_argument(
        "--interval",
        type=str,
        default=None,
        help="Runtime candle interval selector: 5/5m, 15/15m, 45/45m, 1h/1hour. Persisted into run artifacts.",
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

    if args.case_pack and not args.case:
        # Run each case in the pack
        from case_loader import load_cases
        cases = load_cases(args.case_pack)
        exit_codes = []
        for c in cases:
            import tempfile, json as _json, os
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            _json.dump(c, tmp)
            tmp.close()
            code = run(
                tmp.name,
                args.config,
                args.output_dir,
                data_window_months=args.data_window_months,
                interval=args.interval,
            )
            os.unlink(tmp.name)
            exit_codes.append(code)
        sys.exit(1 if any(c != 0 for c in exit_codes) else 0)

    if not args.case:
        parser.error("--case (or --case-pack or --scaffold-check) is required")

    code = run(
        args.case,
        args.config,
        args.output_dir,
        data_window_months=args.data_window_months,
        interval=args.interval,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
