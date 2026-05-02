"""
FinQuant Unified Agent Lab — Multi-Cycle Training Loop

Iterative training that proves learning over N cycles:

  Cycle 1 : First pass over the training dataset.
             Patterns created as candidates.
  Cycle 2 : Same dataset replayed.
             Cycle-1 PROMOTE records now retrievable.
             Some patterns reach provisional (5+ observations).
  Cycle K : Patterns that accumulate wins promote toward validated/active.
             Decision quality measurably improves cycle-over-cycle.

Stopping criterion:
  - At least one pattern promoted past 'candidate' (provisional+), AND
  - At least one case in cycle K made a different action than cycle 1.
  If neither is true after max_cycles, exits non-zero.

Usage (server):
  cd /home/vanayr/blackbox
  python3 finquant/unified/agent_lab/training_loop.py \\
      --cases-dir finquant/unified/agent_lab/cases/ab_memory_replay_pack \\
      --config finquant/unified/agent_lab/configs/stub_lab_config.json \\
      --output-dir finquant/unified/agent_lab/outputs \\
      --cycles 5

  python3 finquant/unified/agent_lab/training_loop.py \\
      --generate-synthetic --case-count 50 --cycles 4 \\
      --config finquant/unified/agent_lab/configs/stub_lab_config.json \\
      --output-dir finquant/unified/agent_lab/outputs
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


def _ts() -> str:
    return datetime.datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tag() -> str:
    return f"train_{datetime.datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def _sep(label: str = "") -> None:
    if label:
        print(f"\n{'═'*60}\n  {label}\n{'═'*60}")
    else:
        print("─" * 60)


def run_cycle(
    *,
    cycle_idx: int,
    case_paths: list[str],
    config: dict[str, Any],
    runs_dir: Path,
    learning_store,
) -> list[dict[str, Any]]:
    from execution_flow import execute_case

    results: list[dict[str, Any]] = []
    print(f"[cycle {cycle_idx}] running {len(case_paths)} cases …")
    for i, cp in enumerate(case_paths):
        if i % 10 == 0 and i > 0:
            print(f"[cycle {cycle_idx}]   {i}/{len(case_paths)}")
        r = execute_case(
            case_path=cp,
            config=config,
            output_dir=str(runs_dir / f"cycle_{cycle_idx:03d}"),
            learning_store=learning_store,
        )
        results.append(r)
    return results


def _snapshot(learning_store) -> dict[str, Any]:
    stats = learning_store.summary_stats()
    by_status: dict[str, int] = stats.get("by_status_v1") or {}
    promoted = sum(
        by_status.get(s, 0)
        for s in ("provisional", "validated", "active")
    )
    return {
        "total_units_v1": stats.get("total_units_v1", 0),
        "by_status_v1": by_status,
        "promoted_past_candidate_v1": promoted,
    }


def _cycle_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = wins = losses = no_trade_correct = no_trade_missed = 0
    total_pnl = 0.0
    pass_count = fail_count = 0
    action_map: dict[str, str] = {}

    for r in results:
        case_id = (r.get("case") or {}).get("case_id", "")
        for d in r.get("decisions") or []:
            decisions += 1
            action_map[case_id] = str(d.get("action") or "NO_TRADE")
        for obs in r.get("learning_observations_v1") or []:
            kind = obs.get("outcome_kind_v1")
            pnl = float(obs.get("pnl_v1") or 0.0)
            if kind == "win":
                wins += 1
                total_pnl += pnl
            elif kind == "loss":
                losses += 1
                total_pnl += pnl
            elif kind == "no_trade_correct":
                no_trade_correct += 1
            elif kind == "no_trade_missed":
                no_trade_missed += 1
        ev = r.get("evaluation") or {}
        if ev.get("final_status_v1") == "PASS":
            pass_count += 1
        elif ev.get("final_status_v1") == "FAIL":
            fail_count += 1

    decided = wins + losses
    return {
        "cases_v1": len(results),
        "decisions_v1": decisions,
        "wins_v1": wins,
        "losses_v1": losses,
        "no_trade_correct_v1": no_trade_correct,
        "no_trade_missed_v1": no_trade_missed,
        "total_pnl_v1": round(total_pnl, 6),
        "win_rate_v1": round(wins / decided, 4) if decided else 0.0,
        "evaluation_pass_v1": pass_count,
        "evaluation_fail_v1": fail_count,
        "action_map_v1": action_map,
    }


def _decision_diff(
    prev_actions: dict[str, str],
    curr_actions: dict[str, str],
) -> dict[str, Any]:
    overlap = sorted(set(prev_actions) & set(curr_actions))
    changed = [(cid, prev_actions[cid], curr_actions[cid])
               for cid in overlap if prev_actions[cid] != curr_actions[cid]]
    return {
        "overlap_cases_v1": len(overlap),
        "decisions_changed_v1": len(changed),
        "changes_v1": [{"case_id": c, "prev": p, "curr": n} for c, p, n in changed[:10]],
    }


def run_training_loop(
    *,
    case_paths: list[str],
    config_path: str,
    output_dir: str,
    max_cycles: int = 5,
) -> dict[str, Any]:
    from config import load_config
    from learning.learning_unit_store import LearningUnitStore

    loop_tag = _tag()
    loop_dir = Path(output_dir) / loop_tag
    runs_dir = loop_dir / "runs"
    loop_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    shared_jsonl = loop_dir / "shared_learning_records_training.jsonl"
    units_dir = loop_dir / "learning_units"
    learning_store = LearningUnitStore(units_dir)

    base_config = load_config(config_path)
    base_config["memory_store_path"] = str(shared_jsonl)
    base_config["auto_promote_learning_v1"] = True
    base_config["write_outputs_v1"] = True

    print(f"[train] loop_tag  : {loop_tag}")
    print(f"[train] cases     : {len(case_paths)}")
    print(f"[train] max_cycles: {max_cycles}")
    print(f"[train] loop_dir  : {loop_dir}")

    cycle_reports: list[dict[str, Any]] = []
    prev_actions: dict[str, str] = {}

    for cycle_idx in range(1, max_cycles + 1):
        _sep(f"Cycle {cycle_idx} / {max_cycles}")

        # Cycle 1: no retrieval (baseline). Cycle 2+: retrieval enabled.
        cfg = copy.deepcopy(base_config)
        cfg["retrieval_enabled_default_v1"] = cycle_idx > 1
        if cycle_idx > 1:
            cfg["retrieval_max_records_v1"] = 25

        results = run_cycle(
            cycle_idx=cycle_idx,
            case_paths=case_paths,
            config=cfg,
            runs_dir=runs_dir,
            learning_store=learning_store,
        )

        snap = _snapshot(learning_store)
        metrics = _cycle_metrics(results)
        curr_actions = metrics.pop("action_map_v1")
        diff = _decision_diff(prev_actions, curr_actions)

        report = {
            "cycle_v1": cycle_idx,
            "created_at_v1": _ts(),
            "metrics_v1": metrics,
            "learning_snapshot_v1": snap,
            "decision_diff_vs_prev_v1": diff if cycle_idx > 1 else None,
        }
        cycle_reports.append(report)

        print(
            f"[cycle {cycle_idx}] "
            f"wins={metrics['wins_v1']} losses={metrics['losses_v1']} "
            f"no_trade_correct={metrics['no_trade_correct_v1']} "
            f"pnl={metrics['total_pnl_v1']:.2f} "
            f"win_rate={metrics['win_rate_v1']:.2%}"
        )
        print(
            f"[cycle {cycle_idx}] patterns: "
            f"total={snap['total_units_v1']} "
            f"candidate={snap['by_status_v1'].get('candidate',0)} "
            f"provisional={snap['by_status_v1'].get('provisional',0)} "
            f"validated={snap['by_status_v1'].get('validated',0)} "
            f"active={snap['by_status_v1'].get('active',0)} "
            f"retired={snap['by_status_v1'].get('retired',0)}"
        )
        if cycle_idx > 1:
            print(
                f"[cycle {cycle_idx}] vs cycle {cycle_idx-1}: "
                f"overlap={diff['overlap_cases_v1']} changed={diff['decisions_changed_v1']}"
            )

        prev_actions = curr_actions

    # ──────────────────────────────────────────────────
    # Verdict
    # ──────────────────────────────────────────────────
    _sep("Training Loop Verdict")
    final_snap = cycle_reports[-1]["learning_snapshot_v1"]
    promoted = final_snap["promoted_past_candidate_v1"]

    any_behavioral_change = any(
        (rep.get("decision_diff_vs_prev_v1") or {}).get("decisions_changed_v1", 0) > 0
        for rep in cycle_reports[1:]
    )
    max_wins = max(rep["metrics_v1"]["wins_v1"] for rep in cycle_reports)

    successes: list[str] = []
    failures: list[str] = []

    if max_wins > 0:
        successes.append(f"PASS: agent accumulated {max_wins} wins across cycles")
    else:
        failures.append("FAIL: zero wins recorded across all cycles — patterns cannot promote via win_rate")

    if promoted > 0:
        successes.append(
            f"PASS: {promoted} pattern(s) promoted past candidate "
            f"(by_status={final_snap['by_status_v1']})"
        )
    else:
        failures.append(
            "FAIL: no patterns promoted past 'candidate' after all cycles — "
            "insufficient evidence or mismatched case/eval setup"
        )

    if any_behavioral_change:
        successes.append("PASS: at least one case produced a different action between cycles (learning influenced decisions)")
    else:
        failures.append("FAIL: no behavioral change detected across cycles — retrieval not influencing decisions")

    overall = "PASS" if not any(f.startswith("FAIL:") for f in failures) else "FAIL"

    for line in successes + failures:
        print(" ", line)

    verdict = {
        "overall_v1": overall,
        "successes_v1": successes,
        "issues_v1": failures,
        "max_wins_v1": max_wins,
        "promoted_past_candidate_v1": promoted,
        "any_behavioral_change_v1": any_behavioral_change,
        "final_unit_status_v1": final_snap["by_status_v1"],
    }

    loop_report = {
        "schema": "finquant_training_loop_report_v1",
        "loop_tag_v1": loop_tag,
        "created_at_v1": _ts(),
        "case_count_v1": len(case_paths),
        "max_cycles_v1": max_cycles,
        "cycles_run_v1": len(cycle_reports),
        "cycle_reports_v1": cycle_reports,
        "verdict_v1": verdict,
        "shared_jsonl_v1": str(shared_jsonl),
        "units_dir_v1": str(units_dir),
        "loop_dir_v1": str(loop_dir),
    }

    report_path = loop_dir / "training_loop_report.json"
    with open(report_path, "w") as f:
        json.dump(loop_report, f, indent=2)

    print(f"\n[train] report: {report_path}")
    print(f"[train] overall: {overall}")
    return loop_report


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant multi-cycle training loop")
    parser.add_argument("--cases-dir", help="Directory of case JSON files")
    parser.add_argument("--config", required=True, help="Lab config JSON path")
    parser.add_argument("--output-dir", required=True, help="Output base directory")
    parser.add_argument("--cycles", type=int, default=5, help="Number of training cycles")
    parser.add_argument("--max-cases", type=int, default=None,
                        help="Limit case count (useful for fast LLM iteration)")
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Generate a synthetic dataset before training",
    )
    parser.add_argument("--case-count", type=int, default=50, help="Cases when generating synthetic")
    parser.add_argument("--seed", type=int, default=1729, help="RNG seed for synthetic generation")
    parser.add_argument("--symbol", default="SOL-PERP", help="Symbol for synthetic generation")
    args = parser.parse_args()

    if args.generate_synthetic:
        from synthetic_dataset import generate_dataset

        syn_dir = Path(args.output_dir) / f"synthetic_{uuid.uuid4().hex[:6]}"
        print(f"[train] generating {args.case_count} synthetic cases → {syn_dir}")
        mfst = generate_dataset(
            out_dir=syn_dir,
            case_count=args.case_count,
            seed=args.seed,
            symbol=args.symbol,
        )
        case_paths = mfst["case_paths_v1"]
    else:
        if not args.cases_dir:
            parser.error("--cases-dir is required when not using --generate-synthetic")
        base = Path(args.cases_dir)
        case_paths = sorted(str(p) for p in base.glob("*.json") if "manifest" not in p.name.lower())
        if not case_paths:
            print(f"[train] ERROR: no cases found under {args.cases_dir}", file=sys.stderr)
            sys.exit(1)

    if args.max_cases and len(case_paths) > args.max_cases:
        print(f"[train] limiting to {args.max_cases} cases (--max-cases)")
        case_paths = case_paths[:args.max_cases]

    report = run_training_loop(
        case_paths=case_paths,
        config_path=args.config,
        output_dir=args.output_dir,
        max_cycles=args.cycles,
    )

    verdict = report["verdict_v1"]
    if verdict["overall_v1"] != "PASS":
        for line in verdict.get("issues_v1") or []:
            print(" ", line, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
