"""
Controlled stdio for **PML proof / RCA / validation** scripts.

Default: stdout/stderr are captured to a **rotating** log under ``runtime/proofs/`` (or
``$BLACKBOX_PML_RUNTIME_ROOT/proofs/``) — never ``/tmp`` or ad hoc ``*.out``.

Operator-facing summaries and machine-readable **final JSON** go to the real terminal via
``proof_console`` / ``proof_json_out`` so piping (e.g. ``| jq``) still works while replay noise
stays off the console.

Opt-in unbounded console: ``--raw-stdout``, ``--verbose``, or ``--debug`` (all equivalent).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterator, TextIO

_REAL_OUT: TextIO = sys.__stdout__
_REAL_ERR: TextIO = sys.__stderr__

_stdio_locked = False
_active_log_path: Path | None = None


class _StreamToLogger:
    """Line-buffered write stream → ``logging.Logger`` (bounded by rotating handler on logger)."""

    def __init__(self, logger: logging.Logger, level: int) -> None:
        self._logger = logger
        self._level = level
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._logger.log(self._level, line.rstrip())
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            self._logger.log(self._level, self._buf.rstrip())
            self._buf = ""

    def isatty(self) -> bool:
        return False


def add_proof_stdio_flags(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group(
        "PML proof output (default: capture to runtime/proofs/*.log; compact on console)"
    )
    g.add_argument(
        "--raw-stdout",
        action="store_true",
        help="Send full stdout/stderr to the terminal (unbounded; risks filling tmpfs if redirected to /tmp).",
    )
    g.add_argument("--verbose", action="store_true", help="Alias of --raw-stdout.")
    g.add_argument("--debug", action="store_true", help="Alias of --raw-stdout.")


def raw_stdout_selected(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "raw_stdout", False)
        or getattr(args, "verbose", False)
        or getattr(args, "debug", False)
    )


def proof_console(*args: object, **kwargs: Any) -> None:
    """Print to the **real** stdout (operator-visible), regardless of stdio capture."""
    kwargs.setdefault("file", _REAL_OUT)
    print(*args, **kwargs)


def proof_json_out(obj: Any, *, indent: int | None = 2, **kwargs: Any) -> None:
    """Emit final JSON artifact on the **real** stdout (for piping / CI)."""
    kwargs.setdefault("default", str)
    _REAL_OUT.write(json.dumps(obj, indent=indent, ensure_ascii=False, **kwargs) + "\n")
    _REAL_OUT.flush()


def begin_pml_proof_stdio(script_stem: str, *, raw_stdout: bool) -> Path:
    """
    Call immediately after ``parse_args()`` in proof/RCA scripts.

    When ``raw_stdout`` is False, replaces ``sys.stdout``/``sys.stderr`` with loggers writing
    to a rotating file under ``runtime/proofs/<stem>.log``.
    """
    global _stdio_locked, _active_log_path
    from renaissance_v4.game_theory.pml_runtime_layout import (
        ensure_pml_runtime_dirs,
        open_proof_rotating_log,
        proof_rotating_log_path,
    )

    ensure_pml_runtime_dirs()
    path = proof_rotating_log_path(script_stem)
    _active_log_path = path

    if raw_stdout:
        _REAL_OUT.write(
            f"[pml_proof] {script_stem}: raw console enabled — use runtime proof log only if you add one explicitly.\n"
        )
        _REAL_OUT.flush()
        return path

    if _stdio_locked:
        return path
    _stdio_locked = True

    h = open_proof_rotating_log(script_stem)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    lg_out = logging.getLogger(f"pml_proof.{script_stem}.stdout")
    lg_out.setLevel(logging.INFO)
    lg_out.handlers.clear()
    lg_out.addHandler(h)
    lg_out.propagate = False

    lg_err = logging.getLogger(f"pml_proof.{script_stem}.stderr")
    lg_err.setLevel(logging.WARNING)
    lg_err.handlers.clear()
    lg_err.addHandler(h)
    lg_err.propagate = False

    sys.stdout = _StreamToLogger(lg_out, logging.INFO)  # type: ignore[assignment]
    sys.stderr = _StreamToLogger(lg_err, logging.WARNING)  # type: ignore[assignment]

    proof_console(f"[pml_proof] {script_stem}: stdout/stderr -> {path} (rotating, max 200MB); final JSON via proof_json_out(); --raw-stdout for full console.")
    return path


def active_proof_log_path() -> Path | None:
    return _active_log_path


@contextlib.contextmanager
def replay_stdout_muted(*, raw_stdout: bool) -> Iterator[None]:
    """Mute per-bar replay spam unless ``raw_stdout`` (opt-in verbose console)."""
    if raw_stdout:
        yield
        return
    import os

    saved = sys.stdout
    dev = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = dev  # type: ignore[assignment]
    try:
        yield
    finally:
        sys.stdout = saved
        dev.close()
