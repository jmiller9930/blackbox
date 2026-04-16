"""
normalize_policy(input_policy) → PolicySpecV1-shaped dict.

DV-ARCH-CANONICAL-POLICY-SPEC-046: backend-owned normalization; submitters keep
POLICY_SPEC.yaml / Sean-style packages; we map into one canonical schema.
"""

from __future__ import annotations

import copy
from typing import Any

from renaissance_v4.policy_spec.policy_spec_v1 import (
    DeploymentMetadataSpec,
    DiagnosticsContractSpec,
    ExitModelSpec,
    IdentitySpec,
    InputsSpec,
    PolicySpecV1,
    RiskSizingSpec,
    SignalLogicSpec,
    StrategySpec,
)


def normalize_policy(input_policy: Any) -> dict[str, Any]:
    """
    Normalize a submitted policy (dict) to PolicySpecV1.

    Supported:
    - POLICY_SPEC.yaml top-level (policy_package_version + policy + inputs + …)
    - Loose dict with ``policy_id`` or ``id`` at top level
    """
    if input_policy is None:
        raise ValueError("input_policy is required")
    if isinstance(input_policy, PolicySpecV1):
        return input_policy.to_canonical_dict()
    if not isinstance(input_policy, dict):
        raise TypeError("normalize_policy expects dict or PolicySpecV1")

    if "policy" in input_policy and isinstance(input_policy["policy"], dict):
        return _from_policy_package_v1(input_policy)
    return _from_loose_dict(input_policy)


def _from_policy_package_v1(data: dict[str, Any]) -> dict[str, Any]:
    pol = copy.deepcopy(data.get("policy") or {})
    pid = str(pol.get("id") or pol.get("catalog_id") or "").strip() or "unknown"
    slot = str(pol.get("baseline_policy_slot") or "")
    sig_mode = str(pol.get("signal_mode") or "")
    tf = str(pol.get("timeframe") or "")
    inst = str(pol.get("instrument") or "")

    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        inputs = {}

    canonical_inputs = inputs.get("canonical")
    req_data: list[str] = ["ohlcv"]
    if isinstance(canonical_inputs, str) and canonical_inputs:
        req_data = [canonical_inputs]

    pclass = "baseline" if "baseline" in slot.lower() or "baseline" in pid.lower() else "candidate"
    if "training" in pid.lower() or "proof" in pid.lower():
        pclass = "training"

    ident = IdentitySpec(
        policy_id=pid,
        policy_family=str(pol.get("display_name") or pid)[:256],
        version=str(data.get("policy_package_version") or pol.get("version") or "1"),
        author=str(data.get("generator_version") or pol.get("author") or "package"),
        policy_class=_coerce_policy_class(pclass),
    )
    strategy = StrategySpec(
        timeframe=tf,
        description=str(pol.get("display_name") or ""),
        signal_type=_infer_signal_type(sig_mode, pid),
    )
    inp = InputsSpec(
        required_data=req_data,
        indicators=[],
        external_sources=[],
    )
    gates = data.get("gates")
    long_g = short_g = ""
    if isinstance(gates, list) and gates:
        long_g = short_g = f"{len(gates)} gate(s) from POLICY_SPEC; see package"
    sig_logic = SignalLogicSpec(long_gate=long_g, short_gate=short_g, deterministic_only=True)

    # Parity / module hints stay in source_submission for auditors
    extra = {
        "policy_package_version": data.get("policy_package_version"),
        "parity": data.get("parity"),
        "constants": data.get("constants"),
    }

    spec = PolicySpecV1(
        identity=ident,
        strategy=strategy,
        inputs=inp,
        signal_logic=sig_logic,
        risk_sizing=RiskSizingSpec(),
        exit_model=ExitModelSpec(exit_type="lifecycle_default", tp_rules="", sl_rules=""),
        diagnostics_contract=DiagnosticsContractSpec(),
        deployment_metadata=DeploymentMetadataSpec(
            target_system="both",
            promotion_eligible=False,
            monte_carlo_bootstrap=True,
        ),
        source_submission={"instrument": inst, "raw_policy": pol, "extra": extra},
    )
    return spec.to_canonical_dict()


def _coerce_policy_class(raw: Any) -> str:
    allowed = frozenset({"training", "candidate", "baseline", "production"})
    s = str(raw or "candidate").strip().lower()
    return s if s in allowed else "candidate"


def _from_loose_dict(data: dict[str, Any]) -> dict[str, Any]:
    pid = str(data.get("policy_id") or data.get("id") or "unknown").strip()
    ident = IdentitySpec(
        policy_id=pid,
        policy_family=str(data.get("policy_family") or ""),
        version=str(data.get("version") or "1"),
        author=str(data.get("author") or ""),
        policy_class=_coerce_policy_class(data.get("policy_class")),
    )
    strategy = StrategySpec(
        timeframe=str(data.get("timeframe") or ""),
        description=str(data.get("description") or ""),
        signal_type=_infer_signal_type("", pid),
    )
    spec = PolicySpecV1(
        identity=ident,
        strategy=strategy,
        inputs=InputsSpec(),
        signal_logic=SignalLogicSpec(),
        risk_sizing=RiskSizingSpec(),
        exit_model=ExitModelSpec(),
        diagnostics_contract=DiagnosticsContractSpec(),
        deployment_metadata=DeploymentMetadataSpec(),
        source_submission={"raw": data},
    )
    return spec.to_canonical_dict()


def _infer_signal_type(signal_mode: str, policy_id: str) -> Any:
    sm = (signal_mode + " " + policy_id).lower()
    if "divergence" in sm:
        return "divergence"
    if "momentum" in sm or "momentum" in policy_id.lower():
        return "momentum"
    if "pipeline_proof" in sm or "pipeline_proof" in policy_id.lower():
        return "pipeline_proof"
    if "mean" in sm or "fade" in sm:
        return "mean_reversion"
    return "trend"

