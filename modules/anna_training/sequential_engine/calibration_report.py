"""Load and validate calibration_report.json (versioned; no manual tuning in code)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class CalibrationReport(BaseModel):
    """Schema for calibration_report.json — extend only via protocol version bumps."""

    schema_version: str = Field(default="calibration_report_v1")
    protocol_id: str = Field(min_length=1)
    p0: float = Field(ge=0.0, le=1.0)
    p1: float = Field(ge=0.0, le=1.0)
    alpha: float = Field(gt=0.0, lt=1.0)
    beta: float = Field(gt=0.0, lt=1.0)
    n_min: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    epsilon: float = Field(ge=0.0)
    mae_protocol_id: str = Field(min_length=1)
    autocorrelation_rho: float | None = Field(default=None)
    calibration_inputs_hash: str = Field(default="", description="Hash of calibration data slice")

    @field_validator("p1")
    @classmethod
    def p1_above_p0(cls, p1: float, info: ValidationInfo) -> float:
        p0 = info.data.get("p0")
        if isinstance(p0, (int, float)) and p1 <= float(p0):
            raise ValueError("p1 must be greater than p0")
        return p1


def load_calibration_report(path: Path | None = None) -> CalibrationReport:
    from modules.anna_training.sequential_engine.io_paths import calibration_report_path

    p = path or calibration_report_path()
    if not p.is_file():
        raise FileNotFoundError(f"calibration_report not found: {p}")
    raw = json.loads(p.read_text(encoding="utf-8"))
    return CalibrationReport.model_validate(raw)


def calibration_report_fingerprint(report: CalibrationReport) -> dict[str, Any]:
    """Stable dict for hashing (subset of fields)."""
    return {
        "schema_version": report.schema_version,
        "protocol_id": report.protocol_id,
        "p0": report.p0,
        "p1": report.p1,
        "alpha": report.alpha,
        "beta": report.beta,
        "n_min": report.n_min,
        "batch_size": report.batch_size,
        "epsilon": report.epsilon,
        "mae_protocol_id": report.mae_protocol_id,
        "autocorrelation_rho": report.autocorrelation_rho,
        "calibration_inputs_hash": report.calibration_inputs_hash,
    }
