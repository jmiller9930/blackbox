"""
Groundhog memory — **executable** continuity on the same tape.

Same bars + same manifest can repeat forever unless **something** changes execution.
A **memory bundle** (see ``memory_bundle.py``) merged before replay is that lever.

This module defines a **canonical bundle path** and helpers so promoted parameters can be
**re-applied** on the next run without hand-editing every scenario:

- **Write** ``groundhog_memory_bundle.json`` (schema ``pattern_game_memory_bundle_v1``).
- **Resolve** bundle path for a run: explicit ``memory_bundle_path`` on the scenario wins;
  else, when enabled, use the canonical file if it exists.

Enable auto-merge with::

    export PATTERN_GAME_GROUNDHOG_BUNDLE=1

Disable per scenario with ``"skip_groundhog_bundle": true`` in the scenario dict.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_bundle import MEMORY_BUNDLE_SCHEMA

_GAME_THEORY = Path(__file__).resolve().parent
GROUNDHOG_FILENAME = "groundhog_memory_bundle.json"


def groundhog_bundle_path() -> Path:
    """Canonical path under ``game_theory/state/`` (created on write)."""
    return _GAME_THEORY / "state" / GROUNDHOG_FILENAME


def groundhog_auto_merge_enabled() -> bool:
    v = os.environ.get("PATTERN_GAME_GROUNDHOG_BUNDLE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def resolve_memory_bundle_for_scenario(
    scenario: dict[str, Any] | None,
    *,
    explicit_path: str | None,
) -> str | None:
    """
    Return the memory bundle path to pass to ``apply_memory_bundle_to_manifest``.

    Precedence: explicit ``memory_bundle_path`` on scenario (or caller) **unless**
    ``skip_groundhog_bundle`` is truthy; else canonical Groundhog file when env enabled and file exists.
    """
    if scenario and scenario.get("skip_groundhog_bundle"):
        return explicit_path
    if explicit_path:
        return explicit_path
    if not groundhog_auto_merge_enabled():
        return None
    p = groundhog_bundle_path()
    return str(p) if p.is_file() else None


def write_groundhog_bundle(
    *,
    atr_stop_mult: float,
    atr_target_mult: float,
    from_run_id: str | None = None,
    note: str | None = None,
) -> Path:
    """Write or overwrite the canonical Groundhog bundle (whitelisted keys only)."""
    p = groundhog_bundle_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "from_run_id": from_run_id or "",
        "note": note
        or "Groundhog memory — merged before replay when PATTERN_GAME_GROUNDHOG_BUNDLE=1.",
        "apply": {
            "atr_stop_mult": float(atr_stop_mult),
            "atr_target_mult": float(atr_target_mult),
        },
    }
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def read_groundhog_bundle() -> dict[str, Any] | None:
    p = groundhog_bundle_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
