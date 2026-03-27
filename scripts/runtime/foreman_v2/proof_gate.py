from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProofCheck:
    has_proof: bool
    developer_handoff_back: bool
    reason: str


def check_proof_and_handoff(shared_log_text: str) -> ProofCheck:
    lower = shared_log_text.lower()
    proof_markers = (
        "implementation proof",
        "tests",
        "commands",
    )
    has_proof = all(marker in lower for marker in proof_markers)
    developer_handoff_back = "have the architect validate shared-docs" in lower
    if not has_proof:
        return ProofCheck(False, developer_handoff_back, "proof_missing")
    if not developer_handoff_back:
        return ProofCheck(True, False, "proof_present_handoff_missing")
    return ProofCheck(True, True, "proof_and_handoff_present")

