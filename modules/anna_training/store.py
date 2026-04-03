"""Filesystem state for Anna training (gitignored JSON under data/runtime/)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.anna_training.catalog import default_state

STATE_FILE_NAME = "state.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def anna_training_dir() -> Path:
    env = os.environ.get("BLACKBOX_ANNA_TRAINING_DIR")
    if env:
        return Path(env).expanduser()
    return _repo_root() / "data" / "runtime" / "anna_training"


def state_path() -> Path:
    return anna_training_dir() / STATE_FILE_NAME


def load_state() -> dict[str, Any]:
    p = state_path()
    if not p.is_file():
        return default_state()
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return default_state()
    base = default_state()
    base.update(raw)
    # Forward-compat: fill new keys from default without clobbering migrated data.
    for k, v in default_state().items():
        if k not in base:
            base[k] = v
    return base


def save_state(state: dict[str, Any]) -> None:
    from modules.anna_training.internalized_knowledge import maybe_grade12_internalize

    maybe_grade12_internalize(state)
    d = anna_training_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (STATE_FILE_NAME + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(state_path())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
