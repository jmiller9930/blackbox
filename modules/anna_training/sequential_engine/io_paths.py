"""Default paths for sequential_engine artifacts (env overrides)."""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_artifacts_dir() -> Path:
    raw = (os.environ.get("BLACKBOX_SEQUENTIAL_ARTIFACTS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _repo_root() / "data" / "sequential_engine"


def outcome_manifest_path(test_id: str) -> Path:
    d = default_artifacts_dir() / test_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "outcome_manifest.jsonl"


def duplicate_audit_path(test_id: str) -> Path:
    d = default_artifacts_dir() / test_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "duplicate_audit.jsonl"


def sequential_state_path(test_id: str) -> Path:
    d = default_artifacts_dir() / test_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "sequential_state.json"


def calibration_report_path() -> Path:
    raw = (os.environ.get("BLACKBOX_CALIBRATION_REPORT_PATH") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return default_artifacts_dir() / "calibration_report.json"
