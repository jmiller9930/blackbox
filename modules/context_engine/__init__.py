"""BLACK BOX context engine — operational storage, guards, and status (Pillar 1)."""

from modules.context_engine.paths import ContextPathError, resolve_context_root, validate_path_under_root
from modules.context_engine.store import append_event, read_recent_events
from modules.context_engine.status import build_context_engine_status, record_api_probe

__all__ = [
    "ContextPathError",
    "append_event",
    "build_context_engine_status",
    "read_recent_events",
    "record_api_probe",
    "resolve_context_root",
    "validate_path_under_root",
]
