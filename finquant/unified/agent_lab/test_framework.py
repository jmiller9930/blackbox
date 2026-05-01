"""
FinQuant Unified Agent Lab — test framework.

Runs named isolated FinQuant test packs and writes an operator-facing summary.
Each test delegates to the observable training cycle harness.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid
from pathlib import Path
from typing import Any

_LAB_ROOT = Path(__file__).parent
sys.path.insert(0, str(_LAB_ROOT))

TEST_PACK_SCHEMA = "finquant_test_pack_v1"
TEST_SUMMARY_SCHEMA = "finquant_test_framework_summary_v1"


def load_test_pack(path: str) -> tuple[dict[str, Any], Path]:
    pack_path = Path(path).resolve()
    with open(pack_path, "r") as f:
        pack = json.load(f)
    _validate_test_pack(pack, pack_path)
    return pack, pack_path


def run_test_pack(
    *,
    pack_path: str,
    config_path: str,
    output_dir: str,
    data_window_months: int | None = None,
    interval: str | None = None,
) -> dict[str, Any]:
    from training_cycle import run_training_cycle

    pack, resolved_pack_path = load_test_pack(pack_path)

    run_id = (
        f"test_run_{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
        f"_{uuid.uuid4().hex[:8]}"
    )
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    tests_passed = 0

    for test in pack["tests"]:
        seed_case_path = _resolve_from_pack(resolved_pack_path, test["seed_case_path"])
        candidate_case_path = _resolve_from_pack(resolved_pack_path, test["candidate_case_path"])

        cycle_result = run_training_cycle(
            seed_case_path=str(seed_case_path),
            candidate_case_path=str(candidate_case_path),
            config_path=config_path,
            output_dir=str(run_dir),
            data_window_months=data_window_months,
            interval=interval,
        )

        report = cycle_result["report"]
        expected_verdicts = list(test.get("expected_verdicts_v1") or [])
        expected_min_retrieval_matches = int(test.get("expected_min_retrieval_matches_v1") or 0)

        verdict_ok = (not expected_verdicts) or (report["verdict_v1"] in expected_verdicts)
        retrieval_ok = report["retrieval_match_count_v1"] >= expected_min_retrieval_matches
        passed = verdict_ok and retrieval_ok
        if passed:
            tests_passed += 1

        results.append(
            {
                "test_id": test["test_id"],
                "cycle_id": cycle_result["cycle_id"],
                "candidate_case_id": cycle_result["candidate_result"]["case"]["case_id"],
                "verdict_v1": report["verdict_v1"],
                "passed_v1": passed,
                "expected_verdicts_v1": expected_verdicts,
                "retrieval_match_count_v1": report["retrieval_match_count_v1"],
                "expected_min_retrieval_matches_v1": expected_min_retrieval_matches,
                "report_path": cycle_result["report_path"],
                "cycle_dir": cycle_result["cycle_dir"],
            }
        )

    overall_status = "PASS" if tests_passed == len(results) else "FAIL"
    summary = {
        "schema": TEST_SUMMARY_SCHEMA,
        "created_at_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_run_id": run_id,
        "pack_id": pack["pack_id"],
        "pack_path": str(resolved_pack_path),
        "tests_total": len(results),
        "tests_passed": tests_passed,
        "overall_status_v1": overall_status,
        "results_v1": results,
    }

    summary_path = run_dir / "test_framework_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    markdown_path = run_dir / "test_framework_summary.md"
    with open(markdown_path, "w") as f:
        f.write(_render_markdown_summary(summary))

    return {
        "summary": summary,
        "summary_path": str(summary_path),
        "markdown_path": str(markdown_path),
        "run_dir": str(run_dir),
    }


def _validate_test_pack(pack: dict[str, Any], path: Path) -> None:
    if pack.get("schema") != TEST_PACK_SCHEMA:
        raise ValueError(f"test pack schema must be '{TEST_PACK_SCHEMA}' in {path}")
    if not str(pack.get("pack_id") or "").strip():
        raise ValueError(f"test pack missing pack_id in {path}")
    tests = pack.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError(f"test pack must contain non-empty tests[] in {path}")
    required = {"test_id", "seed_case_path", "candidate_case_path"}
    for test in tests:
        if not isinstance(test, dict):
            raise ValueError(f"each test must be an object in {path}")
        missing = [k for k in required if k not in test]
        if missing:
            raise ValueError(f"test missing fields {missing} in {path}")


def _resolve_from_pack(pack_path: Path, relative_or_abs: str) -> Path:
    candidate = Path(relative_or_abs)
    if candidate.is_absolute():
        return candidate
    return (pack_path.parent / candidate).resolve()


def _render_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"# FinQuant Test Summary — {summary['pack_id']}",
        "",
        f"- Run ID: `{summary['test_run_id']}`",
        f"- Overall status: `{summary['overall_status_v1']}`",
        f"- Tests passed: `{summary['tests_passed']}/{summary['tests_total']}`",
        "",
        "| Test ID | Verdict | Passed | Retrieval Matches | Report |",
        "|---|---|---:|---:|---|",
    ]
    for result in summary["results_v1"]:
        lines.append(
            f"| `{result['test_id']}` | `{result['verdict_v1']}` | "
            f"`{str(result['passed_v1']).lower()}` | `{result['retrieval_match_count_v1']}` | "
            f"`{result['report_path']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant isolated test framework")
    parser.add_argument(
        "--test-pack",
        required=True,
        type=str,
        help="Path to a finquant_test_pack_v1 JSON file",
    )
    parser.add_argument(
        "--config",
        required=False,
        type=str,
        default=str(_LAB_ROOT / "configs" / "default_lab_config.json"),
    )
    parser.add_argument(
        "--output-dir",
        required=False,
        type=str,
        default=str(_LAB_ROOT / "outputs"),
    )
    parser.add_argument("--data-window-months", type=int, default=None)
    parser.add_argument("--interval", type=str, default=None)
    args = parser.parse_args()

    result = run_test_pack(
        pack_path=args.test_pack,
        config_path=args.config,
        output_dir=args.output_dir,
        data_window_months=args.data_window_months,
        interval=args.interval,
    )
    print(
        json.dumps(
            {
                "test_run_id": result["summary"]["test_run_id"],
                "summary_path": result["summary_path"],
                "overall_status_v1": result["summary"]["overall_status_v1"],
                "tests_passed": result["summary"]["tests_passed"],
                "tests_total": result["summary"]["tests_total"],
            },
            indent=2,
        )
    )
    sys.exit(0 if result["summary"]["overall_status_v1"] == "PASS" else 1)


if __name__ == "__main__":
    main()
