"""Unit tests for memory bundle audit helpers (directive: observable proof fields)."""

from __future__ import annotations

import json
from pathlib import Path

from renaissance_v4.game_theory.memory_bundle import (
    MEMORY_BUNDLE_SCHEMA,
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
