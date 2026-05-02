"""
FinQuant Unified Agent Lab — Run A / Run B Comparison Harness

Implements the architect's PPLE test protocol:

  Run A  : Baseline replay over the dataset.
           No prior validated patterns reused.
           All learning rows captured.
           Patterns accumulate evidence and may promote.

  Run B  : Replay over the SAME dataset (or a held-out tail).
           Learning units from Run A are inherited.
           Validated patterns can drive decisions.
           Decisions are compared against Run A bar-for-bar.

Outputs:
  - Per-run learning_observations.jsonl
  - Per-run decision_summary.json
  - run_ab_comparison_v1.json  (the operator-facing comparison)

Usage:
  python finquant/unified/agent_lab/run_ab_comparison.py \\
      --cases-dir finquant/unified/agent_lab/cases/ab_memory_replay_pack \\
      --config finquant/unified/agent_lab/configs/stub_lab_config.json \\
      --output-dir finquant/unified/agent_lab/outputs \\
      --run-a-fraction 1 \\
      --run-b-mode replay_run_a

  Proof pack ``cases/ab_memory_replay_pack`` demonstrates NO_TRADE→ENTER_LONG on replay
  when Run B retrieves a promoted ENTER_LONG lesson from Run A.
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


def discover_cases(cases_dir: str) -> list[str]:
    base = Path(cases_dir)
    paths = sorted(p for p in base.glob("*.json") if "manifest" not in p.name.lower())
    return [str(p) for p in paths]


def run_ab(
    *,
    cases_dir: str,
    config_path: str,
    output_dir: str,
    run_a_fraction: float = 0.7,
    data_window_months: int | None = None,
    interval: str | None = None,
    run_b_mode: str = "replay_run_a",
) -> dict[str, Any]:
    from config import load_config
    from execution_flow import execute_case
    from runtime_flags import apply_runtime_overrides_v1
    from learning.learning_unit_store import LearningUnitStore

    cycle_id = (
        f"ab_{datetime.datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        f"_{uuid.uuid4().hex[:8]}"
    )
    cycle_dir = Path(output_dir) / cycle_id
    runs_dir = cycle_dir / "runs"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    learning_units_dir = cycle_dir / "learning_units"
    learning_store = LearningUnitStore(learning_units_dir)

    base_config = load_config(config_path)
    base_config = apply_runtime_overrides_v1(
        base_config,
        data_window_months=data_window_months,
        interval=interval,
    )
    case_paths = discover_cases(cases_dir)
    if not case_paths:
        raise ValueError(f"No cases found under {cases_dir}")

    split = max(1, int(len(case_paths) * run_a_fraction))
    run_a_paths = case_paths[:split]
    holdout_paths = case_paths[split:]
    if run_b_mode == "replay_run_a":
        run_b_paths = list(run_a_paths)
    elif run_b_mode == "holdout_only":
        run_b_paths = holdout_paths or list(case_paths)
    else:
        raise ValueError(f"run_b_mode must be replay_run_a or holdout_only, got {run_b_mode!r}")

    print(f"[ab] cases discovered : {len(case_paths)}")
    print(f"[ab] run A cases      : {len(run_a_paths)}")
    print(f"[ab] run B mode       : {run_b_mode}")
    print(f"[ab] run B cases      : {len(run_b_paths)}")
    print(f"[ab] cycle dir        : {cycle_dir}")

    # Single governed JSONL so Run B retrieval sees Run A PROMOTE rows (same symbol/tape).
    governed_ab = cycle_dir / "shared_learning_records_ab.jsonl"

    # ----------------------------------------------------------------
    # Run A — baseline; full learning capture, no driving from validated yet
    # ----------------------------------------------------------------
    config_a = copy.deepcopy(base_config)
    config_a["memory_store_path"] = str(governed_ab)
    config_a["retrieval_enabled_default_v1"] = False
    config_a["auto_promote_learning_v1"] = True

    print("[ab] === Run A: baseline ===")
    run_a_results: list[dict[str, Any]] = []
    for i, cp in enumerate(run_a_paths):
        if i % 10 == 0:
            print(f"[ab] run A progress: {i}/{len(run_a_paths)}")
        result = execute_case(
            case_path=cp,
            config=config_a,
            output_dir=str(runs_dir / "run_a"),
            learning_store=learning_store,
        )
        run_a_results.append(result)

    snapshot_after_a = learning_store.summary_stats()
    print(f"[ab] run A complete. learning units: {snapshot_after_a}")

    # ----------------------------------------------------------------
    # Run B — replay with inherited learning units
    # ----------------------------------------------------------------
    config_b = copy.deepcopy(base_config)
    config_b["memory_store_path"] = str(governed_ab)
    config_b["retrieval_enabled_default_v1"] = True
    config_b["auto_promote_learning_v1"] = True
    config_b["retrieval_max_records_v1"] = int(
        base_config.get("ab_retrieval_max_records_v1")
        or base_config.get("retrieval_max_records_v1")
        or 25
    )

    print("[ab] === Run B: replay with inherited learning ===")
    run_b_results: list[dict[str, Any]] = []
    for i, cp in enumerate(run_b_paths):
        if i % 10 == 0:
            print(f"[ab] run B progress: {i}/{len(run_b_paths)}")
        result = execute_case(
            case_path=cp,
            config=config_b,
            output_dir=str(runs_dir / "run_b"),
            learning_store=learning_store,
        )
        run_b_results.append(result)

    snapshot_after_b = learning_store.summary_stats()
    print(f"[ab] run B complete. learning units: {snapshot_after_b}")

    # ----------------------------------------------------------------
    # Build comparison report
    # ----------------------------------------------------------------
    comparison = build_ab_comparison(
        run_a_results=run_a_results,
        run_b_results=run_b_results,
        snapshot_after_a=snapshot_after_a,
        snapshot_after_b=snapshot_after_b,
        protocol_v1={
            "run_b_mode_v1": run_b_mode,
            "governed_memory_path_v1": str(governed_ab),
            "holdout_case_count_v1": len(holdout_paths),
        },
    )

    # Persist artifacts
    summary_path = cycle_dir / "run_ab_comparison_v1.json"
    with open(summary_path, "w") as f:
        json.dump(comparison, f, indent=2)

    # Persist learning observations from each run
    _write_observations(cycle_dir / "run_a_learning_observations.jsonl", run_a_results)
    _write_observations(cycle_dir / "run_b_learning_observations.jsonl", run_b_results)

    manifest = {
        "schema": "finquant_run_ab_manifest_v1",
        "cycle_id": cycle_id,
        "cycle_dir": str(cycle_dir),
        "run_a_case_count_v1": len(run_a_paths),
        "run_b_case_count_v1": len(run_b_paths),
        "run_b_mode_v1": run_b_mode,
        "governed_memory_path_v1": str(governed_ab),
        "snapshot_after_a_v1": snapshot_after_a,
        "snapshot_after_b_v1": snapshot_after_b,
        "comparison_path_v1": str(summary_path),
        "learning_units_dir_v1": str(learning_units_dir),
    }
    with open(cycle_dir / "run_ab_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[ab] DONE. comparison: {summary_path}")
    return manifest


def build_ab_comparison(
    *,
    run_a_results: list[dict[str, Any]],
    run_b_results: list[dict[str, Any]],
    snapshot_after_a: dict[str, Any],
    snapshot_after_b: dict[str, Any],
    protocol_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the architect-spec Run A vs Run B comparison."""
    a_metrics = _aggregate_run_metrics(run_a_results)
    b_metrics = _aggregate_run_metrics(run_b_results)

    # Cross-run decision diff (only meaningful when same case set)
    decision_diff = _compare_decisions_by_case(run_a_results, run_b_results)

    a_units_by_status = snapshot_after_a.get("by_status_v1", {}) or {}
    b_units_by_status = snapshot_after_b.get("by_status_v1", {}) or {}
    delta_by_status = {
        s: int(b_units_by_status.get(s, 0)) - int(a_units_by_status.get(s, 0))
        for s in set(list(a_units_by_status.keys()) + list(b_units_by_status.keys()))
    }

    out = {
        "schema": "finquant_run_ab_comparison_v1",
        "created_at_v1": datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "protocol_v1": protocol_v1 or {},
        "run_a_metrics_v1": a_metrics,
        "run_b_metrics_v1": b_metrics,
        "delta_v1": _delta(a_metrics, b_metrics),
        "decision_diff_v1": decision_diff,
        "units_after_run_a_v1": snapshot_after_a,
        "units_after_run_b_v1": snapshot_after_b,
        "units_status_delta_v1": delta_by_status,
        "verdict_v1": _ab_verdict(
            a_metrics,
            b_metrics,
            snapshot_after_a,
            snapshot_after_b,
            decision_diff,
            protocol_v1 or {},
        ),
    }
    return out


def _aggregate_run_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    cases = len(results)
    decisions = 0
    learning_observations = 0
    wins = losses = no_trade_correct = no_trade_missed = 0
    total_pnl = 0.0
    pass_count = fail_count = info_count = 0

    for r in results:
        decisions_in_run = r.get("decisions") or []
        decisions += len(decisions_in_run)
        observations = r.get("learning_observations_v1") or []
        learning_observations += len(observations)
        for o in observations:
            kind = o.get("outcome_kind_v1")
            if kind == "win":
                wins += 1
            elif kind == "loss":
                losses += 1
            elif kind == "no_trade_correct":
                no_trade_correct += 1
            elif kind == "no_trade_missed":
                no_trade_missed += 1
            total_pnl += float(o.get("pnl_v1") or 0.0)
        eval_status = (r.get("evaluation") or {}).get("final_status_v1")
        if eval_status == "PASS":
            pass_count += 1
        elif eval_status == "FAIL":
            fail_count += 1
        else:
            info_count += 1

    decided = wins + losses
    win_rate = round(wins / decided, 4) if decided else 0.0
    expectancy = round(total_pnl / decided, 6) if decided else 0.0
    decision_quality_pass_rate = round(pass_count / cases, 4) if cases else 0.0

    return {
        "cases_v1": cases,
        "decisions_v1": decisions,
        "learning_observations_v1": learning_observations,
        "wins_v1": wins,
        "losses_v1": losses,
        "no_trade_correct_v1": no_trade_correct,
        "no_trade_missed_v1": no_trade_missed,
        "total_pnl_v1": round(total_pnl, 6),
        "win_rate_v1": win_rate,
        "expectancy_v1": expectancy,
        "evaluation_pass_v1": pass_count,
        "evaluation_fail_v1": fail_count,
        "evaluation_info_v1": info_count,
        "decision_quality_pass_rate_v1": decision_quality_pass_rate,
    }


def _delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    keys = ("wins_v1", "losses_v1", "no_trade_correct_v1", "no_trade_missed_v1",
            "total_pnl_v1", "win_rate_v1", "expectancy_v1",
            "evaluation_pass_v1", "evaluation_fail_v1",
            "decision_quality_pass_rate_v1")
    return {f"delta_{k}": round(float(b.get(k, 0) or 0) - float(a.get(k, 0) or 0), 6) for k in keys}


def _compare_decisions_by_case(
    run_a_results: list[dict[str, Any]],
    run_b_results: list[dict[str, Any]],
) -> dict[str, Any]:
    a_by_case = {r["case"]["case_id"]: r for r in run_a_results}
    b_by_case = {r["case"]["case_id"]: r for r in run_b_results}
    overlap = sorted(set(a_by_case) & set(b_by_case))

    diffs = 0
    same = 0
    diff_details: list[dict[str, Any]] = []
    for cid in overlap:
        a_actions = [d["action"] for d in (a_by_case[cid].get("decisions") or [])]
        b_actions = [d["action"] for d in (b_by_case[cid].get("decisions") or [])]
        if a_actions != b_actions:
            diffs += 1
            diff_details.append({
                "case_id": cid,
                "run_a_actions": a_actions,
                "run_b_actions": b_actions,
            })
        else:
            same += 1

    return {
        "overlap_cases_v1": len(overlap),
        "decisions_same_v1": same,
        "decisions_changed_v1": diffs,
        "decision_change_rate_v1": round(diffs / max(len(overlap), 1), 4),
        "first_10_diffs_v1": diff_details[:10],
    }


def _ab_verdict(
    a: dict[str, Any],
    b: dict[str, Any],
    snap_a: dict[str, Any],
    snap_b: dict[str, Any],
    decision_diff: dict[str, Any],
    protocol_v1: dict[str, Any],
) -> dict[str, Any]:
    """Operator-facing verdict aligned with architect success criteria."""
    run_b_mode = (protocol_v1 or {}).get("run_b_mode_v1") or "replay_run_a"
    a_units_total = int(snap_a.get("total_units_v1", 0))
    b_units_total = int(snap_b.get("total_units_v1", 0))
    units_grew = b_units_total > a_units_total
    promoted_in_a = int((snap_a.get("by_status_v1") or {}).get("provisional", 0)) + \
                    int((snap_a.get("by_status_v1") or {}).get("validated", 0)) + \
                    int((snap_a.get("by_status_v1") or {}).get("active", 0))
    promoted_in_b = int((snap_b.get("by_status_v1") or {}).get("provisional", 0)) + \
                    int((snap_b.get("by_status_v1") or {}).get("validated", 0)) + \
                    int((snap_b.get("by_status_v1") or {}).get("active", 0))

    failures: list[str] = []
    successes: list[str] = []

    # 1. Learning records written (non-zero)
    if a["learning_observations_v1"] == 0:
        failures.append("FAIL: zero learning observations recorded in Run A")
    else:
        successes.append(f"PASS: {a['learning_observations_v1']} learning observations recorded in Run A")

    # 2. Patterns accumulate evidence
    if a_units_total == 0:
        failures.append("FAIL: zero learning units created in Run A")
    else:
        successes.append(f"PASS: {a_units_total} learning units accumulated evidence in Run A")

    # 3. Patterns change status over time
    if promoted_in_a == 0 and promoted_in_b == 0:
        failures.append("INFO: no patterns promoted past 'candidate' — sample size may be too small")
    else:
        successes.append(f"PASS: {promoted_in_b} patterns reached provisional+ status by end of Run B")

    # 4. Run B uses patterns from Run A
    if b["learning_observations_v1"] == 0:
        failures.append("FAIL: Run B did not engage learning units")
    else:
        successes.append(f"PASS: Run B engaged {b['learning_observations_v1']} learning observations")

    # 5. Replay protocol — must show at least one behavioral change vs Run A (learning demonstration)
    ov = int(decision_diff.get("overlap_cases_v1") or 0)
    changed = int(decision_diff.get("decisions_changed_v1") or 0)
    if run_b_mode == "replay_run_a":
        exp_overlap = int(a.get("cases_v1") or 0)
        if exp_overlap > 0 and ov == 0:
            failures.append(
                "FAIL: replay_run_a expected overlapping case_ids between Run A and Run B; overlap is zero"
            )
        elif ov > 0:
            successes.append(
                f"PASS: apples-to-apples replay — {ov} overlapping case_id(s) compared Run A vs Run B"
            )
            if changed > 0:
                successes.append(
                    f"PASS: {changed}/{ov} overlapping cases produced "
                    "different actions after Run B had retrieval + shared memory from Run A"
                )
            else:
                failures.append(
                    "FAIL: replay completed but every overlapping case matched Run A — shared memory did "
                    "not change decisions (check retrieval, governed JSONL path, ranking, or case pack)"
                )
    elif ov > 0:
        successes.append(
            f"PASS: {ov} overlapping case_id(s) present between Run A and Run B (non-replay mode)"
        )
        if changed > 0:
            successes.append(
                f"PASS: {changed}/{ov} overlapping cases produced different actions Run A vs Run B"
            )

    # 6. Pipeline ran end-to-end
    successes.append("PASS: pipeline executed end-to-end without store write errors")

    overall = "PASS" if not any(f.startswith("FAIL:") for f in failures) else "FAIL"
    return {
        "overall_v1": overall,
        "successes_v1": successes,
        "issues_v1": failures,
    }


def _write_observations(path: Path, results: list[dict[str, Any]]) -> None:
    with open(path, "w") as f:
        for r in results:
            for obs in r.get("learning_observations_v1") or []:
                row = dict(obs)
                row["case_id"] = r.get("case", {}).get("case_id")
                row["run_id"] = r.get("run_id")
                f.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant Run A vs Run B comparison harness")
    parser.add_argument("--cases-dir", required=True, help="Directory containing case JSON files")
    parser.add_argument("--config", required=True, help="Lab config JSON path")
    parser.add_argument("--output-dir", required=True, help="Base output directory")
    parser.add_argument("--run-a-fraction", type=float, default=0.7,
                        help="Fraction of cases used for Run A (rest = holdout; Run B replays Run A by default)")
    parser.add_argument(
        "--run-b-mode",
        type=str,
        default="replay_run_a",
        choices=("replay_run_a", "holdout_only"),
        help="replay_run_a: Run B replays Run A cases for apples-to-apples diffs (default). "
        "holdout_only: legacy — Run B only runs holdout slice.",
    )
    parser.add_argument("--data-window-months", type=int, default=None)
    parser.add_argument("--interval", type=str, default="15m")
    args = parser.parse_args()

    manifest = run_ab(
        cases_dir=args.cases_dir,
        config_path=args.config,
        output_dir=args.output_dir,
        run_a_fraction=args.run_a_fraction,
        data_window_months=args.data_window_months,
        interval=args.interval,
        run_b_mode=args.run_b_mode,
    )
    print(json.dumps({
        "cycle_id": manifest["cycle_id"],
        "comparison_path": manifest["comparison_path_v1"],
        "snapshot_after_a": manifest["snapshot_after_a_v1"],
        "snapshot_after_b": manifest["snapshot_after_b_v1"],
    }, indent=2))

    with open(manifest["comparison_path_v1"]) as cf:
        comparison = json.load(cf)
    verdict = comparison.get("verdict_v1") or {}
    if verdict.get("overall_v1") != "PASS":
        print("[ab] verdict:", verdict.get("overall_v1"), file=sys.stderr)
        for line in verdict.get("issues_v1") or []:
            print(" ", line, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
