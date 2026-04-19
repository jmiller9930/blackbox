"""
Resolve manifest selections to concrete callables / signal instances.

This is the bridge from manifest → current engine without duplicating replay logic.
Future: replay_runner imports from here instead of hardcoding signal list.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from renaissance_v4.core.fusion_engine import fuse_signal_results
from renaissance_v4.registry.load import load_catalog
from renaissance_v4.signals.base_signal import BaseSignal
from renaissance_v4.signals.signal_result import SignalResult


def _import_class(import_path: str, class_name: str) -> type:
    mod = importlib.import_module(import_path)
    cls = getattr(mod, class_name, None)
    if cls is None:
        raise ImportError(f"class {class_name} not in {import_path}")
    return cls


def _import_callable(import_path: str, name: str) -> Callable[..., Any]:
    mod = importlib.import_module(import_path)
    fn = getattr(mod, name, None)
    if fn is None or not callable(fn):
        raise ImportError(f"callable {name} not in {import_path}")
    return fn


def build_signals_from_manifest(
    manifest: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
) -> list[BaseSignal]:
    """
    Instantiate signal plug-ins listed in manifest.signal_modules in catalog order.
    """
    if catalog is None:
        from renaissance_v4.registry import default_catalog_path

        catalog = load_catalog(default_catalog_path())

    by_id = {s["id"]: s for s in catalog.get("signals") or [] if isinstance(s, dict) and s.get("id")}
    disabled = set(manifest.get("disabled_signal_modules") or [])
    out: list[BaseSignal] = []
    for sid in manifest.get("signal_modules") or []:
        if sid in disabled:
            continue
        meta = by_id.get(sid)
        if not meta:
            raise KeyError(f"signal {sid} not in catalog")
        cls = _import_class(str(meta["import_path"]), str(meta["class_name"]))
        inst = cls()
        if not isinstance(inst, BaseSignal):
            raise TypeError(f"{sid} does not inherit BaseSignal")
        inst.configure_from_manifest(manifest)
        out.append(inst)
    return out


def resolve_fusion(manifest: dict[str, Any], *, catalog: dict[str, Any] | None = None) -> Callable[..., Any]:
    if catalog is None:
        from renaissance_v4.registry import default_catalog_path

        catalog = load_catalog(default_catalog_path())
    fid = manifest.get("fusion_module")
    meta = next((f for f in catalog.get("fusion_engines") or [] if f.get("id") == fid), None)
    if not meta:
        raise KeyError(f"fusion {fid} not in catalog")
    import_path = str(meta["import_path"])
    callable_name = str(meta["callable"])
    # Baseline catalog uses fuse_signal_results; pass manifest overrides for thresholds.
    if import_path == "renaissance_v4.core.fusion_engine" and callable_name == "fuse_signal_results":

        def fusion_fn(signal_results: list[SignalResult]) -> Any:
            return fuse_signal_results(
                signal_results,
                min_fusion_score=manifest.get("fusion_min_score"),
                max_conflict_score=manifest.get("fusion_max_conflict_score"),
                overlap_penalty_per_extra_signal=manifest.get("fusion_overlap_penalty_per_extra_signal"),
            )

        return fusion_fn

    return _import_callable(import_path, callable_name)


def resolve_regime_fn(manifest: dict[str, Any], *, catalog: dict[str, Any] | None = None) -> Callable[..., Any]:
    if catalog is None:
        from renaissance_v4.registry import default_catalog_path

        catalog = load_catalog(default_catalog_path())
    rid = manifest.get("regime_module")
    meta = next((r for r in catalog.get("regime_classifiers") or [] if r.get("id") == rid), None)
    if not meta:
        raise KeyError(f"regime {rid} not in catalog")
    return _import_callable(str(meta["import_path"]), str(meta["callable"]))


def resolve_risk_fn(manifest: dict[str, Any], *, catalog: dict[str, Any] | None = None) -> Callable[..., Any]:
    if catalog is None:
        from renaissance_v4.registry import default_catalog_path

        catalog = load_catalog(default_catalog_path())
    rid = manifest.get("risk_model")
    meta = next((r for r in catalog.get("risk_models") or [] if r.get("id") == rid), None)
    if not meta:
        raise KeyError(f"risk model {rid} not in catalog")
    return _import_callable(str(meta["import_path"]), str(meta["callable"]))


def resolve_factor_fn(manifest: dict[str, Any], *, catalog: dict[str, Any] | None = None) -> Callable[..., Any]:
    if catalog is None:
        from renaissance_v4.registry import default_catalog_path

        catalog = load_catalog(default_catalog_path())
    pid = manifest.get("factor_pipeline")
    meta = next((p for p in catalog.get("factor_pipelines") or [] if p.get("id") == pid), None)
    if not meta:
        raise KeyError(f"factor pipeline {pid} not in catalog")
    return _import_callable(str(meta["import_path"]), str(meta["callable"]))


def build_execution_manager_from_manifest(
    manifest: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
) -> Any:
    """Instantiate execution template class from catalog (e.g. ExecutionManager)."""
    if catalog is None:
        from renaissance_v4.registry import default_catalog_path

        catalog = load_catalog(default_catalog_path())
    eid = manifest.get("execution_template")
    meta = next((e for e in catalog.get("execution_templates") or [] if e.get("id") == eid), None)
    if not meta:
        raise KeyError(f"execution_template {eid} not in catalog")
    cls = _import_class(str(meta["import_path"]), str(meta["class_name"]))
    raw_s = manifest.get("atr_stop_mult")
    raw_t = manifest.get("atr_target_mult")
    kwargs: dict[str, float] = {}
    if raw_s is not None:
        kwargs["atr_stop_mult"] = float(raw_s)
    if raw_t is not None:
        kwargs["atr_target_mult"] = float(raw_t)
    return cls(**kwargs) if kwargs else cls()
