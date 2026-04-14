"""
Auto-generated — DV-ARCH-POLICY-GENERATOR-022-C (generator_version='022-c-1').

Delegates full deterministic replay to ``renaissance_v4.research.replay_runner.run_manifest_replay``
using manifest: ``renaissance_v4/configs/manifests/candidate_robustness_compare.json``. Does not duplicate lifecycle or signal math.

``evaluate_jupiter_4_manifest_policy`` returns a Jupiter4-shaped result for mechanical tests;
authoritative Kitchen truth is ``replay_manifest_policy_checksum()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.jupiter_4_sean_policy import Jupiter4SeanPolicyResult

GENERATOR_VERSION = "022-c-1"
STRATEGY_ID = 'exp_candidate_compare_001'
MANIFEST_REL = 'renaissance_v4/configs/manifests/candidate_robustness_compare.json'
MANIFEST_HASH = '8b33dd012ad220eb6079f0318c71638ebf518e5822ee677f9a6540156922acdf'
REFERENCE_SOURCE = "policy_gen_022c:exp_candidate_compare_001"
CATALOG_ID = 'exp_candidate_compare_001'

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def manifest_path() -> Path:
    return (_REPO_ROOT / MANIFEST_REL).resolve()


def replay_manifest_policy_checksum() -> str:
    from renaissance_v4.research.replay_runner import run_manifest_replay

    out = run_manifest_replay(
        manifest_path=manifest_path(),
        emit_baseline_artifacts=False,
        verbose=False,
    )
    return str(out["validation_checksum"])


def evaluate_jupiter_4_manifest_policy(
    *,
    bars_asc: list[dict[str, Any]],
    free_collateral_usd: float | None = None,
    training_state: dict[str, Any] | None = None,
    ledger_db_path: Path | None = None,
) -> Jupiter4SeanPolicyResult:
    _ = (free_collateral_usd, training_state, ledger_db_path)
    return Jupiter4SeanPolicyResult(
        trade=False,
        side="flat",
        reason_code="kitchen_full_manifest_replay_required",
        pnl_usd=None,
        features={
            "reference": REFERENCE_SOURCE,
            "catalog_id": CATALOG_ID,
            "generator_version": GENERATOR_VERSION,
            "strategy_id": STRATEGY_ID,
            "manifest_path": str(manifest_path()),
            "manifest_hash": MANIFEST_HASH,
            "bars_asc_len": len(bars_asc),
        },
    )
