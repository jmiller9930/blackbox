"""
Resolve manifest selections to concrete callables / signal instances.

This is the bridge from manifest → current engine without duplicating replay logic.
Future: replay_runner imports from here instead of hardcoding signal list.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from renaissance_v4.registry.load import load_catalog
from renaissance_v4.signals.base_signal import BaseSignal


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
    out: list[BaseSignal] = []
    for sid in manifest.get("signal_modules") or []:
        meta = by_id.get(sid)
        if not meta:
            raise KeyError(f"signal {sid} not in catalog")
        cls = _import_class(str(meta["import_path"]), str(meta["class_name"]))
        inst = cls()
        if not isinstance(inst, BaseSignal):
            raise TypeError(f"{sid} does not inherit BaseSignal")
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
    return _import_callable(str(meta["import_path"]), str(meta["callable"]))


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
