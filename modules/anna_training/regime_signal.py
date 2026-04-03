"""Regime + optional ``trading_core`` signal snapshot — atmosphere and execution gating.

``trading_core`` (TypeScript bot) can drop ``trading_core_signal.json`` under the Anna training dir
(see ``load_trading_core_signal``). Analysis merges it into ``anna_analysis_v1`` for proposals and
optional strict execution wiring (``ANNA_REQUIRE_SIGNAL_SNAPSHOT_FOR_EXECUTION``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from modules.anna_training.store import anna_training_dir

SIGNAL_SCHEMA = "trading_core_signal_v1"
SIGNAL_FILE_NAME = "trading_core_signal.json"


def infer_regime_from_phase5_market(phase5_market: dict[str, Any] | None) -> str:
    """Coarse regime from Phase 5.1 market tick gate_state (atmosphere / data health)."""
    if not phase5_market or not isinstance(phase5_market, dict):
        return "unknown"
    tick = phase5_market.get("tick")
    if not isinstance(tick, dict):
        return "unknown"
    gs = str(tick.get("gate_state") or "unknown").strip().lower()
    if gs == "blocked":
        return "data_blocked"
    if gs == "degraded":
        return "degraded"
    if gs in ("ok", "nominal", "passed"):
        return "nominal"
    return gs or "unknown"


def load_trading_core_signal() -> dict[str, Any] | None:
    """Optional JSON written by ``trading_core`` / operator — latest bot signal evaluation."""
    p = anna_training_dir() / SIGNAL_FILE_NAME
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("schema") != SIGNAL_SCHEMA:
        return None
    return raw


def signal_allows_execution_path(signal: dict[str, Any] | None) -> bool:
    """
    True if snapshot says filters pass and at least one direction is allowed.

    Missing snapshot → True (backward compatible) unless caller applies strict mode separately.
    """
    if not signal:
        return True
    if signal.get("schema") != SIGNAL_SCHEMA:
        return True
    if signal.get("filters_pass") is False:
        return False
    lo = bool(signal.get("long_ok"))
    so = bool(signal.get("short_ok"))
    return lo or so


def require_signal_snapshot_for_execution() -> bool:
    return (os.environ.get("ANNA_REQUIRE_SIGNAL_SNAPSHOT_FOR_EXECUTION") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def execution_blocked_by_signal_policy(
    analysis: dict[str, Any],
) -> tuple[bool, str]:
    """
    When strict: require a valid ``signal_snapshot`` that passes ``signal_allows_execution_path``.

    Returns (blocked, reason).
    """
    if not require_signal_snapshot_for_execution():
        return False, ""
    ss = analysis.get("signal_snapshot")
    if not isinstance(ss, dict) or not ss:
        return True, "strict_signal_missing_snapshot"
    if ss.get("schema") != SIGNAL_SCHEMA:
        return True, "strict_signal_bad_schema"
    if not signal_allows_execution_path(ss):
        return True, "strict_signal_filters_or_direction"
    return False, ""


def signal_fact_lines(signal: dict[str, Any] | None, regime: str | None) -> list[str]:
    """Short FACT lines for analyst merge."""
    lines: list[str] = []
    r = (regime or "unknown").strip() or "unknown"
    lines.append(f"FACT (regime): market atmosphere tag = {r}")
    if not signal:
        lines.append(
            "FACT (trading_core signal): no trading_core_signal.json snapshot — "
            "execution gating uses policy only unless ANNA_REQUIRE_SIGNAL_SNAPSHOT_FOR_EXECUTION=1."
        )
        return lines
    if signal.get("schema") != SIGNAL_SCHEMA:
        lines.append("FACT (trading_core signal): snapshot present but schema not trading_core_signal_v1")
        return lines
    lo = bool(signal.get("long_ok"))
    so = bool(signal.get("short_ok"))
    fp = signal.get("filters_pass")
    bar = str(signal.get("bar_ts") or "—")
    lines.append(
        f"FACT (trading_core signal): filters_pass={fp!s} long_ok={lo} short_ok={so} bar_ts={bar}"
    )
    return lines
