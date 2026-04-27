"""
RM preflight — thread context for Student seam early exit after first sealed trade.

Used only with :func:`learning_trace_memory_sink_session_v1` during bounded wiring validation.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_rm_preflight_early_exit_after_seal: ContextVar[bool] = ContextVar(
    "rm_preflight_early_exit_after_seal_v1", default=False
)


def rm_preflight_early_exit_after_seal_active_v1() -> bool:
    return _rm_preflight_early_exit_after_seal.get()


@contextmanager
def rm_preflight_seam_early_exit_session_v1() -> Iterator[None]:
    token = _rm_preflight_early_exit_after_seal.set(True)
    try:
        yield
    finally:
        _rm_preflight_early_exit_after_seal.reset(token)


__all__ = [
    "rm_preflight_early_exit_after_seal_active_v1",
    "rm_preflight_seam_early_exit_session_v1",
]
