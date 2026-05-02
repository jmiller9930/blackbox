"""
FinQuant Unified Agent Lab — Config loader.

Loads and validates agent_lab_config_v1 JSON.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from schemas import SCHEMA_CONFIG

REQUIRED_FIELDS = [
    "schema",
    "agent_id",
    "mode",
    "use_llm_v1",
    "memory_store_path",
    "retrieval_enabled_default_v1",
    "write_outputs_v1",
]


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r") as f:
        cfg = json.load(f)
    _validate(cfg, path)
    return cfg


def _validate(cfg: dict[str, Any], path: str) -> None:
    if cfg.get("schema") != SCHEMA_CONFIG:
        raise ValueError(
            f"config schema must be '{SCHEMA_CONFIG}', got '{cfg.get('schema')}' in {path}"
        )
    missing = [f for f in REQUIRED_FIELDS if f not in cfg]
    if missing:
        raise ValueError(f"config missing fields: {missing} in {path}")
