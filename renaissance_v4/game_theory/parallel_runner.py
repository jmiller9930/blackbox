"""
parallel_runner.py

Run many pattern-game scenarios in parallel (separate processes) to use multiple cores.

SQLite is read by each worker; keep concurrent writes (experience log) in the parent process only.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.pattern_game import json_summary, run_pattern_game

DEFAULT_WORKERS = max(1, (os.cpu_count() or 4))


def _worker_run_one(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    Top-level for multiprocessing pickling. Returns JSON-friendly dict only.
    """
    sid = scenario.get("scenario_id", "unknown")
    try:
        out = run_pattern_game(
            scenario["manifest_path"],
            atr_stop_mult=scenario.get("atr_stop_mult"),
            atr_target_mult=scenario.get("atr_target_mult"),
            emit_baseline_artifacts=bool(scenario.get("emit_baseline_artifacts", False)),
            verbose=False,
        )
        return {
            "ok": True,
            "scenario_id": sid,
            "summary": json_summary(out),
            "validation_checksum": out.get("validation_checksum"),
            "cumulative_pnl": out.get("cumulative_pnl"),
            "dataset_bars": out.get("dataset_bars"),
            "manifest_path": str(scenario.get("manifest_path", "")),
        }
    except Exception as e:
        return {
            "ok": False,
            "scenario_id": sid,
            "error": f"{type(e).__name__}: {e}",
            "manifest_path": str(scenario.get("manifest_path", "")),
        }


def _normalize_scenario(s: dict[str, Any]) -> dict[str, Any]:
    """Resolve manifest path so worker processes do not depend on cwd."""
    n = dict(s)
    mp = n.get("manifest_path")
    if mp:
        n["manifest_path"] = str(Path(mp).expanduser().resolve())
    return n


def run_scenarios_parallel(
    scenarios: list[dict[str, Any]],
    *,
    max_workers: int | None = None,
    experience_log_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    Run each scenario in a process pool. Order of results is **completion** order unless you sort by scenario_id.

    Each scenario dict should include ``manifest_path`` and optional ``scenario_id``, ``atr_stop_mult``,
    ``atr_target_mult``, ``emit_baseline_artifacts``.

    If ``experience_log_path`` is set, append one JSON line per result (parent process only).
    """
    if not scenarios:
        return []

    normalized = [_normalize_scenario(s) for s in scenarios]

    workers = max_workers if max_workers is not None else DEFAULT_WORKERS
    workers = max(1, min(workers, len(normalized)))

    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker_run_one, s): s for s in normalized}
        for fut in as_completed(futures):
            results.append(fut.result())

    if experience_log_path is not None:
        p = Path(experience_log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    return results


def _load_scenarios_from_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict) and "scenarios" in raw:
        s = raw["scenarios"]
        return [x for x in s if isinstance(x, dict)]
    raise ValueError("JSON must be a list of scenario objects or { \"scenarios\": [ ... ] }")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run multiple pattern-game scenarios in parallel (process pool).",
    )
    parser.add_argument(
        "scenarios_json",
        type=str,
        help="JSON file: list of { scenario_id?, manifest_path, atr_stop_mult?, atr_target_mult? }",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=None,
        help=f"Max parallel workers (default: min(cpu_count, num scenarios), ~{DEFAULT_WORKERS})",
    )
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="Append JSONL results to this path (default: game_theory/experience_log.jsonl)",
    )
    args = parser.parse_args()
    scenarios_path = Path(args.scenarios_json)
    scenarios = _load_scenarios_from_json(scenarios_path)

    log_path = args.log
    if log_path is None:
        log_path = Path(__file__).resolve().parent / "experience_log.jsonl"

    results = run_scenarios_parallel(
        scenarios,
        max_workers=args.jobs,
        experience_log_path=log_path,
    )
    ok = sum(1 for r in results if r.get("ok"))
    print(json.dumps({"ran": len(results), "ok": ok, "failed": len(results) - ok, "results": results}, indent=2))


if __name__ == "__main__":
    main()
