"""
memory_paths.py — where pattern-game **memory I/O** lives on disk.

Set **PATTERN_GAME_MEMORY_ROOT** to a directory on a **RAM-backed filesystem** (tmpfs, ramdisk)
when you want append/read latency minimal for logs and JSONL queues. The tree is still
**files on a filesystem** — permanence is whatever that mount provides (tmpfs clears on reboot
unless you mirror/sync elsewhere).

Typical Linux::

    sudo mkdir -p /mnt/pattern_mem
    sudo mount -t tmpfs -o size=512M tmpfs /mnt/pattern_mem
    export PATTERN_GAME_MEMORY_ROOT=/mnt/pattern_mem

Layout under the root (created on demand)::

    {MEMORY_ROOT}/logs/              # session + batch folders
    {MEMORY_ROOT}/run_memory.jsonl
    {MEMORY_ROOT}/experience_log.jsonl
    {MEMORY_ROOT}/batch_scorecard.jsonl   # batch run timing + totals (web UI + scripts)
    {MEMORY_ROOT}/ask_data_operator_feedback.jsonl  # Ask DATA interaction + operator rating lines (not Referee)
    {MEMORY_ROOT}/retrospective_log.jsonl # operator/agent “what we learned / try next” (not Referee scores)
"""

from __future__ import annotations

import os
from pathlib import Path

_GAME_THEORY = Path(__file__).resolve().parent


def memory_root() -> Path | None:
    """If ``PATTERN_GAME_MEMORY_ROOT`` is set, all default memory paths use this prefix."""
    v = os.environ.get("PATTERN_GAME_MEMORY_ROOT", "").strip()
    return Path(v).expanduser() if v else None


def default_logs_root() -> Path:
    mr = memory_root()
    if mr:
        return mr / "logs"
    return _GAME_THEORY / "logs"


def default_run_memory_jsonl() -> Path:
    mr = memory_root()
    if mr:
        return mr / "run_memory.jsonl"
    return _GAME_THEORY / "run_memory.jsonl"


def default_experience_log_jsonl() -> Path:
    mr = memory_root()
    if mr:
        return mr / "experience_log.jsonl"
    return _GAME_THEORY / "experience_log.jsonl"


def default_batch_scorecard_jsonl() -> Path:
    """Append-only batch timing scorecard (parallel runs: start/end, counts)."""
    mr = memory_root()
    if mr:
        return mr / "batch_scorecard.jsonl"
    return _GAME_THEORY / "batch_scorecard.jsonl"


def default_retrospective_log_jsonl() -> Path:
    """Append-only retrospective lines (hypothesis follow-ups, what to try next)."""
    mr = memory_root()
    if mr:
        return mr / "retrospective_log.jsonl"
    return _GAME_THEORY / "retrospective_log.jsonl"


def default_ask_data_operator_feedback_jsonl() -> Path:
    """Append-only Ask DATA telemetry: ``interaction`` lines plus operator ``feedback`` (ratings/tags)."""
    mr = memory_root()
    if mr:
        return mr / "ask_data_operator_feedback.jsonl"
    return _GAME_THEORY / "ask_data_operator_feedback.jsonl"


def default_learning_trace_events_jsonl() -> Path:
    """Append-only **learning_trace_events_v1** (runtime handoffs not reconstructable from scorecard alone)."""
    mr = memory_root()
    if mr:
        return mr / "learning_trace_events_v1.jsonl"
    return _GAME_THEORY / "learning_trace_events_v1.jsonl"


def ensure_memory_root_tree() -> None:
    """Create ``logs`` under memory root when ``PATTERN_GAME_MEMORY_ROOT`` is set (idempotent)."""
    mr = memory_root()
    if mr:
        (mr / "logs").mkdir(parents=True, exist_ok=True)
