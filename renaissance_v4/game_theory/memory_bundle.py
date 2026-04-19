"""
memory_bundle.py — explicit “memory affects behavior” for deterministic replay.

A **memory bundle** is a small JSON file you promote from prior work. When provided, its
``apply`` block is merged into the manifest **before** the Referee runs — so stored knowledge
can change execution and **decision** thresholds (whitelisted keys only).

This is **opt-in**: no bundle path → no merge → behavior unchanged vs plain manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

MEMORY_BUNDLE_SCHEMA = "pattern_game_memory_bundle_v1"

# Whitelisted ``apply`` keys (governance: extend only with review). Values validated in
# :func:`_validate_apply_entry`.
BUNDLE_APPLY_WHITELIST: frozenset[str] = frozenset(
    {
        # Execution geometry (ExecutionManager)
        "atr_stop_mult",
        "atr_target_mult",
        # Fusion (``fuse_signal_results`` manifest overrides)
        "fusion_min_score",
        "fusion_max_conflict_score",
        "fusion_overlap_penalty_per_extra_signal",
        # Signal thresholds (``configure_from_manifest`` on each signal class)
        "mean_reversion_fade_min_confidence",
        "mean_reversion_fade_stretch_threshold",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
        # Policy: disable catalog signal modules for this run
        "disabled_signal_modules",
    }
)

# Back-compat alias for imports expecting a single frozenset name
ALLOWED_APPLY_KEYS: frozenset[str] = BUNDLE_APPLY_WHITELIST


def sha256_file(path: Path | str) -> str:
    """SHA-256 hex digest of file bytes (for operator audit)."""
    p = Path(path).expanduser().resolve()
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def categorize_applied_bundle_keys(keys: list[str]) -> dict[str, list[str]]:
    """Split applied keys for audit: execution / signal / fusion / policy."""
    execution: list[str] = []
    signal_k: list[str] = []
    fusion_k: list[str] = []
    policy_k: list[str] = []
    for k in keys:
        if k in ("atr_stop_mult", "atr_target_mult"):
            execution.append(k)
        elif k.startswith("fusion_"):
            fusion_k.append(k)
        elif k == "disabled_signal_modules":
            policy_k.append(k)
        elif k in BUNDLE_APPLY_WHITELIST:
            signal_k.append(k)
    return {
        "execution_keys_applied": execution,
        "signal_keys_applied": signal_k,
        "fusion_keys_applied": fusion_k,
        "policy_keys_applied": policy_k,
    }


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
    cat = (apply_audit or {}).get("categorized_keys") or categorize_applied_bundle_keys(keys)
    out: dict[str, Any] = {
        "memory_bundle_path": path_s,
        "memory_bundle_hash": digest,
        "memory_bundle_loaded": loaded,
        "memory_bundle_applied": applied,
        "memory_keys_applied": keys,
        "memory_bundle_apply_audit": apply_audit,
        "execution_keys_applied": cat.get("execution_keys_applied", []),
        "signal_keys_applied": cat.get("signal_keys_applied", []),
        "fusion_keys_applied": cat.get("fusion_keys_applied", []),
        "policy_keys_applied": cat.get("policy_keys_applied", []),
    }
    return out


def _validate_apply_entry(key: str, val: Any) -> Any:
    """Validate one apply value; return normalized value for manifest."""
    if key == "disabled_signal_modules":
        if not isinstance(val, list):
            raise ValueError("disabled_signal_modules must be a JSON array of strings")
        out = [str(x) for x in val]
        return out
    if key not in BUNDLE_APPLY_WHITELIST:
        raise ValueError(f"unknown bundle apply key: {key!r}")
    try:
        f = float(val)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{key} must be numeric") from e
    if key in ("atr_stop_mult", "atr_target_mult"):
        if not (0.5 <= f <= 6.0):
            raise ValueError(f"{key} must be in [0.5, 6.0], got {f}")
    elif key == "mean_reversion_fade_stretch_threshold":
        # Absolute price deviation fraction (same scale as code default 0.003)
        if not (0.000001 <= f <= 0.2):
            raise ValueError(f"{key} must be in [1e-6, 0.2], got {f}")
    elif key in (
        "fusion_min_score",
        "fusion_max_conflict_score",
        "mean_reversion_fade_min_confidence",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
    ):
        if not (0.0 <= f <= 1.0):
            raise ValueError(f"{key} must be in [0.0, 1.0], got {f}")
    elif key == "fusion_overlap_penalty_per_extra_signal":
        if not (0.0 <= f <= 1.0):
            raise ValueError(f"{key} must be in [0.0, 1.0], got {f}")
    return f


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
    snapshot: dict[str, Any] = {}

    for key, raw_val in apply_block.items():
        if raw_val is None:
            continue
        if key not in BUNDLE_APPLY_WHITELIST:
            raise ValueError(
                f"bundle apply key not whitelisted: {key!r}; allowed keys are from BUNDLE_APPLY_WHITELIST"
            )
        norm = _validate_apply_entry(key, raw_val)
        manifest[key] = norm
        applied.append(key)
        snapshot[key] = norm

    if not applied:
        return None

    categorized = categorize_applied_bundle_keys(applied)
    return {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "bundle_path": str(path_resolved) if path_resolved else None,
        "from_run_id": bundle.get("from_run_id"),
        "note": bundle.get("note"),
        "keys_applied": applied,
        "apply_snapshot": snapshot,
        "categorized_keys": categorized,
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
