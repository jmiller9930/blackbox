"""Create, template, and validate calibration_report.json for a run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.anna_training.sequential_engine.calibration_report import CalibrationReport, load_calibration_report
from modules.anna_training.sequential_engine.mae_v1 import MAE_PROTOCOL_ID


def default_template_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "sequential_engine" / "calibration_report.template.json"


def validate_calibration_for_run(report: CalibrationReport, *, strict_mae: bool = True) -> None:
    """
    Startup validation: protocol must be self-consistent.

    Raises ValueError if ``mae_protocol_id`` does not match the locked MAE v1 id (when strict_mae).
    """
    if strict_mae and report.mae_protocol_id != MAE_PROTOCOL_ID:
        raise ValueError(
            f"calibration mae_protocol_id must be {MAE_PROTOCOL_ID!r} (locked MAE v1), got {report.mae_protocol_id!r}"
        )
    if not (report.protocol_id or "").strip():
        raise ValueError("calibration protocol_id is required")


def write_calibration_from_template(
    dest: Path,
    *,
    protocol_id: str,
    copy_from: Path | None = None,
) -> CalibrationReport:
    """Write a new calibration file from bundled template with ``protocol_id`` set."""
    src = copy_from or default_template_path()
    if not src.is_file():
        raise FileNotFoundError(f"template not found: {src}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = json.loads(src.read_text(encoding="utf-8"))
    raw["protocol_id"] = protocol_id.strip()
    raw["mae_protocol_id"] = MAE_PROTOCOL_ID
    report = CalibrationReport.model_validate(raw)
    validate_calibration_for_run(report)
    dest.write_text(json.dumps(report.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def load_and_validate_calibration(path: Path | None = None) -> CalibrationReport:
    """Load calibration from path (or default) and run protocol validation."""
    report = load_calibration_report(path)
    validate_calibration_for_run(report)
    return report
