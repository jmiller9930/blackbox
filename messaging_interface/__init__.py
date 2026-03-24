"""Directive 4.6.3.3 — messaging transport abstraction (Anna pipeline boundary)."""

from messaging_interface.normalized import normalized_from_payload
from messaging_interface.pipeline import run_dispatch_pipeline

__all__ = [
    "normalized_from_payload",
    "run_dispatch_pipeline",
]
