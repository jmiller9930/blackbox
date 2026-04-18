"""Memory bundle merge affects manifest before replay (audit + whitelist)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from renaissance_v4.game_theory.memory_bundle import (
    MEMORY_BUNDLE_SCHEMA,
    apply_memory_bundle_to_manifest,
    load_memory_bundle,
)


def test_apply_memory_bundle_merges_atr() -> None:
    manifest = {"atr_stop_mult": 1.0, "atr_target_mult": 2.0, "id": "x"}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "m.json"
        p.write_text(
            json.dumps(
                {
                    "schema": MEMORY_BUNDLE_SCHEMA,
                    "apply": {"atr_stop_mult": 1.78, "atr_target_mult": 3.35},
                }
            ),
            encoding="utf-8",
        )
        audit = apply_memory_bundle_to_manifest(manifest, str(p))
        assert audit is not None
        assert manifest["atr_stop_mult"] == 1.78
        assert manifest["atr_target_mult"] == 3.35
        assert "atr_stop_mult" in audit["keys_applied"]


def test_load_memory_bundle_schema() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "b.json"
        p.write_text(
            json.dumps({"schema": MEMORY_BUNDLE_SCHEMA, "apply": {}}),
            encoding="utf-8",
        )
        b = load_memory_bundle(p)
        assert b["schema"] == MEMORY_BUNDLE_SCHEMA
