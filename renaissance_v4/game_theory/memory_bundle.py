"""
memory_bundle.py — explicit “memory affects behavior” for deterministic replay.

A **memory bundle** is a small JSON file you promote from prior work. When provided, its
``apply`` block is merged into the manifest **before** the Referee runs — so stored knowledge
can change execution (ATR geometry first; extend keys deliberately).

This is **opt-in**: no bundle path → no merge → behavior unchanged vs plain manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

MEMORY_BUNDLE_SCHEMA = "pattern_game_memory_bundle_v1"

# Only whitelisted manifest keys may be applied from memory (extend with governance review).
ALLOWED_APPLY_KEYS: frozenset[str] = frozenset({"atr_stop_mult", "atr_target_mult"})


def sha256_file(path: Path | str) -> str:
    """SHA-256 hex digest of file bytes (for operator audit)."""
    p = Path(path).expanduser().resolve()
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_memory_bundle_proof(
    *,
    resolved_bundle_path: str | None,
    apply_audit: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Flattened audit for runs and APIs: loaded vs applied vs hash.

    * ``memory_bundle_loaded`` — a bundle file path was resolved **and** the file exists on disk.
    * ``memory_bundle_applied`` — at least one whitelisted key was merged into the manifest.
    """
    path_s = (resolved_bundle_path or "").strip() or None
    loaded = False
    digest: str | None = None
    if path_s:
        p = Path(path_s).expanduser().resolve()
        if p.is_file():
            loaded = True
            digest = sha256_file(p)
    applied = apply_audit is not None
    keys = list((apply_audit or {}).get("keys_applied") or [])
    return {
        "memory_bundle_path": path_s,
        "memory_bundle_hash": digest,
        "memory_bundle_loaded": loaded,
        "memory_bundle_applied": applied,
        "memory_keys_applied": keys,
        "memory_bundle_apply_audit": apply_audit,
    }


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
