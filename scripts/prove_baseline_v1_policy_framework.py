#!/usr/bin/env python3
"""
Proof: baseline v1 policy framework is loadable, matches memory-bundle tunable whitelist,
preset scenarios attach audits, ATR sweep scenarios stay in-framework, operator run audit echoes identity.

Run from repo root:
  PYTHONPATH=. python3 scripts/prove_baseline_v1_policy_framework.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from renaissance_v4.game_theory.catalog_batch_builder import build_atr_sweep_scenarios  # noqa: E402
from renaissance_v4.game_theory.memory_bundle import BUNDLE_APPLY_WHITELIST  # noqa: E402
from renaissance_v4.game_theory.operator_recipes import build_scenarios_for_recipe, recipe_meta_by_id  # noqa: E402
from renaissance_v4.game_theory.policy_framework import (  # noqa: E402
    DEFAULT_BASELINE_POLICY_FRAMEWORK_REL,
    attach_policy_framework_audits,
    load_policy_framework,
    validate_policy_framework_v1,
)
from renaissance_v4.game_theory.hunter_planner import resolve_repo_root  # noqa: E402
from renaissance_v4.game_theory.run_memory import build_operator_run_audit  # noqa: E402
from renaissance_v4.game_theory.pml_proof_stdio import (  # noqa: E402
    add_proof_stdio_flags,
    begin_pml_proof_stdio,
    raw_stdout_selected,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_proof_stdio_flags(ap)
    args = ap.parse_args()
    begin_pml_proof_stdio("prove_baseline_v1_policy_framework", raw_stdout=raw_stdout_selected(args))

    root = resolve_repo_root(_REPO)
    meta = recipe_meta_by_id("pattern_learning")
    assert meta is not None
    assert meta.get("policy_framework_path") == DEFAULT_BASELINE_POLICY_FRAMEWORK_REL

    rel_fw = str(meta["policy_framework_path"])
    fw_abs = (root / rel_fw).resolve()
    doc = load_policy_framework(fw_abs)
    ok, msgs = validate_policy_framework_v1(doc, repo_root=root)
    if not ok:
        print("VALIDATION_FAILED", msgs)
        return 1

    tunable = (
        (doc.get("allowed_adaptations") or {}).get("tunable_surface") or {}
    ).get("memory_bundle_apply_keys")
    assert isinstance(tunable, list)
    assert set(tunable) == set(BUNDLE_APPLY_WHITELIST)
    print("OK tunable_surface matches BUNDLE_APPLY_WHITELIST")

    scenarios = build_scenarios_for_recipe("pattern_learning")
    for s in scenarios:
        s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())
    ok2, attach_msgs = attach_policy_framework_audits(scenarios)
    if not ok2:
        print("ATTACH_FAILED", attach_msgs)
        return 1
    audit = scenarios[0]["policy_framework_audit"]
    print("OK preset scenario audit:", json.dumps(audit, indent=2, sort_keys=True))

    manifest = str((root / "renaissance_v4/configs/manifests/baseline_v1_recipe.json").resolve())
    atr_batch = build_atr_sweep_scenarios(
        manifest,
        pairs=[(1.0, 3.0), (1.2, 3.5)],
        max_scenarios=2,
    )
    for s in atr_batch:
        s["policy_framework_path"] = rel_fw
        s["manifest_path"] = str(Path(s["manifest_path"]).expanduser().resolve())
    ok3, _ = attach_policy_framework_audits(atr_batch)
    if not ok3:
        print("ATR_ATTACH_FAILED")
        return 1
    print("OK atr_sweep scenarios in-framework:", len(atr_batch))

    op_aud = build_operator_run_audit(scenarios[0], {"replay_data_audit": None})
    assert op_aud.get("policy_framework_audit", {}).get("framework_id") == doc.get("framework_id")
    print("OK operator_run_audit echoes framework_id")

    print("PROOF_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
