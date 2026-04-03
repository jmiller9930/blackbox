"""Anna training runtime — curriculum assignment, method invocation, operator-visible state (CLI)."""

from __future__ import annotations

from modules.anna_training.catalog import (
    CURRICULA,
    TRAINING_METHODS,
    default_state,
    describe_catalog,
)
from modules.anna_training.store import (
    STATE_FILE_NAME,
    anna_training_dir,
    load_state,
    save_state,
)

__all__ = [
    "CURRICULA",
    "TRAINING_METHODS",
    "STATE_FILE_NAME",
    "anna_training_dir",
    "default_state",
    "describe_catalog",
    "load_state",
    "save_state",
]
