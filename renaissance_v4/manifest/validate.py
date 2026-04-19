"""
Validate a strategy manifest against the plugin catalog before replay.

Malformed manifests must fail before replay begins (directive: governed processing).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renaissance_v4.registry.load import load_catalog


def _index_by_id(items: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not items:
        return out
    for it in items:
        if isinstance(it, dict) and it.get("id"):
            out[str(it["id"])] = it
    return out


def validate_manifest_against_catalog(
    manifest: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
    catalog_path: Path | None = None,
) -> list[str]:
    """
    Return a list of error strings; empty list means manifest is structurally valid for v1.
    Does not execute imports — only registry membership and allowed experiment types.
    """
    errors: list[str] = []
    if manifest.get("schema") != "strategy_manifest_v1":
        errors.append("manifest.schema must be 'strategy_manifest_v1'")
    if manifest.get("manifest_version") != "1.0":
        errors.append("manifest.manifest_version must be '1.0' for this validator")

    if catalog is None:
        if catalog_path is None:
            from renaissance_v4.registry import default_catalog_path

            catalog_path = default_catalog_path()
        catalog = load_catalog(catalog_path)

    factors = _index_by_id(catalog.get("factor_pipelines"))
    signals = _index_by_id(catalog.get("signals"))
    regimes = _index_by_id(catalog.get("regime_classifiers"))
    risks = _index_by_id(catalog.get("risk_models"))
    fusions = _index_by_id(catalog.get("fusion_engines"))
    executions = _index_by_id(catalog.get("execution_templates"))
    stops = _index_by_id(catalog.get("stop_target_templates"))

    fp = manifest.get("factor_pipeline")
    if fp and fp not in factors:
        errors.append(f"unknown factor_pipeline id: {fp}")

    for sid in manifest.get("signal_modules") or []:
        if sid not in signals:
            errors.append(f"unknown signal module id: {sid}")

    rm = manifest.get("regime_module")
    if rm and rm not in regimes:
        errors.append(f"unknown regime_module id: {rm}")

    rk = manifest.get("risk_model")
    if rk and rk not in risks:
        errors.append(f"unknown risk_model id: {rk}")

    fu = manifest.get("fusion_module")
    if fu and fu not in fusions:
        errors.append(f"unknown fusion_module id: {fu}")

    ex = manifest.get("execution_template")
    if ex and ex not in executions:
        errors.append(f"unknown execution_template id: {ex}")

    st = manifest.get("stop_target_template")
    if st and st not in stops:
        errors.append(f"unknown stop_target_template id: {st}")

    et = manifest.get("experiment_type")
    allowed = catalog.get("allowed_experiment_types") or []
    if et and allowed and et not in allowed:
        errors.append(f"experiment_type not allowed: {et}; allowed={allowed}")

    # Optional pattern-game ATR multiples (ExecutionManager); must stay in a sane band.
    _MIN_ATR, _MAX_ATR = 0.5, 6.0
    for key in ("atr_stop_mult", "atr_target_mult"):
        v = manifest.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric")
            continue
        if not (_MIN_ATR <= f <= _MAX_ATR):
            errors.append(f"{key} must be in [{_MIN_ATR}, {_MAX_ATR}], got {f}")

    # Optional fusion overrides (fusion_engine.fuse_signal_results)
    for key in ("fusion_min_score", "fusion_max_conflict_score", "fusion_overlap_penalty_per_extra_signal"):
        v = manifest.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric")
            continue
        if not (0.0 <= f <= 1.0):
            errors.append(f"{key} must be in [0.0, 1.0], got {f}")

    # Optional signal threshold overrides (see signals/*.py configure_from_manifest)
    for key in (
        "mean_reversion_fade_min_confidence",
        "trend_continuation_min_confidence",
        "trend_continuation_min_regime_fit",
        "pullback_continuation_min_confidence",
        "pullback_continuation_volatility_threshold",
        "breakout_expansion_min_confidence",
    ):
        v = manifest.get(key)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            errors.append(f"{key} must be numeric")
            continue
        if not (0.0 <= f <= 1.0):
            errors.append(f"{key} must be in [0.0, 1.0], got {f}")

    v_st = manifest.get("mean_reversion_fade_stretch_threshold")
    if v_st is not None:
        try:
            f = float(v_st)
        except (TypeError, ValueError):
            errors.append("mean_reversion_fade_stretch_threshold must be numeric")
        else:
            if not (0.000001 <= f <= 0.2):
                errors.append(f"mean_reversion_fade_stretch_threshold must be in [1e-6, 0.2], got {f}")

    disabled = manifest.get("disabled_signal_modules")
    if disabled is not None:
        if not isinstance(disabled, list):
            errors.append("disabled_signal_modules must be a list of signal module ids")
        else:
            active = list(manifest.get("signal_modules") or [])
            for sid in disabled:
                if not isinstance(sid, str):
                    errors.append(f"disabled_signal_modules entries must be strings, got {sid!r}")
                    continue
                if sid not in signals:
                    errors.append(f"unknown disabled_signal_modules id: {sid}")
                elif sid not in active:
                    errors.append(
                        f"disabled_signal_modules id {sid!r} is not in manifest.signal_modules"
                    )
            remaining = [s for s in active if s not in set(disabled)]
            if not remaining:
                errors.append(
                    "at least one signal module must remain enabled after disabled_signal_modules"
                )

    return errors


def load_manifest_file(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest must be a JSON object")
    return raw
