"""
student_test_mode_v1 — engineering-triggered isolated Student seam validation.

All Student memory, traces, scorecard-adjacent JSONL defaults, and learning stores resolve under
``runtime/student_test/<job_id>/`` when :func:`apply_student_test_mode_env_v1` runs **before**
imports that resolve paths.

Market SQLite bars stay read-only (unchanged); production promoted bundles, Groundhog merges, and
production Student learning reads are disabled for v1 (see env + ``retrieve_applicable_learning_context_026c_v1``).
"""

from __future__ import annotations

import copy
import os
import sqlite3
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_to_jsonable
from renaissance_v4.game_theory.groundhog_memory import resolve_memory_bundle_for_scenario
from renaissance_v4.game_theory.pattern_game import prepare_effective_manifest_for_replay
from renaissance_v4.game_theory.pml_runtime_layout import blackbox_repo_root
from renaissance_v4.manifest.validate import load_manifest_file
from renaissance_v4.utils.db import DB_PATH

STUDENT_TEST_MODE_FLAG_V1 = "student_test_mode_v1"
STUDENT_TEST_REQUIRED_TRADE_COUNT_V1 = 10
STUDENT_TEST_INSUFFICIENT_TRADE_COUNT_V1 = "student_test_insufficient_trade_count_v1"
STUDENT_TEST_INSUFFICIENT_DB_ANCHOR_TIMES_V1 = "student_test_insufficient_db_anchor_times_v1"
STUDENT_TEST_ISOLATION_ENV_V1 = "PATTERN_GAME_STUDENT_TEST_ISOLATION_V1"


class StudentTestInsufficientTradesError(Exception):
    """Replay produced fewer closed trades than :data:`STUDENT_TEST_REQUIRED_TRADE_COUNT_V1`."""

    def __init__(self, total: int, *, required: int = STUDENT_TEST_REQUIRED_TRADE_COUNT_V1) -> None:
        self.total = total
        self.required = required
        super().__init__(f"{STUDENT_TEST_INSUFFICIENT_TRADE_COUNT_V1}: got {total}, need {required}")


def _symbol_from_manifest_student_test_v1(manifest: dict[str, Any]) -> str:
    sym = str(manifest.get("symbol") or "").strip()
    if sym:
        return sym
    return str(manifest.get("strategy_id") or "").strip()


def _decision_open_times_from_db_v1(db_path: Path, symbol: str, n: int) -> list[int]:
    """Latest ``n`` bar open times for ``symbol`` (same query family as Student behavior probe)."""
    try:
        conn = sqlite3.connect(str(db_path))
    except OSError:
        return []
    try:
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT open_time FROM market_bars_5m WHERE symbol = ? ORDER BY open_time DESC LIMIT ?",
            (symbol, max(1, int(n))),
        ).fetchall()
        return [int(r[0]) for r in rows if r and r[0] is not None]
    finally:
        conn.close()


def build_student_test_mode_parallel_results_from_db_anchors_v1(
    *,
    scenarios: list[dict[str, Any]],
    trade_count: int = STUDENT_TEST_REQUIRED_TRADE_COUNT_V1,
    db_path: Path | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """
    Deterministic proof harness: **exactly** ``trade_count`` synthetic :class:`OutcomeRecord` shells,
    anchored on the latest ``trade_count`` rows in ``market_bars_5m`` for the scenario manifest symbol.

    Same packet philosophy as ``build_probe_minimal_results_v1`` (DB-backed anchors; not Referee PnL replay).
    When the recipe lists multiple scenarios, only the **first** carries the ten outcomes; remaining rows are
    empty ``replay_outcomes_json`` so parallel batch shape matches recipe cardinality.
    """
    if not scenarios:
        return None, "student_test_empty_scenarios_v1"
    scen0 = scenarios[0]
    mbp = scen0.get("memory_bundle_path")
    if mbp:
        mbp = str(Path(str(mbp)).expanduser().resolve())
    else:
        mbp = resolve_memory_bundle_for_scenario(scen0, explicit_path=None)

    prep = None
    try:
        prep = prepare_effective_manifest_for_replay(
            scen0["manifest_path"],
            atr_stop_mult=scen0.get("atr_stop_mult"),
            atr_target_mult=scen0.get("atr_target_mult"),
            memory_bundle_path=mbp,
            use_groundhog_auto_resolve=False,
        )
        manifest = load_manifest_file(prep.replay_path)
    except Exception as e:
        if prep is not None:
            try:
                prep.cleanup()
            except Exception:
                pass
        return None, f"student_test_manifest_prepare_failed_v1:{type(e).__name__}:{e}"

    try:
        sym = _symbol_from_manifest_student_test_v1(manifest)
        db_used = Path(str(db_path or DB_PATH)).resolve()
        times = _decision_open_times_from_db_v1(db_used, sym, trade_count)
        if len(times) < trade_count:
            return (
                None,
                f"{STUDENT_TEST_INSUFFICIENT_DB_ANCHOR_TIMES_V1}: need at least {trade_count} rows in "
                f"market_bars_5m for symbol={sym!r} in {db_used}, got {len(times)}",
            )

        sid = str(scen0.get("scenario_id") or "student_test_scenario_v1").strip() or "student_test_scenario_v1"
        outcomes: list[dict[str, Any]] = []
        for i, t_ms in enumerate(times[:trade_count]):
            exit_ms = int(t_ms) + 300_000
            o = OutcomeRecord(
                trade_id=f"student_test_{i:04d}_v1",
                symbol=sym,
                direction="long",
                entry_time=int(t_ms),
                exit_time=exit_ms,
                entry_price=1.0,
                exit_price=1.01,
                pnl=0.0,
                mae=0.0,
                mfe=0.0,
                exit_reason="student_test_mode_db_anchor_shell_v1",
                metadata={"student_test_mode_v1_db_anchor_shell_v1": True},
            )
            outcomes.append(outcome_record_to_jsonable(o))

        primary = {
            "ok": True,
            "scenario_id": sid,
            "replay_outcomes_json": outcomes,
        }
        rows: list[dict[str, Any]] = [primary]
        for s in scenarios[1:]:
            sid_i = str(s.get("scenario_id") or "").strip() or "scenario_v1"
            rows.append({"ok": True, "scenario_id": sid_i, "replay_outcomes_json": []})
        return rows, None
    finally:
        if prep is not None:
            try:
                prep.cleanup()
            except Exception:
                pass


def student_test_job_runtime_root_v1(job_id: str) -> Path:
    jid = str(job_id).strip()
    if not jid:
        raise ValueError("student_test_mode_v1 requires non-empty job_id")
    return (blackbox_repo_root() / "runtime" / "student_test" / jid).resolve()


def apply_student_test_mode_env_v1(job_id: str, *, repo_root: Path | None = None) -> dict[str, str]:
    """
    Env overrides so PML runtime + memory JSONL roots sit under ``runtime/student_test/<job_id>/``.

    Returns a dict suitable for ``os.environ.update(...)``. Idempotent for repeated calls with same job_id.
    """
    root = student_test_job_runtime_root_v1(job_id)
    root.mkdir(parents=True, exist_ok=True)
    logs = root / "logs"
    telemetry = logs / "pattern_game_telemetry"
    batches = root / "batches"
    for d in (logs, telemetry, batches):
        d.mkdir(parents=True, exist_ok=True)
    # Repo root is only used for consistency checks; blackbox_repo_root() matches checkout.
    _ = repo_root
    env = {
        "BLACKBOX_PML_RUNTIME_ROOT": str(root),
        "PATTERN_GAME_MEMORY_ROOT": str(root),
        "PATTERN_GAME_TELEMETRY_DIR": str(telemetry),
        "PATTERN_GAME_SESSION_LOGS_ROOT": str(batches),
        "PATTERN_GAME_GROUNDHOG_BUNDLE": "0",
        STUDENT_TEST_ISOLATION_ENV_V1: "1",
    }
    # Proof harness expects learning-loop JSONL (decision fingerprint report reads trace).
    env["PATTERN_GAME_LEARNING_TRACE_EVENTS"] = os.environ.get("PATTERN_GAME_LEARNING_TRACE_EVENTS", "1").strip() or "1"
    return env


def student_test_mode_isolation_active_v1() -> bool:
    return os.environ.get(STUDENT_TEST_ISOLATION_ENV_V1, "").strip() in ("1", "true", "yes", "on")


def count_replay_outcomes_parallel_results_v1(results: list[dict[str, Any]] | None) -> int:
    n = 0
    for r in results or []:
        if not r.get("ok"):
            continue
        n += len(r.get("replay_outcomes_json") or [])
    return n


def truncate_parallel_results_to_trade_budget_v1(
    results: list[dict[str, Any]],
    *,
    budget: int = STUDENT_TEST_REQUIRED_TRADE_COUNT_V1,
) -> list[dict[str, Any]]:
    """
    Keep scenario order; take the first ``budget`` trades across ok rows; clear overflow rows' outcomes.

    Raises :class:`StudentTestInsufficientTradesError` when total ok trades < ``budget``.
    """
    total = count_replay_outcomes_parallel_results_v1(results)
    if total < budget:
        raise StudentTestInsufficientTradesError(total, required=budget)
    out = copy.deepcopy(results)
    remaining = budget
    for r in out:
        if not r.get("ok"):
            continue
        ro = list(r.get("replay_outcomes_json") or [])
        if remaining <= 0:
            r["replay_outcomes_json"] = []
            continue
        if len(ro) <= remaining:
            r["replay_outcomes_json"] = ro
            remaining -= len(ro)
        else:
            r["replay_outcomes_json"] = ro[:remaining]
            remaining = 0
    return out
