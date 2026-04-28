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
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.pml_runtime_layout import blackbox_repo_root

STUDENT_TEST_MODE_FLAG_V1 = "student_test_mode_v1"
STUDENT_TEST_REQUIRED_TRADE_COUNT_V1 = 10
STUDENT_TEST_INSUFFICIENT_TRADE_COUNT_V1 = "student_test_insufficient_trade_count_v1"
STUDENT_TEST_ISOLATION_ENV_V1 = "PATTERN_GAME_STUDENT_TEST_ISOLATION_V1"


class StudentTestInsufficientTradesError(Exception):
    """Replay produced fewer closed trades than :data:`STUDENT_TEST_REQUIRED_TRADE_COUNT_V1`."""

    def __init__(self, total: int, *, required: int = STUDENT_TEST_REQUIRED_TRADE_COUNT_V1) -> None:
        self.total = total
        self.required = required
        super().__init__(f"{STUDENT_TEST_INSUFFICIENT_TRADE_COUNT_V1}: got {total}, need {required}")


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
    return {
        "BLACKBOX_PML_RUNTIME_ROOT": str(root),
        "PATTERN_GAME_MEMORY_ROOT": str(root),
        "PATTERN_GAME_TELEMETRY_DIR": str(telemetry),
        "PATTERN_GAME_SESSION_LOGS_ROOT": str(batches),
        "PATTERN_GAME_GROUNDHOG_BUNDLE": "0",
        STUDENT_TEST_ISOLATION_ENV_V1: "1",
    }


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
