"""Load QEL survival checkpoint config (YAML + env override)."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from modules.anna_training.store import utc_now_iso

_DEFAULT_REL = Path("config/survival_engine.json")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_survival_config_path() -> Path:
    raw = (os.environ.get("SURVIVAL_ENGINE_CONFIG") or os.environ.get("ANNA_SURVIVAL_CONFIG_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _repo_root() / _DEFAULT_REL


def load_survival_config(path: Path | None = None) -> dict[str, Any]:
    """Load JSON config; fall back to builtins if missing or invalid."""
    p = path or default_survival_config_path()
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return deepcopy(data)
        except (json.JSONDecodeError, OSError):
            pass
    return _builtin_defaults()


def _builtin_defaults() -> dict[str, Any]:
    return {
        "qel_version": "1",
        "lifecycle_auto": {
            "enabled": True,
            "min_completed_survived_for_promotion_ready": 3,
        },
        "regime_v1": {
            "vol_low_below": 0.003,
            "vol_mid_below": 0.012,
            "flat_abs_pct": 0.0005,
        },
        "checkpoints": {
            "min_economic_trades": {"enabled": True, "min_count": 5},
            "min_distinct_market_events": {"enabled": True, "min_count": 5},
            "min_calendar_span_days": {"enabled": True, "min_days": 1},
            "distinctiveness_hash": {"enabled": True},
            "min_regime_vol_buckets": {
                "enabled": True,
                "min_distinct_vol_buckets": 2,
                "min_trades_per_bucket": 1,
            },
            "min_performance": {
                "enabled": True,
                "min_total_pnl_usd": -1e9,
                "min_win_rate_decisive": 0.0,
            },
        },
    }


def checkpoint_summary_header(
    *,
    checkpoint_name: str,
    decision: str,
    strategy_id: str,
    test_id: str,
    engine_version: str,
) -> dict[str, Any]:
    """Stable top-level fields every checkpoint_summary_json must include."""
    return {
        "subsystem": "Quantitative Evaluation Layer",
        "checkpoint_name": checkpoint_name,
        "decision": decision,
        "strategy_id": strategy_id,
        "test_id": test_id,
        "engine_version": engine_version,
        "evaluated_at_utc": utc_now_iso(),
    }
