"""Remove Anna training runtime files and write a fresh ``state.json`` (curriculum/method unassigned)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.catalog import default_state
from modules.anna_training.execution_ledger import default_execution_ledger_path
from modules.anna_training.store import anna_training_dir, save_state, state_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _unlink_sqlite_database_and_sidecars(db_path: Path) -> list[str]:
    """
    Remove main SQLite file plus common sidecars (``-wal``, ``-shm``, ``-journal``) if present.

    Uses the resolved path (``BLACKBOX_EXECUTION_LEDGER_PATH`` when set).
    """
    removed: list[str] = []
    p = Path(db_path).expanduser()
    candidates = [
        p,
        Path(str(p) + "-wal"),
        Path(str(p) + "-shm"),
        Path(str(p) + "-journal"),
    ]
    for cand in candidates:
        try:
            if cand.is_file():
                cand.unlink()
                removed.append(str(cand))
        except OSError:
            pass
    return removed


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

    Deletes the **execution ledger** SQLite file at :func:`default_execution_ledger_path` (``execution_trades``,
    ``decision_traces``, and all derived PnL rows) plus WAL/SHM/journal sidecars.

    Then persist :func:`default_state` so the **training dashboard** (API + UI) sees a clean slate on next fetch.

    Optionally clear ``data/runtime/execution_plane/requests.json`` so Jack handoff IDs start fresh.

    **Stop the Karpathy loop / supervisor** before calling so files are not immediately recreated.

    Does **not** delete **live market data** collection: canonical market DB (``BLACKBOX_MARKET_DATA_PATH`` / ``data/sqlite/market_data.db``), Pyth/Hermes probe JSON (``docs/working/artifacts/pyth_stream_*.json``), or other ingest stores — only training dir + execution ledger + optional execution-plane request queue.
    """
    removed: list[str] = []
    ad = anna_training_dir()
    removed.extend(_wipe_anna_training_dir_files(ad))

    elp = default_execution_ledger_path()
    removed.extend(_unlink_sqlite_database_and_sidecars(elp))

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
        "execution_ledger_path": str(elp),
        "removed_paths": removed,
        "execution_requests_cleared": exec_cleared,
        "state_written": str(state_path()),
    }
