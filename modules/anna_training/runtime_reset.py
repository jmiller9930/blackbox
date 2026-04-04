"""Remove Anna training runtime files and write a fresh ``state.json`` (curriculum/method unassigned)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.catalog import default_state
from modules.anna_training.store import anna_training_dir, save_state, state_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _wipe_anna_training_dir_files(ad: Path) -> list[str]:
    """Remove **all** regular files under ``ad`` (recursive). School + dashboard read only from here."""
    removed: list[str] = []
    if not ad.exists():
        return removed
    ad.mkdir(parents=True, exist_ok=True)
    for p in sorted(ad.rglob("*")):
        if p.is_file() and p.name != ".gitkeep":
            p.unlink()
            removed.append(str(p))
    return removed


def flush_anna_training_runtime(*, include_execution_requests: bool = True) -> dict[str, Any]:
    """
    Wipe **every file** under ``BLACKBOX_ANNA_TRAINING_DIR`` (or default ``data/runtime/anna_training``):
    ``state.json`` (school: cumulative log, skills deck, Karpathy snapshots), paper ledger, attempts,
    heartbeat JSONL, cross-checks, strategy catalog, trading_core signal, and any other loose artifacts.

    Then persist :func:`default_state` so the **training dashboard** (API + UI) sees a clean slate on next fetch.

    Optionally clear ``data/runtime/execution_plane/requests.json`` so Jack handoff IDs start fresh.

    **Stop the Karpathy loop / supervisor** before calling so files are not immediately recreated.
    """
    removed: list[str] = []
    ad = anna_training_dir()
    removed.extend(_wipe_anna_training_dir_files(ad))

    exec_cleared = False
    if include_execution_requests:
        ep = _repo_root() / "data" / "runtime" / "execution_plane" / "requests.json"
        if ep.is_file():
            ep.unlink()
            removed.append(str(ep))
            exec_cleared = True

    save_state(default_state())
    return {
        "ok": True,
        "anna_training_dir": str(ad),
        "removed_paths": removed,
        "execution_requests_cleared": exec_cleared,
        "state_written": str(state_path()),
    }
