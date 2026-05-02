"""
FinQuant Unified Agent Lab — Operator Report

Reads a test run output and prints a plain-English summary.
No JSON dumps. No jargon. Any operator can read this.

Usage (from repo root):
  python finquant/unified/agent_lab/operator_report.py \\
      --test-run finquant/unified/agent_lab/outputs/test_run_20260501T.../

  python finquant/unified/agent_lab/operator_report.py --latest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LAB_ROOT = Path(__file__).parent
sys.path.insert(0, str(_LAB_ROOT))

DIVIDER = "═" * 60
THIN    = "─" * 60

# ─────────────────────────────────────────────────────────────
# Entry
# ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant operator-readable report")
    parser.add_argument("--test-run", type=str, help="Path to a test_run_* output directory")
    parser.add_argument("--cycle-dir", type=str, help="Path to a single cycle_* directory")
    parser.add_argument("--ab-cycle-dir", type=str, help="Path to an ab_* (Run A/B) cycle directory")
    parser.add_argument("--latest", action="store_true", help="Read the most recent test run or ab cycle")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(_LAB_ROOT / "outputs"),
        help="Base output directory to search for --latest",
    )
    args = parser.parse_args()

    if args.latest:
        ab_dir = _find_latest_ab_cycle(args.output_dir)
        if ab_dir:
            _print_ab_report(ab_dir)
            return
        run_dir = _find_latest_test_run(args.output_dir)
        if not run_dir:
            print("No test runs or AB cycles found in", args.output_dir)
            sys.exit(1)
        _print_test_run_report(run_dir)

    elif args.ab_cycle_dir:
        _print_ab_report(Path(args.ab_cycle_dir))

    elif args.test_run:
        _print_test_run_report(Path(args.test_run))

    elif args.cycle_dir:
        _print_single_cycle_report(Path(args.cycle_dir))

    else:
        parser.error("Use --latest, --test-run, --cycle-dir, or --ab-cycle-dir")


# ─────────────────────────────────────────────────────────────
# Run A / Run B report
# ─────────────────────────────────────────────────────────────

def _print_ab_report(cycle_dir: Path) -> None:
    summary_path = cycle_dir / "run_ab_comparison_v1.json"
    if not summary_path.exists():
        print(f"No run_ab_comparison_v1.json in {cycle_dir}")
        sys.exit(1)
    summary = json.load(open(summary_path))

    a = summary.get("run_a_metrics_v1", {})
    b = summary.get("run_b_metrics_v1", {})
    delta = summary.get("delta_v1", {})
    units_a = summary.get("units_after_run_a_v1", {})
    units_b = summary.get("units_after_run_b_v1", {})
    decision_diff = summary.get("decision_diff_v1", {})
    verdict = summary.get("verdict_v1", {})

    print()
    print(DIVIDER)
    print("  FINQUANT — RUN A vs RUN B COMPARISON")
    print(DIVIDER)
    print(f"  Cycle dir : {cycle_dir}")
    print(f"  Date      : {summary.get('created_at_v1', '?')}")
    print(DIVIDER)
    print()
    print("  RUN METRICS")
    print(THIN)
    print(f"  {'metric':<35} {'Run A':>14} {'Run B':>14} {'delta':>14}")
    rows = [
        ("cases processed",          a.get("cases_v1"),                    b.get("cases_v1"),                    None),
        ("learning observations",    a.get("learning_observations_v1"),    b.get("learning_observations_v1"),    None),
        ("wins",                     a.get("wins_v1"),                     b.get("wins_v1"),                     delta.get("delta_wins_v1")),
        ("losses",                   a.get("losses_v1"),                   b.get("losses_v1"),                   delta.get("delta_losses_v1")),
        ("no-trade correct",         a.get("no_trade_correct_v1"),         b.get("no_trade_correct_v1"),         delta.get("delta_no_trade_correct_v1")),
        ("no-trade missed",          a.get("no_trade_missed_v1"),          b.get("no_trade_missed_v1"),          delta.get("delta_no_trade_missed_v1")),
        ("total pnl",                a.get("total_pnl_v1"),                b.get("total_pnl_v1"),                delta.get("delta_total_pnl_v1")),
        ("win rate",                 a.get("win_rate_v1"),                 b.get("win_rate_v1"),                 delta.get("delta_win_rate_v1")),
        ("expectancy (avg pnl)",     a.get("expectancy_v1"),               b.get("expectancy_v1"),               delta.get("delta_expectancy_v1")),
        ("evaluation PASS count",    a.get("evaluation_pass_v1"),          b.get("evaluation_pass_v1"),          delta.get("delta_evaluation_pass_v1")),
        ("evaluation FAIL count",    a.get("evaluation_fail_v1"),          b.get("evaluation_fail_v1"),          delta.get("delta_evaluation_fail_v1")),
        ("decision quality (pass%)", a.get("decision_quality_pass_rate_v1"), b.get("decision_quality_pass_rate_v1"), delta.get("delta_decision_quality_pass_rate_v1")),
    ]
    for label, av, bv, dv in rows:
        ds = "" if dv is None else f"{dv:+}"
        print(f"  {label:<35} {str(av):>14} {str(bv):>14} {ds:>14}")

    print()
    print("  LEARNING UNITS")
    print(THIN)
    a_by = units_a.get("by_status_v1", {}) or {}
    b_by = units_b.get("by_status_v1", {}) or {}
    print(f"  {'status':<14} {'Run A end':>10} {'Run B end':>10}")
    for status in ("active", "validated", "provisional", "candidate", "retired"):
        ac = a_by.get(status, 0)
        bc = b_by.get(status, 0)
        print(f"  {status:<14} {ac:>10} {bc:>10}")
    print(f"  {'TOTAL':<14} {units_a.get('total_units_v1', 0):>10} {units_b.get('total_units_v1', 0):>10}")

    print()
    print("  DECISION DIFF (overlapping cases)")
    print(THIN)
    print(f"  Overlap cases     : {decision_diff.get('overlap_cases_v1', 0)}")
    print(f"  Decisions same    : {decision_diff.get('decisions_same_v1', 0)}")
    print(f"  Decisions changed : {decision_diff.get('decisions_changed_v1', 0)}")
    print(f"  Change rate       : {decision_diff.get('decision_change_rate_v1', 0)}")

    print()
    print("  VERDICT")
    print(THIN)
    print(f"  Overall : {verdict.get('overall_v1', '?')}")
    print()
    for s in verdict.get("successes_v1", []):
        print(f"    + {s}")
    for s in verdict.get("issues_v1", []):
        print(f"    ! {s}")
    print()
    print(DIVIDER)


def _find_latest_ab_cycle(output_dir: str) -> Path | None:
    base = Path(output_dir)
    cycles = sorted(base.glob("ab_*"), reverse=True)
    for c in cycles:
        if (c / "run_ab_comparison_v1.json").exists():
            return c
    return None


# ─────────────────────────────────────────────────────────────
# Test-run report (from test_framework_summary.json)
# ─────────────────────────────────────────────────────────────

def _print_test_run_report(run_dir: Path) -> None:
    summary_path = run_dir / "test_framework_summary.json"
    if not summary_path.exists():
        print(f"No test_framework_summary.json in {run_dir}")
        sys.exit(1)

    summary = json.load(open(summary_path))

    print()
    print(DIVIDER)
    print("  FINQUANT OPERATOR LEARNING REPORT")
    print(DIVIDER)
    print(f"  Run ID   : {summary.get('test_run_id', '?')}")
    print(f"  Pack     : {summary.get('pack_id', '?')}")
    print(f"  Date     : {summary.get('created_at_utc', '?')}")
    overall = summary.get("overall_status_v1", "?")
    passed = summary.get("tests_passed", 0)
    total = summary.get("tests_total", 0)
    print(f"  Result   : {overall}  ({passed}/{total} tests passed)")
    print(DIVIDER)

    for result in summary.get("results_v1", []):
        print()
        print(f"  TEST: {result.get('test_id', '?')}")
        print(THIN)

        cycle_dir = result.get("cycle_dir")
        if cycle_dir and Path(cycle_dir).exists():
            _print_single_cycle_report(Path(cycle_dir), indent="  ")
        else:
            verdict = result.get("verdict_v1", "?")
            retrieval = result.get("retrieval_match_count_v1", 0)
            print(f"  Verdict      : {_plain_verdict(verdict)}")
            print(f"  Memory used  : {retrieval} prior record(s)")

    print()
    print(DIVIDER)
    print(_overall_plain_summary(summary))
    print(DIVIDER)
    print()


# ─────────────────────────────────────────────────────────────
# Single cycle report (from student_learning_referee_report_v1.json)
# ─────────────────────────────────────────────────────────────

def _print_single_cycle_report(cycle_dir: Path, indent: str = "") -> None:
    report_path = cycle_dir / "student_learning_referee_report_v1.json"
    if not report_path.exists():
        print(f"{indent}No referee report found in {cycle_dir}")
        return

    report = json.load(open(report_path))
    bd = report.get("behavior_delta_v1", {})
    od = report.get("outcome_delta_v1", {})
    checks = {c["id"]: c for c in report.get("proof_checks_v1", [])}

    model = report.get("model_resolved_v1") or "stub (no LLM)"
    retrieval = report.get("retrieval_match_count_v1", 0)
    verdict = report.get("verdict_v1", "?")
    scenario = report.get("scenario_id", "?")
    control_action = bd.get("control_action_v1", "NO_TRADE")
    candidate_action = bd.get("candidate_action_v1", "NO_TRADE")
    control_status = od.get("control_final_status_v1", "?")
    candidate_status = od.get("candidate_final_status_v1", "?")

    # NEW: learning unit summary (engineering-grade learning surface)
    units_summary = report.get("learning_units_summary_v1") or _try_load_learning_units(cycle_dir)

    p = lambda s: print(f"{indent}{s}")

    p(f"  Scenario : {scenario}")
    p(f"  Model    : {model}")
    p("")
    p("  WHAT HAPPENED STEP BY STEP")
    p(THIN.replace("─", " ─")[2:])
    p("")
    p(f"  Step 1 — Seed run (building memory)")
    p(f"           The student ran a training case with memory write enabled.")
    seed_writes = report.get("store_writes_count_v1", 0)
    if seed_writes > 0:
        seed_eligible = checks.get("eligible_memory_exists", {}).get("pass", False)
        if seed_eligible:
            p(f"           ✓ Produced {seed_writes} learning record(s) — marked as retrievable.")
        else:
            p(f"           ✗ Produced {seed_writes} learning record(s) — NOT promoted (student made mistakes).")
    else:
        p(f"           ✗ No learning records written.")

    p("")
    p(f"  Step 2 — Control run (no memory)")
    p(f"           The student ran the test case cold — no prior lessons loaded.")
    p(f"           Decision : {_plain_action(control_action)}")
    p(f"           Outcome  : {_plain_status(control_status)}")

    p("")
    p(f"  Step 3 — Memory run (with prior lessons)")
    p(f"           The student ran the same test case with access to prior lessons.")
    p(f"           Prior lessons found : {retrieval}")
    p(f"           Decision : {_plain_action(candidate_action)}")
    p(f"           Outcome  : {_plain_status(candidate_status)}")

    p("")
    p("  WHAT CHANGED")
    p(THIN.replace("─", " ─")[2:])
    p("")

    action_changed = bd.get("action_changed_v1", False)
    thesis_changed = bd.get("thesis_changed_v1", False)
    conf_changed = bd.get("confidence_changed_v1", False)
    retrieval_attributed = bd.get("retrieval_attributed_v1", False)
    outcome_improved = od.get("exam_result_changed_v1", False) or od.get("abstention_quality_improved_v1", False)

    p(f"  {'✓' if action_changed else '─'} Action changed       : {'YES — student chose differently' if action_changed else 'No — same decision'}")
    p(f"  {'✓' if thesis_changed else '─'} Reasoning changed    : {'YES — student explained differently' if thesis_changed else 'No — same explanation'}")
    p(f"  {'✓' if conf_changed else '─'} Confidence changed   : {'YES' if conf_changed else 'No'}")
    p(f"  {'✓' if retrieval_attributed else '─'} Memory attributed    : {'YES — prior lesson influenced the decision' if retrieval_attributed else 'No — memory did not change behavior'}")
    p(f"  {'✓' if outcome_improved else '─'} Outcome improved     : {'YES — result got better' if outcome_improved else 'No — same or neither changed'}")

    if units_summary:
        p("")
        p("  LEARNING UNITS — engineering-grade learning surface")
        p(THIN.replace("─", " ─")[2:])
        total = units_summary.get("total_units_v1", 0)
        by_status = units_summary.get("by_status_v1", {}) or {}
        p("")
        p(f"  Total patterns observed : {total}")
        for status_name in ("active", "validated", "provisional", "candidate", "retired"):
            count = by_status.get(status_name, 0)
            label = {
                "active": "Driving decisions",
                "validated": "Statistically meaningful, not yet driving",
                "provisional": "Multiple observations, logged only",
                "candidate": "First-seen, observation only",
                "retired": "Negative knowledge — explicitly suppressed",
            }[status_name]
            if count > 0:
                p(f"    {status_name:12} : {count:3}  ({label})")

    p("")
    p("  VERDICT")
    p(THIN.replace("─", " ─")[2:])
    p("")
    p(f"  {_plain_verdict(verdict)}")
    p("")
    p(f"  {_plain_explanation(verdict, retrieval, action_changed, outcome_improved, seed_writes, checks)}")


def _try_load_learning_units(cycle_dir: Path) -> dict | None:
    units_path = cycle_dir / "learning_units" / "units.json"
    if not units_path.exists():
        return None
    try:
        snapshot = json.load(open(units_path))
        units = snapshot.get("units_v1") or []
        by_status: dict[str, int] = {}
        for u in units:
            s = str(u.get("status_v1", "unknown"))
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_units_v1": len(units),
            "by_status_v1": by_status,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Plain language helpers
# ─────────────────────────────────────────────────────────────

def _plain_action(action: str) -> str:
    return {
        "ENTER_LONG": "Entered a long position (bought)",
        "ENTER_SHORT": "Entered a short position (sold)",
        "NO_TRADE": "Stood down — did not trade",
        "HOLD": "Held the existing position",
        "EXIT": "Closed the position",
    }.get(action, action)


def _plain_status(status: str | None) -> str:
    return {
        "PASS": "✓ Passed — student made the right call",
        "FAIL": "✗ Failed — student made the wrong call",
        "INFO": "○ Info — run completed, quality is neutral",
        None: "Unknown",
    }.get(status, str(status))


def _plain_verdict(verdict: str) -> str:
    labels = {
        "LEARNED_BEHAVIOR_PROVEN":
            "✓ LEARNED — Memory changed the decision AND the result got better.",
        "BEHAVIOR_CHANGED_NOT_PROVEN_BETTER":
            "◑ CHANGED — Memory changed the reasoning, but we can't prove it helped yet.",
        "MEMORY_MATCH_NO_IMPACT":
            "○ NO IMPACT — Memory was loaded but didn't change anything.",
        "MEMORY_AVAILABLE_NO_MATCH":
            "○ NO MATCH — No eligible prior lessons were found for this scenario.",
        "ENGAGEMENT_WITHOUT_STORE_WRITES":
            "✗ NO STORE — Student ran but didn't write any learning records.",
        "FALSE_LEARNING_CLAIM_REJECTED":
            "✗ REJECTED — Something looked like learning but the proof doesn't hold up.",
        "CONTROL_ONLY":
            "― BASELINE ONLY — Control run exists; no memory comparison yet.",
    }
    return labels.get(verdict, f"? {verdict}")


def _plain_explanation(
    verdict: str,
    retrieval: int,
    action_changed: bool,
    outcome_improved: bool,
    store_writes: int,
    checks: dict,
) -> str:
    eligible = checks.get("eligible_memory_exists", {}).get("pass", False)

    if verdict == "LEARNED_BEHAVIOR_PROVEN":
        return (
            "The student used a prior lesson and made a better decision because of it.\n"
            "  This is the target state. The student is genuinely learning."
        )
    if verdict == "BEHAVIOR_CHANGED_NOT_PROVEN_BETTER":
        return (
            "The student found prior lessons and its reasoning changed.\n"
            "  But both runs were already correct, so there was nothing left to improve.\n"
            "  This is normal at this stage. Run harder test cases to prove improvement."
        )
    if verdict == "MEMORY_MATCH_NO_IMPACT":
        return (
            "The student found prior lessons but didn't change its decision.\n"
            "  Memory is working but not influencing judgment yet.\n"
            "  The student needs more relevant training cases."
        )
    if verdict == "MEMORY_AVAILABLE_NO_MATCH":
        if store_writes > 0 and not eligible:
            return (
                "The seed run wrote a learning record but it was REJECTED by governance.\n"
                "  This usually means the student made a mistake in the seed run\n"
                "  (wrong action, unexpected trade, or other violation).\n"
                "  The student must first succeed in a seed case before memory is available."
            )
        return (
            "The student looked for prior lessons but found none that matched this scenario.\n"
            "  Run more seed cases with the same symbol and scenario type."
        )
    if verdict == "ENGAGEMENT_WITHOUT_STORE_WRITES":
        return (
            "The student ran but didn't write anything to memory.\n"
            "  Check that auto_promote_learning_v1 is enabled in the seed config."
        )
    return "See the referee report for details."


def _overall_plain_summary(summary: dict) -> str:
    passed = summary.get("tests_passed", 0)
    total = summary.get("tests_total", 0)
    overall = summary.get("overall_status_v1", "?")

    if overall == "PASS":
        return (
            f"  SUMMARY: All {total} test(s) produced an accepted verdict.\n"
            "  The learning loop is running. Review individual test verdicts above\n"
            "  to see whether the student proved genuine learning or is still building up."
        )
    return (
        f"  SUMMARY: {total - passed} of {total} test(s) did not meet the acceptance bar.\n"
        "  Review the verdicts above to find what's blocking."
    )


# ─────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────

def _find_latest_test_run(output_dir: str) -> Path | None:
    base = Path(output_dir)
    runs = sorted(base.glob("test_run_*"), reverse=True)
    for run in runs:
        if (run / "test_framework_summary.json").exists():
            return run
    return None


if __name__ == "__main__":
    main()
