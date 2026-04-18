"""
memory_bundle.py — explicit “memory affects behavior” for deterministic replay.

A **memory bundle** is a small JSON file you promote from prior work. When provided, its
``apply`` block is merged into the manifest **before** the Referee runs — so stored knowledge
can change execution (ATR geometry first; extend keys deliberately).

This is **opt-in**: no bundle path → no merge → behavior unchanged vs plain manifest.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MEMORY_BUNDLE_SCHEMA = "pattern_game_memory_bundle_v1"

# Only whitelisted manifest keys may be applied from memory (extend with governance review).
ALLOWED_APPLY_KEYS: frozenset[str] = frozenset({"atr_stop_mult", "atr_target_mult"})


def load_memory_bundle(path: Path | str) -> dict[str, Any]:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(f"memory bundle not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    sch = raw.get("schema")
    if sch != MEMORY_BUNDLE_SCHEMA:
        raise ValueError(
            f"memory bundle schema must be {MEMORY_BUNDLE_SCHEMA!r}, got {sch!r} ({p})"
        )
    if not isinstance(raw.get("apply"), dict):
        raise ValueError(f"memory bundle missing apply object: {p}")
    return raw


def apply_memory_bundle_to_manifest(
    manifest: dict[str, Any],
    bundle_path: str | Path | None = None,
    *,
    bundle_dict: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Merge ``apply`` keys from bundle into ``manifest`` (mutates manifest).

    Returns an audit dict for :func:`renaissance_v4.game_theory.run_memory.build_decision_audit`,
    or ``None`` if nothing was applied.
    """
    path_resolved: Path | None = None
    if bundle_dict is not None:
        bundle = bundle_dict
    else:
        p = bundle_path or os.environ.get("PATTERN_GAME_MEMORY_BUNDLE", "").strip() or None
        if not p:
            return None
        path_resolved = Path(p).expanduser().resolve()
        bundle = load_memory_bundle(path_resolved)

    apply_block = bundle.get("apply") or {}
    applied: list[str] = []
    for key in ALLOWED_APPLY_KEYS:
        if key not in apply_block:
            continue
        val = apply_block[key]
        if val is None:
            continue
        manifest[key] = float(val)
        applied.append(key)

    if not applied:
        return None

    return {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "bundle_path": str(path_resolved) if path_resolved else None,
        "from_run_id": bundle.get("from_run_id"),
        "note": bundle.get("note"),
        "keys_applied": applied,
        "apply_snapshot": {k: apply_block[k] for k in applied},
    }


def memory_bundle_required_and_missing(explicit_path: str | Path | None) -> bool:
    """True when env demands a bundle but neither CLI nor PATTERN_GAME_MEMORY_BUNDLE is set."""
    req = os.environ.get("PATTERN_GAME_REQUIRE_MEMORY_BUNDLE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if not req:
        return False
    p = (str(explicit_path).strip() if explicit_path else "") or os.environ.get(
        "PATTERN_GAME_MEMORY_BUNDLE", ""
    ).strip()
    return not p
