"""Unit tests for memory bundle audit helpers (directive: observable proof fields)."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.memory_bundle import (
    MEMORY_BUNDLE_SCHEMA,
    apply_memory_bundle_to_manifest,
    build_memory_bundle_proof,
    sha256_file,
)


def test_sha256_file_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "b.json"
    p.write_text('{"x":1}', encoding="utf-8")
    h = sha256_file(p)
    assert len(h) == 64
    assert h == sha256_file(p)


def test_build_memory_bundle_proof_no_path() -> None:
    d = build_memory_bundle_proof(resolved_bundle_path=None, apply_audit=None)
    assert d["memory_bundle_loaded"] is False
    assert d["memory_bundle_applied"] is False
    assert d["memory_bundle_hash"] is None
    assert d["memory_keys_applied"] == []


def test_build_memory_bundle_proof_with_apply(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    doc = {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "apply": {"atr_stop_mult": 2.0, "atr_target_mult": 3.0},
    }
    p.write_text(json.dumps(doc), encoding="utf-8")
    audit = {
        "keys_applied": ["atr_stop_mult", "atr_target_mult"],
        "apply_snapshot": {"atr_stop_mult": 2.0, "atr_target_mult": 3.0},
    }
    d = build_memory_bundle_proof(resolved_bundle_path=str(p), apply_audit=audit)
    assert d["memory_bundle_loaded"] is True
    assert d["memory_bundle_applied"] is True
    assert d["memory_bundle_hash"] == sha256_file(p)
    assert set(d["memory_keys_applied"]) == {"atr_stop_mult", "atr_target_mult"}
    assert d["execution_keys_applied"] == ["atr_stop_mult", "atr_target_mult"]
    assert d["signal_keys_applied"] == []
    assert d["fusion_keys_applied"] == []


def test_apply_memory_bundle_fusion_and_policy() -> None:
    m: dict = {
        "schema": "strategy_manifest_v1",
        "manifest_version": "1.0",
        "signal_modules": ["mean_reversion_fade", "trend_continuation"],
    }
    bundle = {
        "schema": MEMORY_BUNDLE_SCHEMA,
        "apply": {
            "fusion_min_score": 0.1,
            "disabled_signal_modules": ["trend_continuation"],
        },
    }
    audit = apply_memory_bundle_to_manifest(m, bundle_dict=bundle)
    assert audit is not None
    assert m["fusion_min_score"] == 0.1
    assert m["disabled_signal_modules"] == ["trend_continuation"]
    cat = audit["categorized_keys"]
    assert cat["fusion_keys_applied"] == ["fusion_min_score"]
    assert cat["policy_keys_applied"] == ["disabled_signal_modules"]
