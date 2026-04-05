"""Sequential experiment engine: pattern specs, paired outcomes, SPRT, append-only manifests."""

from __future__ import annotations

from modules.anna_training.sequential_engine.calibration_factory import (
    load_and_validate_calibration,
    validate_calibration_for_run,
    write_calibration_from_template,
)
from modules.anna_training.sequential_engine.calibration_report import (
    CalibrationReport,
    calibration_report_fingerprint,
    load_calibration_report,
)
from modules.anna_training.sequential_engine.decision_state import (
    advance_sprt_after_outcome,
    commit_outcome,
    export_decision_snapshot,
    load_calibration_for_test,
)
from modules.anna_training.sequential_engine.runtime_driver import run_sequential_learning_driver
from modules.anna_training.sequential_engine.sequential_persistence import (
    ensure_strategy_registered,
    list_sequential_runs_for_test,
    load_last_sequential_decision,
    persist_sequential_decision_run,
)
from modules.anna_training.sequential_engine.mae_v1 import MAE_PROTOCOL_ID, compute_mae_usd_v1
from modules.anna_training.sequential_engine.outcome_manifest import (
    append_outcome_record,
    rebuild_state_hashes_from_manifest,
)
from modules.anna_training.sequential_engine.pair_evaluation import build_outcome_record, eligible_for_sprt
from modules.anna_training.sequential_engine.pattern_spec import pattern_spec_hash
from modules.anna_training.sequential_engine.hypothesis import hypothesis_hash
from modules.anna_training.sequential_engine.sequential_errors import CorruptionError
from modules.anna_training.sequential_engine.sprt import classify_sprt_decision, sprt_thresholds
from modules.anna_training.sequential_engine.scaling_policy import execution_tier, max_scale_bound

__all__ = [
    "MAE_PROTOCOL_ID",
    "CalibrationReport",
    "CorruptionError",
    "advance_sprt_after_outcome",
    "append_outcome_record",
    "build_outcome_record",
    "calibration_report_fingerprint",
    "classify_sprt_decision",
    "commit_outcome",
    "compute_mae_usd_v1",
    "eligible_for_sprt",
    "ensure_strategy_registered",
    "execution_tier",
    "export_decision_snapshot",
    "hypothesis_hash",
    "list_sequential_runs_for_test",
    "load_and_validate_calibration",
    "load_calibration_for_test",
    "load_calibration_report",
    "load_last_sequential_decision",
    "max_scale_bound",
    "pattern_spec_hash",
    "persist_sequential_decision_run",
    "rebuild_state_hashes_from_manifest",
    "run_sequential_learning_driver",
    "sprt_thresholds",
    "validate_calibration_for_run",
    "write_calibration_from_template",
]
