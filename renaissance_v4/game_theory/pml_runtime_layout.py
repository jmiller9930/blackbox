"""
PML runtime disk layout — **explicit** paths for logs, proofs, and batch artifacts.

**Path choice (engineer-confirmed default):** ``<repo_root>/runtime/{logs,proofs,batches}``
where ``repo_root`` is the parent of ``renaissance_v4/``.

**Override (e.g. dedicated mount):** set ``BLACKBOX_PML_RUNTIME_ROOT=/mnt/pml_runtime`` (or any
absolute path). The application prints the resolved root at Flask startup — **no silent
alternate root**.

**Do not** use ``/tmp`` for Flask logs, proof captures, replay stdout, batch session trees, or
live telemetry snapshots; those belong under this runtime tree (or the explicit mount).

**Sizing note:** replay DB and contextual memory JSONL stay under ``renaissance_v4/data/`` and
``renaissance_v4/game_theory/state/`` — unchanged by this module.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --- Thresholds (directive) ---
_TMP_WARN_FREE_BYTES = 500 * 1024 * 1024
_TMP_BLOCK_FREE_BYTES = 200 * 1024 * 1024
_RUNTIME_BLOCK_FREE_BYTES = 1024 * 1024 * 1024  # 1 GiB free on runtime filesystem → block
_RUNTIME_WARN_FREE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB → warn

_FLASK_LOG_MAX_BYTES = 100 * 1024 * 1024
_FLASK_LOG_BACKUP_COUNT = 5
_PROOF_LOG_MAX_BYTES = 200 * 1024 * 1024
_PROOF_LOG_BACKUP_COUNT = 1

_DEFAULT_BATCH_DIR_CAP = 120
_DEFAULT_BATCH_BYTES_CAP = 8 * 1024 * 1024 * 1024


def blackbox_repo_root() -> Path:
    return _REPO_ROOT


def pml_runtime_root() -> Path:
    """Resolved PML runtime root (``BLACKBOX_PML_RUNTIME_ROOT`` or ``<repo>/runtime``)."""
    ex = os.environ.get("BLACKBOX_PML_RUNTIME_ROOT", "").strip()
    if ex:
        return Path(ex).expanduser().resolve()
    return (_REPO_ROOT / "runtime").resolve()


def pml_runtime_logs_dir() -> Path:
    return pml_runtime_root() / "logs"


def pml_runtime_proofs_dir() -> Path:
    return pml_runtime_root() / "proofs"


def pml_runtime_batches_dir() -> Path:
    return pml_runtime_root() / "batches"


def telemetry_snapshots_dir() -> Path:
    """Live telemetry JSON snapshots (replaces default under system temp)."""
    return pml_runtime_logs_dir() / "pattern_game_telemetry"


def ensure_pml_runtime_dirs() -> None:
    for d in (
        pml_runtime_logs_dir(),
        telemetry_snapshots_dir(),
        pml_runtime_proofs_dir(),
        pml_runtime_batches_dir(),
    ):
        d.mkdir(parents=True, exist_ok=True)


def describe_pml_runtime_for_startup() -> str:
    root = pml_runtime_root()
    src = "BLACKBOX_PML_RUNTIME_ROOT" if os.environ.get("BLACKBOX_PML_RUNTIME_ROOT", "").strip() else "default <repo>/runtime"
    return (
        f"[pml_runtime] layout v1 — root={root} (from {src}); "
        f"logs={pml_runtime_logs_dir()}; proofs={pml_runtime_proofs_dir()}; batches={pml_runtime_batches_dir()}"
    )


def _free_bytes(path: Path) -> int:
    try:
        return int(shutil.disk_usage(str(path)).free)
    except OSError:
        return -1


def check_disk_before_run() -> tuple[bool, list[str], str | None]:
    """
    Pre-run guard. Returns ``(allowed, warnings, block_reason)``.
    ``block_reason`` is None when the run may proceed.
    """
    warnings: list[str] = []
    ensure_pml_runtime_dirs()
    rt = pml_runtime_root()
    tmp_free = _free_bytes(Path("/tmp"))
    rt_free = _free_bytes(rt)

    if tmp_free >= 0 and tmp_free < _TMP_BLOCK_FREE_BYTES:
        return (
            False,
            warnings,
            f"/tmp critically low: {tmp_free // (1024 * 1024)} MiB free (< {_TMP_BLOCK_FREE_BYTES // (1024 * 1024)} MiB) — refusing run.",
        )
    if tmp_free >= 0 and tmp_free < _TMP_WARN_FREE_BYTES:
        warnings.append(
            f"/tmp low: {tmp_free // (1024 * 1024)} MiB free (warn below {_TMP_WARN_FREE_BYTES // (1024 * 1024)} MiB)."
        )

    if rt_free >= 0 and rt_free < _RUNTIME_BLOCK_FREE_BYTES:
        return (
            False,
            warnings,
            f"PML runtime storage critically low on filesystem of {rt}: "
            f"{rt_free // (1024 * 1024)} MiB free (< {_RUNTIME_BLOCK_FREE_BYTES // (1024 * 1024)} MiB) — refusing run.",
        )
    if rt_free >= 0 and rt_free < _RUNTIME_WARN_FREE_BYTES:
        warnings.append(
            f"PML runtime volume low: {rt_free // (1024 * 1024)} MiB free "
            f"(recommend ≥ {_RUNTIME_WARN_FREE_BYTES // (1024 * 1024)} MiB headroom for logs/proofs/batches)."
        )

    return True, warnings, None


def runtime_status_snapshot() -> dict[str, object]:
    """Read-only fields for ``GET /api/capabilities``."""
    ensure_pml_runtime_dirs()
    root = pml_runtime_root()
    tmp_free = _free_bytes(Path("/tmp"))
    rt_free = _free_bytes(root)
    allowed, warnings, block_reason = check_disk_before_run()
    return {
        "pml_runtime_root": str(root),
        "pml_runtime_logs": str(pml_runtime_logs_dir()),
        "pml_runtime_proofs": str(pml_runtime_proofs_dir()),
        "pml_runtime_batches": str(pml_runtime_batches_dir()),
        "pml_tmp_free_bytes": tmp_free,
        "pml_runtime_free_bytes": rt_free,
        "pml_disk_run_allowed": allowed,
        "pml_disk_block_reason": block_reason,
        "pml_disk_warnings": warnings,
        "pml_flask_log_max_bytes": _FLASK_LOG_MAX_BYTES,
        "pml_flask_log_backup_count": _FLASK_LOG_BACKUP_COUNT,
        "pml_proof_log_max_bytes": _PROOF_LOG_MAX_BYTES,
    }


_logging_configured = False


def configure_web_server_file_logging() -> None:
    """
    Rotating Flask / Werkzeug file log (100 MiB × 5). Uses ``PATTERN_GAME_WEB_LOG_FILE`` env
    (set by ``pattern_game_remote_restart.sh`` or ``web_app`` ``main()`` default).
    """
    global _logging_configured
    if _logging_configured:
        return
    log_path = os.environ.get("PATTERN_GAME_WEB_LOG_FILE", "").strip()
    if not log_path:
        return
    p = Path(log_path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fh = logging.handlers.RotatingFileHandler(
        str(p),
        maxBytes=_FLASK_LOG_MAX_BYTES,
        backupCount=_FLASK_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    _logging_configured = True


def open_proof_rotating_log(stem: str) -> logging.Handler:
    """
    Proof / RCA capture: 200 MiB max, one backup. Attach to a logger, e.g.
    ``logging.getLogger("pml_proof").addHandler(open_proof_rotating_log("ctx_proof"))``.
    """
    ensure_pml_runtime_dirs()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)[:80] or "proof"
    path = pml_runtime_proofs_dir() / f"{safe}.log"
    return logging.handlers.RotatingFileHandler(
        str(path),
        maxBytes=_PROOF_LOG_MAX_BYTES,
        backupCount=_PROOF_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )


def _dir_total_bytes(path: Path) -> int:
    n = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    n += f.stat().st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return n


def prune_pml_runtime_batch_dirs() -> dict[str, int]:
    """
    Keep batch session folders bounded under ``runtime/batches/`` (mtime-newest first).
    Env: ``PML_RUNTIME_BATCH_MAX_DIRS`` (default 120), ``PML_RUNTIME_BATCH_MAX_BYTES`` (default 8 GiB).
    """
    ensure_pml_runtime_dirs()
    root = pml_runtime_batches_dir()
    max_dirs = int(os.environ.get("PML_RUNTIME_BATCH_MAX_DIRS", str(_DEFAULT_BATCH_DIR_CAP)))
    max_bytes = int(os.environ.get("PML_RUNTIME_BATCH_MAX_BYTES", str(_DEFAULT_BATCH_BYTES_CAP)))
    removed = 0
    freed = 0
    try:
        dirs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("batch_")]
    except OSError:
        return {"removed": 0, "freed_bytes": 0}

    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    total_bytes = sum(_dir_total_bytes(p) for p in dirs)

    while dirs and (len(dirs) > max_dirs or total_bytes > max_bytes):
        victim = dirs.pop()  # oldest among remaining
        try:
            b = _dir_total_bytes(victim)
            shutil.rmtree(victim, ignore_errors=True)
            removed += 1
            freed += b
            total_bytes -= b
        except OSError:
            break
    return {"removed": removed, "freed_bytes": freed}


def apply_main_process_runtime_env_defaults() -> None:
    """
    Called from ``web_app.main()`` before ``create_app()`` so worker subprocesses inherit
    non-``/tmp`` paths without requiring shell exports.
    """
    ensure_pml_runtime_dirs()
    rt = pml_runtime_root()
    os.environ.setdefault("PATTERN_GAME_WEB_LOG_FILE", str(rt / "logs" / "pattern_game_web.log"))
    os.environ.setdefault("PATTERN_GAME_TELEMETRY_DIR", str(rt / "logs" / "pattern_game_telemetry"))
    os.environ.setdefault("PATTERN_GAME_SESSION_LOGS_ROOT", str(rt / "batches"))
