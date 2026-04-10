"""Named strategies — catalog + optional strict label validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from modules.anna_training.store import anna_training_dir

CATALOG_FILE = "strategy_catalog.json"

# Minimal built-in ids so tests and fresh installs have stable references.
# **Baseline / Karpathy policy engine** = Jupiter_2 (`jupiter_2_sean_perps_v1`). The older id remains for
# legacy ledger rows and tests that pin a stable label.
DEFAULT_STRATEGIES: list[dict[str, Any]] = [
    {
        "id": "jupiter_2_sean_perps_v1",
        "title": "Jupiter_2 — Sean policy spec v1.0 (SOL perp, 5m, ST10×3 + EMA200 + RSI + ATR ratio)",
        "description": "Canonical engine: modules/anna_training/jupiter_2_sean_policy.py; TypeScript-bot parity; paper only.",
    },
    {
        "id": "jupiter_supertrend_ema_rsi_atr_v1",
        "title": "Legacy strategy label (pre–Jupiter_2 catalog id)",
        "description": "Historical id; baseline lane uses jupiter_2_sean_perps_v1. Kept for old execution_trades rows.",
    },
    {
        "id": "manual_operator_v1",
        "title": "Operator-attested manual paper",
        "description": "Rows from anna log-trade without bot signal file.",
    },
]


def catalog_path() -> Path:
    return anna_training_dir() / CATALOG_FILE


def load_strategy_catalog() -> list[dict[str, Any]]:
    p = catalog_path()
    if not p.is_file():
        return list(DEFAULT_STRATEGIES)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return list(DEFAULT_STRATEGIES)
    if not isinstance(raw, list):
        return list(DEFAULT_STRATEGIES)
    out: list[dict[str, Any]] = []
    for x in raw:
        if isinstance(x, dict) and x.get("id"):
            out.append(x)
    return out if out else list(DEFAULT_STRATEGIES)


def known_strategy_ids() -> set[str]:
    return {str(x.get("id", "")).strip() for x in load_strategy_catalog() if x.get("id")}


def strict_strategy_labels() -> bool:
    return (os.environ.get("ANNA_STRICT_STRATEGY_LABELS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def validate_strategy_label(label: str | None) -> tuple[bool, str]:
    """
    When ``ANNA_STRICT_STRATEGY_LABELS=1``, ``strategy_label`` must match a catalog ``id``.

    Empty label is allowed (uncategorized).
    """
    if not label or not str(label).strip():
        return True, ""
    if not strict_strategy_labels():
        return True, ""
    lid = str(label).strip()
    if lid in known_strategy_ids():
        return True, ""
    return False, f"strategy_label_not_in_catalog:{lid}"


def strategy_catalog_fact_lines() -> list[str]:
    ids = sorted(known_strategy_ids())[:24]
    return [f"FACT (strategy catalog): registered strategy ids include: {', '.join(ids)}"]
