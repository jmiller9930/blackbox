"""
GT_DIRECTIVE_026AI — ``reasoning_router_config_v1`` (no secrets; env references only).
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA = "reasoning_router_config_v1"
CONTRACT_VERSION = 1

# Allowed escalation reason codes (must match router).
ALLOWED_ESCALATION_REASONS = (
    "low_confidence_v1",
    "indicator_conflict_v1",
    "memory_conflict_v1",
    "risk_conflict_v1",
    "schema_failure_v1",
    "operator_forced_audit_v1",
    "high_value_opportunity_v1",
    "student_vs_baseline_disagreement_v1",
    "random_audit_sample_v1",
)

DEFAULTS: dict[str, Any] = {
    "schema": SCHEMA,
    "contract_version": CONTRACT_VERSION,
    "router_enabled": True,
    "external_api_enabled": False,
    "external_provider": "openai",
    "external_model": "gpt-5.5",
    "api_key_env_var": "OPENAI_API_KEY",
    "max_external_calls_per_run": 1,
    "max_external_calls_per_trade": 1,
    "max_input_tokens_per_call": 8000,
    "max_output_tokens_per_call": 2000,
    "max_total_tokens_per_run": 24_000,
    "max_estimated_cost_usd_per_run": 0.5,
    "low_confidence_threshold": 0.35,
    "max_memory_records_for_external": 3,
    "random_audit_sample_rate": 0.0,
    "enabled_escalation_reasons": list(ALLOWED_ESCALATION_REASONS),
    "local_llm_model": "qwen3-coder:30b",
    "local_ollama_base_url": "http://172.20.1.66:11434",
}


def _as_float(s: str | None, default: float) -> float:
    if s is None or not str(s).strip():
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _as_int(s: str | None, default: int) -> int:
    if s is None or not str(s).strip():
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def apply_environment_overrides_v1(base: dict[str, Any]) -> dict[str, Any]:
    """
    Documented overrides (non-exhaustive; only safe toggles and caps from env):
    - OPENAI_REASONING_MODEL → external_model
    - OPENAI_MAX_DOLLARS_PER_RUN → max_estimated_cost_usd_per_run
    - OPENAI_MAX_TOKENS_PER_RUN → max_total_tokens_per_run
    - OPENAI_ESCALATION_ENABLED / OPENAI_ESCALATION_ENABLED=1|0 → external_api_enabled
    """
    out = deepcopy(base)
    m = (os.environ.get("OPENAI_REASONING_MODEL") or "").strip()
    if m:
        out["external_model"] = m
    md = (os.environ.get("OPENAI_MAX_DOLLARS_PER_RUN") or "").strip()
    if md:
        out["max_estimated_cost_usd_per_run"] = _as_float(md, float(out.get("max_estimated_cost_usd_per_run") or 0.5))
    mt = (os.environ.get("OPENAI_MAX_TOKENS_PER_RUN") or "").strip()
    if mt:
        out["max_total_tokens_per_run"] = _as_int(mt, int(out.get("max_total_tokens_per_run") or 0))
    es = (os.environ.get("OPENAI_ESCALATION_ENABLED") or "").strip().lower()
    if es in ("1", "true", "yes", "on"):
        out["external_api_enabled"] = True
    elif es in ("0", "false", "no", "off"):
        out["external_api_enabled"] = False
    return out


def load_reasoning_router_config_v1(
    path: str | os.PathLike[str] | None = None,
    *,
    extra_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load JSON config (no secret values). Merge: defaults < file < extra_dict < environment."""
    c = deepcopy(DEFAULTS)
    c["schema"] = SCHEMA
    c["contract_version"] = CONTRACT_VERSION
    if path:
        p = Path(path)
        if p.is_file():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                c.update({k: v for k, v in raw.items() if not str(k).startswith("_")})
    if isinstance(extra_dict, dict):
        c.update({k: v for k, v in extra_dict.items() if v is not None})
    c = apply_environment_overrides_v1(c)
    return c


def validate_config_public_surface_v1(c: dict[str, Any]) -> list[str]:
    """Ensure no obvious secret material in the config dict (best-effort)."""
    errs: list[str] = []
    for _k, v in (c or {}).items():
        s = str(v)
        if s.startswith("sk-") and len(s) > 20:
            errs.append("config values must not contain raw API key material")
    return errs
