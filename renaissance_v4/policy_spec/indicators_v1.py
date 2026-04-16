"""
Frozen indicator vocabulary + validation for PolicySpecV1 (DV-ARCH-CANONICAL-POLICY-VOCABULARY-063).

Rules:
- The vocabulary is broad; each policy declares only the indicators it uses.
- Undeclared kinds are not validated (no declaration → no check).
- Declared kinds must use ``kind`` ∈ INDICATOR_KIND_VOCABULARY and satisfy per-kind params.
- Gates reference declaration ``id`` values only.
"""

from __future__ import annotations

import json
from typing import Any

# Frozen in this pass — extend only via intentional contract revision.
INDICATOR_KIND_VOCABULARY: frozenset[str] = frozenset(
    {
        # Price / trend / momentum (classic)
        "ema",
        "sma",
        "rsi",
        "atr",
        "macd",
        "bollinger_bands",
        "vwap",
        "supertrend",
        "stochastic",
        "adx",
        # Common extras (same contract; declare only if used)
        "cci",
        "williams_r",
        "mfi",
        "obv",
        "parabolic_sar",
        "ichimoku",
        "donchian",
        # Volume / structure / meta (declarative hooks; runtime computes from OHLCV)
        "volume_filter",
        "divergence",
        "body_measurement",
        "fixed_threshold",
        "threshold_group",
    }
)

INDICATORS_SCHEMA_VERSION = "policy_indicators_v1"

GATE_OPERATORS: frozenset[str] = frozenset(
    {
        "lt",
        "lte",
        "gt",
        "gte",
        "eq",
        "between",
        "cross_above",
        "cross_below",
    }
)

ALLOWED_INDICATORS_TOP_LEVEL_KEYS = frozenset({"schema_version", "declarations", "gates", "notes"})


def default_indicators_section() -> dict[str, Any]:
    return {
        "schema_version": INDICATORS_SCHEMA_VERSION,
        "declarations": [],
        "gates": [],
    }


def coerce_indicators_section(raw: Any) -> dict[str, Any]:
    """Return a well-shaped indicators dict; empty if missing/invalid."""
    if not isinstance(raw, dict):
        return default_indicators_section()
    out = default_indicators_section()
    sv = raw.get("schema_version")
    out["schema_version"] = str(sv).strip() if isinstance(sv, str) and str(sv).strip() else INDICATORS_SCHEMA_VERSION
    dec = raw.get("declarations")
    out["declarations"] = list(dec) if isinstance(dec, list) else []
    gates = raw.get("gates")
    out["gates"] = list(gates) if isinstance(gates, list) else []
    if isinstance(raw.get("notes"), str):
        out["notes"] = raw["notes"][:4000]
    return out


def _positive_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _positive_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) == float(v)


def _validate_params_for_kind(kind: str, params: dict[str, Any], label: str) -> list[str]:
    errs: list[str] = []
    p = params

    def req_int(key: str) -> None:
        if not _positive_int(p.get(key)):
            errs.append(f"{label}: params.{key} must be a positive integer")

    def req_num(key: str) -> None:
        if not _positive_number(p.get(key)):
            errs.append(f"{label}: params.{key} must be a positive number")

    if kind in ("ema", "sma", "rsi", "atr", "adx"):
        req_int("period")
    elif kind == "macd":
        for k in ("fast_period", "slow_period", "signal_period"):
            req_int(k)
        if (
            _positive_int(p.get("fast_period"))
            and _positive_int(p.get("slow_period"))
            and int(p["fast_period"]) >= int(p["slow_period"])
        ):
            errs.append(f"{label}: macd fast_period must be < slow_period")
    elif kind == "bollinger_bands":
        req_int("period")
        req_num("std_dev")
    elif kind == "vwap":
        pass
    elif kind == "supertrend":
        req_int("period")
        req_num("multiplier")
    elif kind == "stochastic":
        for k in ("k_period", "d_period"):
            req_int(k)
    elif kind in ("cci", "williams_r", "mfi"):
        req_int("period")
    elif kind == "obv":
        pass
    elif kind == "parabolic_sar":
        for k in ("step", "max_step"):
            v = p.get(k)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errs.append(f"{label}: parabolic_sar.params.{k} must be a number")
            elif float(v) <= 0 or float(v) > 1:
                errs.append(f"{label}: parabolic_sar.params.{k} must be in (0, 1]")
    elif kind == "ichimoku":
        for k in ("tenkan", "kijun", "senkou_b"):
            req_int(k)
    elif kind == "donchian":
        req_int("period")
    elif kind == "volume_filter":
        mode = p.get("mode")
        if str(mode or "") not in (
            "relative_to_sma",
            "min_quote_volume",
            "min_raw_volume",
            "session_compare",
        ):
            errs.append(
                f"{label}: volume_filter.params.mode must be one of "
                "relative_to_sma|min_quote_volume|min_raw_volume|session_compare"
            )
        if str(mode or "") == "relative_to_sma":
            req_int("period")
    elif kind == "divergence":
        if not _positive_int(p.get("lookback")):
            errs.append(f"{label}: divergence.params.lookback must be a positive integer")
        ir = p.get("indicator_ref")
        if not str(ir or "").strip():
            errs.append(f"{label}: divergence.params.indicator_ref must reference a declaration id")
    elif kind == "body_measurement":
        mode = p.get("mode")
        if str(mode or "") not in ("body_to_range", "body_pct_of_range", "candle_direction"):
            errs.append(
                f"{label}: body_measurement.params.mode must be one of "
                "body_to_range|body_pct_of_range|candle_direction"
            )
    elif kind == "fixed_threshold":
        v = p.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"{label}: fixed_threshold.params.value must be numeric")
    elif kind == "threshold_group":
        gid = str(p.get("group_id") or "").strip()
        if not gid:
            errs.append(f"{label}: threshold_group.params.group_id required")
        members = p.get("members")
        if not isinstance(members, list) or len(members) < 1:
            errs.append(f"{label}: threshold_group.params.members must be a non-empty list")
        else:
            for i, m in enumerate(members):
                if not isinstance(m, dict) or not str(m.get("ref") or "").strip():
                    errs.append(f"{label}: threshold_group.params.members[{i}] needs ref")

    return errs


def validate_indicators_section(section: Any) -> list[str]:
    """
    Validate optional ``indicators`` block on the canonical policy.

    If ``declarations`` is empty, returns [] (undeclared indicators are ignored globally).
    """
    errs: list[str] = []
    if section is None:
        return errs
    if not isinstance(section, dict):
        return ["indicators: must be an object when present"]

    extra = set(section.keys()) - ALLOWED_INDICATORS_TOP_LEVEL_KEYS
    if extra:
        errs.append(f"indicators: unknown keys {sorted(extra)} — use only declarations/gates/notes")

    decls = section.get("declarations")
    if decls is None:
        decls = []
    if not isinstance(decls, list):
        errs.append("indicators.declarations must be a list")
        return errs

    seen_ids: set[str] = set()
    decl_ids: list[str] = []

    for i, d in enumerate(decls):
        label = f"indicators.declarations[{i}]"
        if not isinstance(d, dict):
            errs.append(f"{label}: must be an object")
            continue
        did = str(d.get("id") or "").strip()
        if not did:
            errs.append(f"{label}: id required")
            continue
        if did in seen_ids:
            errs.append(f"{label}: duplicate id {did!r}")
        seen_ids.add(did)
        decl_ids.append(did)

        kind = str(d.get("kind") or "").strip().lower()
        if not kind:
            errs.append(f"{label}: kind required")
            continue
        if kind not in INDICATOR_KIND_VOCABULARY:
            errs.append(
                f"{label}: unknown kind {kind!r} — must be one of the frozen vocabulary "
                f"(see INDICATOR_KIND_VOCABULARY in indicators_v1.py)"
            )
            continue

        params = d.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            errs.append(f"{label}: params must be an object")
            continue

        errs.extend(_validate_params_for_kind(kind, params, label))

    gates = section.get("gates")
    if gates is None:
        gates = []
    if not isinstance(gates, list):
        errs.append("indicators.gates must be a list")
        return errs

    decl_set = set(decl_ids)
    for i, g in enumerate(gates):
        gl = f"indicators.gates[{i}]"
        if not isinstance(g, dict):
            errs.append(f"{gl}: must be an object")
            continue
        gid = str(g.get("indicator_id") or "").strip()
        if not gid:
            errs.append(f"{gl}: indicator_id required")
            continue
        if gid not in decl_set:
            errs.append(
                f"{gl}: indicator_id {gid!r} must match a indicators.declarations[].id — "
                "undeclared indicators cannot be gated"
            )
        op = str(g.get("operator") or "").strip().lower()
        if op and op not in GATE_OPERATORS:
            errs.append(f"{gl}: unknown operator {op!r}")

        ref2 = str(g.get("reference_indicator_id") or "").strip()
        if ref2 and ref2 not in decl_set:
            errs.append(f"{gl}: reference_indicator_id must match a declaration id")

    return errs


def indicators_section_json_for_harness(section: dict[str, Any]) -> str:
    """Serialize for RV4_POLICY_INDICATORS_JSON env (UTF-8 JSON object)."""
    return json.dumps(coerce_indicators_section(section), separators=(",", ":"), ensure_ascii=True)
