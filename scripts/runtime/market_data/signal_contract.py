"""Participant / tier-aware signal contract foundation (Phase 5.1). Anna does not assign tiers."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class SignalContractV1:
    """Required fields per development_plan §5.0 — operator-owned risk_tier."""

    participant_id: str
    participant_type: str
    account_id: str
    wallet_context: str
    risk_tier: str
    interaction_path: str
    market_symbol: str | None = None
    schema_version: str = "signal_contract_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_signal_contract(obj: SignalContractV1) -> None:
    missing = [
        name
        for name in (
            "participant_id",
            "participant_type",
            "account_id",
            "wallet_context",
            "risk_tier",
            "interaction_path",
        )
        if not str(getattr(obj, name, "") or "").strip()
    ]
    if missing:
        raise ValueError(f"signal_contract_missing_fields:{','.join(missing)}")
