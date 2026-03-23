"""Process-local kill switch persisted under data/runtime/execution_plane/."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _paths import repo_root


def _path() -> Path:
    return repo_root() / "data" / "runtime" / "execution_plane" / "kill_switch.json"


def _load() -> dict[str, Any]:
    p = _path()
    if not p.is_file():
        return {"active": False}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def enable() -> None:
    _save({"active": True})


def disable() -> None:
    _save({"active": False})


def is_active() -> bool:
    return bool(_load().get("active"))


def toggle() -> bool:
    """Return new active state."""
    n = not is_active()
    _save({"active": n})
    return n
