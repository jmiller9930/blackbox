"""Execution target registry (DV-ARCH-KITCHEN-EXECUTION-TARGET-055)."""

from __future__ import annotations

import pytest

from renaissance_v4.execution_targets import (
    EXECUTION_BLACKBOX,
    EXECUTION_JUPITER,
    baseline_artifacts_present,
    normalize_execution_target,
    paths_for_execution_target,
)


def test_normalize_defaults_and_allowed() -> None:
    assert normalize_execution_target(None) == EXECUTION_JUPITER
    assert normalize_execution_target("") == EXECUTION_JUPITER
    assert normalize_execution_target("JuPiTeR") == EXECUTION_JUPITER
    assert normalize_execution_target("BLACKBOX") == EXECUTION_BLACKBOX


def test_normalize_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid_execution_target"):
        normalize_execution_target("solana")


def test_paths_jupiter_vs_blackbox_differ() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    pj = paths_for_execution_target(root, EXECUTION_JUPITER)
    pb = paths_for_execution_target(root, EXECUTION_BLACKBOX)
    assert pj["baseline_det"] != pb["baseline_det"]
    assert "blackbox_baseline" in pb["baseline_det"].name


def test_baseline_present_jupiter_uses_repo_state() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    ok, msg = baseline_artifacts_present(root, EXECUTION_JUPITER)
    assert isinstance(ok, bool)
    assert msg == "" or "No baseline" in msg
