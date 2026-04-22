"""
Groundhog memory — **executable** continuity on the same tape.

Same bars + same manifest can repeat forever unless **something** changes execution.
A **memory bundle** (see ``memory_bundle.py``) merged before replay is that lever.

This module defines a **canonical bundle path** and helpers so promoted parameters can be
**re-applied** on the next run without hand-editing every scenario:

- **Write** ``groundhog_memory_bundle.json`` (schema ``pattern_game_memory_bundle_v1``).
- **Resolve** bundle path for a run: explicit ``memory_bundle_path`` on the scenario wins;
  else use the **canonical container** (``groundhog_memory_bundle.json``) whenever it exists.

**Auto-merge is ON by default** (no operator “arm” step). Opt out only with::

    export PATTERN_GAME_GROUNDHOG_BUNDLE=0

Disable per scenario with ``"skip_groundhog_bundle": true`` in the scenario dict.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Literal

from renaissance_v4.game_theory.memory_bundle import MEMORY_BUNDLE_SCHEMA

_GAME_THEORY = Path(__file__).resolve().parent
GROUNDHOG_FILENAME = "groundhog_memory_bundle.json"


def groundhog_bundle_path() -> Path:
    """Canonical path under ``game_theory/state/`` (created on write)."""
    return _GAME_THEORY / "state" / GROUNDHOG_FILENAME


def groundhog_auto_merge_enabled() -> bool:
    """
    Canonical Groundhog container merge is **active by default**.

    Set ``PATTERN_GAME_GROUNDHOG_BUNDLE`` to ``0`` / ``false`` / ``no`` / ``off`` to disable
    auto-resolve for tests or emergency isolation.
    """
    v = os.environ.get("PATTERN_GAME_GROUNDHOG_BUNDLE", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def resolve_memory_bundle_for_scenario(
    scenario: dict[str, Any] | None,
    *,
    explicit_path: str | None,
) -> str | None:
    """
    Return the memory bundle path to pass to ``apply_memory_bundle_to_manifest``.

    Precedence: explicit ``memory_bundle_path`` on scenario (or caller) **unless**
    ``skip_groundhog_bundle`` is truthy; else canonical Groundhog file when auto-merge is not
    explicitly disabled and the file exists.
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
        or "Groundhog memory — canonical container merged before replay when present (auto-merge on by default).",
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


def _groundhog_apply_has_promoted_atr(doc: dict[str, Any]) -> bool:
    """True when ``apply`` carries finite ATR multipliers (canonical promoted bundle)."""
    app = doc.get("apply")
    if not isinstance(app, dict):
        return False
    try:
        s = float(app.get("atr_stop_mult", float("nan")))
        t = float(app.get("atr_target_mult", float("nan")))
    except (TypeError, ValueError):
        return False
    return math.isfinite(s) and math.isfinite(t)


def groundhog_wiring_signal() -> tuple[Literal["green", "yellow", "red"], str]:
    """
    Tri-state wiring for the module board:

    - **green** — auto-merge active and the canonical file exists with a valid promoted ``apply`` block.
    - **yellow** — auto-merge **opt-out** (``PATTERN_GAME_GROUNDHOG_BUNDLE=0``), or active but bundle
      file not created yet, or file not yet a full promoted bundle (wrong schema or empty ``apply``).
    - **red** — **read/parse fails**, or JSON is not an object (broken file).
    """
    env = groundhog_auto_merge_enabled()
    p = groundhog_bundle_path()

    if not env:
        return (
            "yellow",
            "Groundhog auto-merge **opt-out** (PATTERN_GAME_GROUNDHOG_BUNDLE=0) — canonical container not merged.",
        )

    if not p.is_file():
        return (
            "yellow",
            f"Canonical Groundhog container not created yet at {p}. POST /api/groundhog-memory to promote (idle).",
        )

    try:
        raw = p.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except OSError as e:
        return "red", f"Cannot read bundle file: {e}"[:220]
    except json.JSONDecodeError as e:
        return "red", f"Bundle is not valid JSON: {e}"[:220]

    if not isinstance(doc, dict):
        return "red", "Bundle JSON is not an object — container is unusable."

    if doc.get("schema") != MEMORY_BUNDLE_SCHEMA:
        return (
            "yellow",
            "Container exists but schema is not pattern_game_memory_bundle_v1 — republish via POST /api/groundhog-memory.",
        )

    if not _groundhog_apply_has_promoted_atr(doc):
        return (
            "yellow",
            "Container on disk — waiting for promoted atr_stop_mult / atr_target_mult in apply (POST promote).",
        )

    return (
        "green",
        "Groundhog ready: canonical container has promoted ATR multipliers (auto-merge active).",
    )
