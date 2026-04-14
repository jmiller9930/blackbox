"""
RenaissanceV4 baseline manifest — policy package shell (DV-ARCH-POLICY-GENERATOR-022-B).

This module does **not** reimplement signals, fusion, risk, or execution. Full deterministic
replay and ``[VALIDATION_CHECKSUM]`` use the same code path as ``replay_runner``:
``run_manifest_replay`` with ``renaissance_v4/configs/manifests/baseline_v1_recipe.json``.

BlackBox-style ``evaluate_jupiter_*`` is a **research placeholder**: Kitchen authoritative
truth is the full bar replay above; single-bar evaluation cannot carry execution state
without the ledger bridge. See README.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.jupiter_4_sean_policy import Jupiter4SeanPolicyResult

REFERENCE_SOURCE = "jupiter_4_renaissance_baseline_v1_policy:022b"
CATALOG_ID = "renaissance_baseline_v1_kitchen_manifest"
POLICY_ENGINE_ID = "renaissance_kitchen_v1"

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BASELINE_MANIFEST = _REPO_ROOT / "renaissance_v4" / "configs" / "manifests" / "baseline_v1_recipe.json"


def baseline_manifest_path() -> Path:
    """Resolved path to the baseline strategy manifest this package was emitted from."""
    return _BASELINE_MANIFEST.resolve()


def replay_baseline_v1_checksum() -> str:
    """
    Run the authoritative manifest-driven replay (same engine as ``replay_runner``) and
    return ``validation_checksum`` — use for parity vs ``python -m renaissance_v4.research.replay_runner``.
    """
    from renaissance_v4.research.replay_runner import run_manifest_replay

    out = run_manifest_replay(
        manifest_path=baseline_manifest_path(),
        emit_baseline_artifacts=False,
        verbose=False,
    )
    return str(out["validation_checksum"])


def evaluate_jupiter_4_renaissance_baseline_v1(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> Jupiter4SeanPolicyResult:
    """
    Jupiter4-shaped result object for mechanical integration tests.

    **022-B:** Does not run the full Renaissance execution simulation on one tick.
    Use :func:`replay_baseline_v1_checksum` for deterministic parity vs Kitchen replay.
    """
    _ = (free_collateral_usd, training_state, ledger_db_path)
    return Jupiter4SeanPolicyResult(
        trade=False,
        side="flat",
        reason_code="kitchen_full_manifest_replay_required",
        pnl_usd=None,
        features={
            "reference": REFERENCE_SOURCE,
            "catalog_id": CATALOG_ID,
            "policy_engine": POLICY_ENGINE_ID,
            "manifest_path": str(baseline_manifest_path()),
            "bars_asc_len": len(bars_asc),
            "note": "Parity vs replay_runner: call replay_baseline_v1_checksum() or run replay_runner module.",
        },
    )
