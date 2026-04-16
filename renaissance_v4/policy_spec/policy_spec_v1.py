"""
PolicySpecV1 — canonical internal policy schema (DV-ARCH-CANONICAL-POLICY-SPEC-046).

All normalized policies should map to this shape for Kitchen evaluation, documentation,
and future deployment metadata. This module defines the structure and validation helpers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class IdentitySpec:
    policy_id: str
    policy_family: str = ""
    version: str = "1"
    author: str = ""
    # training | candidate | baseline | production (validated at integration boundary)
    policy_class: str = "candidate"


@dataclass
class StrategySpec:
    timeframe: str = ""
    description: str = ""
    signal_type: str = "other"


@dataclass
class InputsSpec:
    required_data: list[str] = field(default_factory=list)
    indicators: list[str] = field(default_factory=list)
    external_sources: list[str] = field(default_factory=list)


@dataclass
class SignalLogicSpec:
    long_gate: str = ""
    short_gate: str = ""
    deterministic_only: bool = True


@dataclass
class RiskSizingSpec:
    risk_model: str = ""
    leverage_model: str = ""
    min_collateral: float | None = None


@dataclass
class ExitModelSpec:
    exit_type: str = ""
    tp_rules: str = ""
    sl_rules: str = ""
    trailing_enabled: bool = False
    breakeven_enabled: bool = False


@dataclass
class DiagnosticsContractSpec:
    required_outputs: list[str] = field(
        default_factory=lambda: ["signal", "confidence", "reason_code", "features"]
    )


@dataclass
class DeploymentMetadataSpec:
    target_system: str = "both"
    promotion_eligible: bool = False
    monte_carlo_bootstrap: bool = False


@dataclass
class IndicatorsSectionSpec:
    """
    DV-063: selective indicator declarations + optional gates.
    See ``renaissance_v4/policy_spec/indicators_v1.py`` for frozen vocabulary and validation.
    """

    schema_version: str = "policy_indicators_v1"
    declarations: list[dict[str, Any]] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""


@dataclass
class PolicySpecV1:
    """Canonical policy specification (internal)."""

    identity: IdentitySpec
    strategy: StrategySpec
    inputs: InputsSpec = field(default_factory=InputsSpec)
    signal_logic: SignalLogicSpec = field(default_factory=SignalLogicSpec)
    risk_sizing: RiskSizingSpec = field(default_factory=RiskSizingSpec)
    exit_model: ExitModelSpec = field(default_factory=ExitModelSpec)
    diagnostics_contract: DiagnosticsContractSpec = field(default_factory=DiagnosticsContractSpec)
    deployment_metadata: DeploymentMetadataSpec = field(default_factory=DeploymentMetadataSpec)
    indicators: IndicatorsSectionSpec = field(default_factory=IndicatorsSectionSpec)
    source_submission: dict[str, Any] = field(default_factory=dict)

    def to_canonical_dict(self) -> dict[str, Any]:
        """Return JSON-serializable nested dict."""
        return asdict(self)


def policy_spec_v1_validate_minimal(d: dict[str, Any]) -> list[str]:
    """Return list of validation errors (empty if OK)."""
    errs: list[str] = []
    ident = d.get("identity")
    if not isinstance(ident, dict):
        errs.append("missing identity")
        return errs
    if not str(ident.get("policy_id") or "").strip():
        errs.append("identity.policy_id required")
    return errs
