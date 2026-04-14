"""
Plugin catalog for Quant Research Kitchen V1 — factor pipelines, signals, regime, risk, fusion, execution.

The catalog is data-driven (`catalog_v1.json`). The replay engine resolves manifests against this file
instead of hardcoding new strategy wiring in `replay_runner.py`.
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.registry.load import load_catalog

_CATALOG_PATH = Path(__file__).resolve().parent / "catalog_v1.json"


def default_catalog_path() -> Path:
    return _CATALOG_PATH


def load_default_catalog() -> dict:
    return load_catalog(_CATALOG_PATH)
