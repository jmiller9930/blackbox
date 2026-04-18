"""
parallel_runner.py

Run many pattern-game scenarios in parallel (separate processes) to use multiple cores.

SQLite is read by each worker; keep concurrent writes (experience log) in the parent process only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.pattern_game import json_summary, run_pattern_game
from renaissance_v4.game_theory.run_memory import append_run_memory, build_run_memory_record
from renaissance_v4.game_theory.run_session_log import (
    allocate_unique_run_directory,
    default_logs_root,
    write_batch_index_and_scenario_logs,
)
from renaissance_v4.game_theory.scenario_contract import extract_scenario_echo_fields

DEFAULT_WORKERS = max(1, (os.cpu_count() or 4))

# Hard cap: avoid fork/memory storms; soft recommendation = logical CPUs (CPU-bound replay).
_MAX_PARALLEL_ABS = 64


def get_parallel_limits() -> dict[str, Any]:
    """
    Exposed for UI / API: recommended and maximum parallel workers for this host.

    Uses **processes** (not OS threads); each scenario runs a replay in a worker process.
    """
    cpu = os.cpu_count() or 4
    hard = min(_MAX_PARALLEL_ABS, max(1, cpu * 2))
    return {
        "cpu_logical_count": cpu,
        "recommended_max_workers": cpu,
        "hard_cap_workers": hard,
        "note": "Workers are processes, not Python threads; past ~CPU count yields diminishing returns for CPU-bound replay.",
    }


def clamp_parallel_workers(requested: int | None, num_scenarios: int) -> int:
    """Clamp user-requested worker count to [1, hard_cap, num_scenarios]."""
    if num_scenarios < 1:
        return 1
    limits = get_parallel_limits()
    hard = int(limits["hard_cap_workers"])
    if requested is None:
        return max(1, min(DEFAULT_WORKERS, num_scenarios, hard))
    try:
        w = int(requested)
    except (TypeError, ValueError):
        w = DEFAULT_WORKERS
    return max(1, min(w, num_scenarios, hard))


def _worker_run_one(scenario: dict[str, Any]) -> dict[str, Any]:
    """
    Top-level for multiprocessing pickling. Returns JSON-friendly dict only.
    """
    sid = scenario.get("scenario_id", "unknown")
    try:
        mbp = scenario.get("memory_bundle_path")
        if mbp:
            mbp = str(Path(mbp).expanduser().resolve())
        out = run_pattern_game(
            scenario["manifest_path"],
            atr_stop_mult=scenario.get("atr_stop_mult"),
            atr_target_mult=scenario.get("atr_target_mult"),
            memory_bundle_path=mbp,
            emit_baseline_artifacts=bool(scenario.get("emit_baseline_artifacts", False)),
            verbose=False,
        )
        row: dict[str, Any] = {
            "ok": True,
            "scenario_id": sid,
            "summary": json_summary(out),
            "validation_checksum": out.get("validation_checksum"),
            "cumulative_pnl": out.get("cumulative_pnl"),
            "dataset_bars": out.get("dataset_bars"),
            "manifest_path": str(scenario.get("manifest_path", "")),
            "memory_bundle_audit": out.get("memory_bundle_audit"),
        }
        row.update(extract_scenario_echo_fields(scenario))
        return row
    except Exception as e:
        row = {
            "ok": False,
            "scenario_id": sid,
            "error": f"{type(e).__name__}: {e}",
            "manifest_path": str(scenario.get("manifest_path", "")),
        }
        row.update(extract_scenario_echo_fields(scenario))
        return row


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
    run_memory_log_path: Path | str | None = None,
    write_session_logs: bool = True,
    session_logs_base: Path | str | None = None,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
    on_session_log_batch: Callable[[Path], None] | None = None,
) -> list[dict[str, Any]]:
    """
    Run each scenario in a process pool. Order of results is **completion** order unless you sort by scenario_id.

    Each scenario dict should include ``manifest_path`` and optional ``scenario_id``, ``atr_stop_mult``,
    ``atr_target_mult``, ``emit_baseline_artifacts``. Optional **echo** fields (tier,
    ``evaluation_window``, ``agent_explanation``, ids, etc.) are copied into each result for audit;
    the Referee does not use them for scoring. See ``scenario_contract.py`` / README.

    If ``experience_log_path`` is set, append one JSON line per result (parent process only).

    If ``run_memory_log_path`` is set, append one structured :mod:`run_memory` JSONL line per
    result (hypothesis + indicator_context + referee summary — durable audit trail).

    If ``write_session_logs`` is True (default), create ``logs/batch_<UTC>_<id>/`` with one subfolder
    per scenario containing ``HUMAN_READABLE.md`` and ``run_record.json``. Disable with
    ``write_session_logs=False`` or env ``PATTERN_GAME_NO_SESSION_LOG=1``.

    If ``progress_callback`` is set, it is invoked after each scenario completes as
    ``(completed_count, total_count, result_row)`` for live progress UIs.

    If session logs are written and ``on_session_log_batch`` is set, it is called once with the
    ``batch_*`` directory path (for UIs and APIs).
    """
    if not scenarios:
        return []

    normalized = [_normalize_scenario(s) for s in scenarios]

    workers = clamp_parallel_workers(max_workers, len(normalized))
    total = len(normalized)

    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker_run_one, s): s for s in normalized}
        completed = 0
        for fut in as_completed(futures):
            row = fut.result()
            results.append(row)
            completed += 1
            if progress_callback is not None:
                progress_callback(completed, total, row)

    if experience_log_path is not None:
        p = Path(experience_log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    by_sid = {str(s.get("scenario_id", "")): s for s in normalized}
    mem_p = Path(run_memory_log_path) if run_memory_log_path is not None else None
    if mem_p is not None:
        mem_p.parent.mkdir(parents=True, exist_ok=True)

    session_ok = write_session_logs and os.environ.get("PATTERN_GAME_NO_SESSION_LOG", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )
    session_records: list[tuple[str, dict[str, Any]]] = []

    for row in results:
        sid = str(row.get("scenario_id", "")) or "unknown"
        scen = by_sid.get(str(row.get("scenario_id", "")))
        mp = str(row.get("manifest_path") or (scen or {}).get("manifest_path", ""))
        summ = row.get("summary") if row.get("ok") else None
        err = None if row.get("ok") else str(row.get("error", "unknown"))
        atr_s = None
        atr_t = None
        if scen:
            atr_s = scen.get("atr_stop_mult")
            atr_t = scen.get("atr_target_mult")
            if isinstance(atr_s, (int, float)):
                atr_s = float(atr_s)
            else:
                atr_s = None
            if isinstance(atr_t, (int, float)):
                atr_t = float(atr_t)
            else:
                atr_t = None
        prior_rid = None
        if scen and scen.get("prior_run_id") is not None:
            prior_rid = str(scen["prior_run_id"])
        rec = build_run_memory_record(
            source="parallel_scenarios",
            manifest_path=mp,
            json_summary_row=summ,
            scenario=scen,
            parallel_error=err,
            atr_stop_mult=atr_s,
            atr_target_mult=atr_t,
            prior_run_id=prior_rid,
            memory_bundle_audit=row.get("memory_bundle_audit"),
        )
        if mem_p is not None:
            append_run_memory(mem_p, rec)
        if session_ok:
            session_records.append((sid, rec))

    if session_ok and session_records:
        root_raw = session_logs_base or os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT")
        log_root = Path(root_raw).expanduser() if root_raw else default_logs_root()
        batch_dir = allocate_unique_run_directory(logs_root=log_root, prefix="batch")
        write_batch_index_and_scenario_logs(batch_dir, session_records)
        print(
            f"[session_log] batch folder={batch_dir} ({len(session_records)} scenarios — see BATCH_README.md)",
            file=sys.stderr,
        )
        if on_session_log_batch is not None:
            on_session_log_batch(batch_dir)

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
    parser.add_argument(
        "--run-memory-log",
        type=str,
        nargs="?",
        const="default",
        default=None,
        help="Also append structured run_memory JSONL (default: game_theory/run_memory.jsonl)",
    )
    parser.add_argument(
        "--no-session-log",
        action="store_true",
        help="Skip logs/batch_<UTC>_<id>/ human-readable folders (default: session logs ON)",
    )
    parser.add_argument(
        "--session-logs-root",
        type=str,
        default=None,
        help="Base directory for batch session folders (default: game_theory/logs)",
    )
    args = parser.parse_args()
    scenarios_path = Path(args.scenarios_json)
    scenarios = _load_scenarios_from_json(scenarios_path)

    log_path = args.log
    if log_path is None:
        log_path = Path(__file__).resolve().parent / "experience_log.jsonl"

    rmem: Path | None = None
    if args.run_memory_log is not None:
        rmem = (
            Path(__file__).resolve().parent / "run_memory.jsonl"
            if args.run_memory_log in ("default", "1")
            else Path(args.run_memory_log).expanduser()
        )

    sl_root = Path(args.session_logs_root).expanduser() if args.session_logs_root else None
    results = run_scenarios_parallel(
        scenarios,
        max_workers=args.jobs,
        experience_log_path=log_path,
        run_memory_log_path=rmem,
        write_session_logs=not args.no_session_log,
        session_logs_base=sl_root,
    )
    ok = sum(1 for r in results if r.get("ok"))
    print(json.dumps({"ran": len(results), "ok": ok, "failed": len(results) - ok, "results": results}, indent=2))


if __name__ == "__main__":
    main()
