from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProofCheck:
    has_proof: bool
    developer_handoff_back: bool
    architect_verdict: str
    architect_rejection_count: int
    architect_outcome: str
    reason: str


def check_proof_and_handoff(shared_log_text: str) -> ProofCheck:
    scoped_text = _latest_directive_scope(shared_log_text)
    lower = scoped_text.lower()
    proof_markers = (
        "implementation proof",
        "tests",
        "commands",
    )
    has_proof = all(marker in lower for marker in proof_markers)
    developer_handoff_back = "have the architect validate shared-docs" in lower
    architect_verdict = _parse_architect_verdict(scoped_text)
    architect_rejection_count = _count_architect_not_met(scoped_text)
    architect_outcome = _parse_architect_outcome(scoped_text)
    if architect_verdict == "not_met":
        return ProofCheck(
            has_proof,
            developer_handoff_back,
            architect_verdict,
            architect_rejection_count,
            architect_outcome,
            "architect_not_met",
        )
    if architect_verdict == "met":
        return ProofCheck(
            has_proof,
            developer_handoff_back,
            architect_verdict,
            architect_rejection_count,
            architect_outcome,
            "architect_met",
        )
    if not has_proof:
        return ProofCheck(
            False,
            developer_handoff_back,
            architect_verdict,
            architect_rejection_count,
            architect_outcome,
            "proof_missing",
        )
    if not developer_handoff_back:
        return ProofCheck(
            True,
            False,
            architect_verdict,
            architect_rejection_count,
            architect_outcome,
            "proof_present_handoff_missing",
        )
    return ProofCheck(
        True,
        True,
        architect_verdict,
        architect_rejection_count,
        architect_outcome,
        "proof_and_handoff_present",
    )


def _latest_directive_scope(shared_log_text: str) -> str:
    marker = "directive_context:"
    lower = shared_log_text.lower()
    idx = lower.rfind(marker)
    if idx == -1:
        return shared_log_text
    return shared_log_text[idx:]


def _parse_architect_verdict(shared_log_text: str) -> str:
    matches = re.findall(
        r"architect_canonical_verdict\s*:\s*(not_met|not met|met)\b",
        shared_log_text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return "missing"
    value = matches[-1].strip().lower().replace(" ", "_")
    if value in {"met", "not_met"}:
        return value
    return "missing"


def _count_architect_not_met(shared_log_text: str) -> int:
    matches = re.findall(
        r"architect_canonical_verdict\s*:\s*(not_met|not met)",
        shared_log_text,
        flags=re.IGNORECASE,
    )
    return len(matches)


def _parse_architect_outcome(shared_log_text: str) -> str:
    matches = re.findall(
        r"architect_directive_outcome\s*:\s*(accepted|rejected|blocked|deferred|closed_without_completion)",
        shared_log_text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return "missing"
    return matches[-1].strip().lower()

