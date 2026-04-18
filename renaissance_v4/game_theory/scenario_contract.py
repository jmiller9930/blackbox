"""
Scenario batch JSON — required shape for parallel_runner / web UI.

The Referee uses only manifest_path + optional ATR overrides. Optional *agent* fields are
echoed in results for training / audit (they do not change deterministic replay scores).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Keys copied from each scenario dict into worker results (for ML / operator trace).
AGENT_ECHO_KEYS: tuple[str, ...] = (
    "agent_explanation",
    "training_trace_id",
    "prior_scenario_id",
)


def extract_agent_fields(scenario: dict[str, Any]) -> dict[str, Any]:
    """Return whitelisted agent/training metadata for JSON-safe echo in results."""
    out: dict[str, Any] = {}
    for k in AGENT_ECHO_KEYS:
        if k in scenario and scenario[k] is not None:
            out[k] = scenario[k]
    return out


def validate_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    check_manifest_exists: bool = False,
    repo_root: Path | None = None,
) -> tuple[bool, list[str]]:
    """
    Return (ok, messages). ``ok`` is False only for blocking errors (empty list, missing manifest_path).

    Non-blocking warnings: unknown keys (we only document known keys), missing optional agent fields.
    """
    messages: list[str] = []
    if not scenarios:
        return False, ["scenarios must be a non-empty JSON array of objects"]

    known = {
        "scenario_id",
        "manifest_path",
        "atr_stop_mult",
        "atr_target_mult",
        "emit_baseline_artifacts",
        *AGENT_ECHO_KEYS,
    }

    for i, s in enumerate(scenarios):
        mp = s.get("manifest_path")
        if not mp or not isinstance(mp, str):
            return False, [f"scenario[{i}] missing or invalid manifest_path (required string)"]
        if check_manifest_exists and repo_root is not None:
            p = Path(mp).expanduser()
            if not p.is_absolute():
                p = (repo_root / p).resolve()
            else:
                p = p.resolve()
            if not p.is_file():
                messages.append(f"warning: scenario[{i}] manifest not found: {p}")

        extra = set(s.keys()) - known
        if extra:
            messages.append(
                f"scenario[{i}] has undocumented keys (ignored by runner): {sorted(extra)}"
            )

    return True, messages
