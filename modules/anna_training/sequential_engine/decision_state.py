"""SPRT decision state (versioned), batch evaluation after n_min, Wilson reporting only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.anna_training.store import utc_now_iso
from modules.anna_training.wilson_nist_reference import wilson_score_interval_95_decimal

from .calibration_report import CalibrationReport, calibration_report_fingerprint, load_calibration_report
from .canonical_json import sha256_hex
from .io_paths import calibration_report_path, sequential_state_path
from .outcome_manifest import STATE_SCHEMA_VERSION, _atomic_write_json, load_state
from .sequential_errors import CorruptionError
from .sprt import classify_sprt_decision, sprt_log_contribution


def _wilson(wins: int, n: int) -> tuple[float, float]:
    lo, hi = wilson_score_interval_95_decimal(wins, n)
    return float(lo), float(hi)


def _default_sprt_block(calibration_hash: str) -> dict[str, Any]:
    return {
        "log_likelihood_ratio": 0.0,
        "eligible_n": 0,
        "win_n": 0,
        "last_decision": "CONTINUE",
        "last_evaluated_at_eligible_n": 0,
        "calibration_fingerprint": calibration_hash,
    }


def advance_sprt_after_outcome(
    *,
    test_id: str,
    outcome_record: dict[str, Any],
    calibration: CalibrationReport,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    """
    After a successful append (not duplicate_noop), update SPRT state.

    EXCLUDED observations do not advance SPRT. WIN/NOT_WIN advance eligible_n.
    Threshold check only when eligible_n % batch_size == 0 and eligible_n >= n_min.
    """
    if calibration.mae_protocol_id != outcome_record.get("mae_protocol_id"):
        raise ValueError("calibration mae_protocol_id mismatch vs outcome record")

    cal_hash = sha256_hex(calibration_report_fingerprint(calibration))
    state_path = sequential_state_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "sequential_state.json"
    state = load_state(test_id, artifacts_dir=artifacts_dir)

    sprt = state.get("sprt") or {}
    if sprt.get("calibration_fingerprint") and sprt["calibration_fingerprint"] != cal_hash:
        raise CorruptionError("calibration fingerprint changed mid-test — refuse to advance SPRT")

    oc = (outcome_record.get("outcome") or "").strip()
    if oc not in ("WIN", "NOT_WIN", "EXCLUDED"):
        raise ValueError(f"invalid outcome {oc!r}")

    if not sprt.get("calibration_fingerprint"):
        sprt = _default_sprt_block(cal_hash)

    if oc == "EXCLUDED":
        state["sprt"] = sprt
        _atomic_write_json(state_path, state)
        return {
            "sprt_eligible_n": int(sprt.get("eligible_n", 0)),
            "decision": "CONTINUE",
            "wilson": None,
            "evaluated": False,
            "reason": "excluded_skipped",
        }

    win = oc == "WIN"
    llr = float(sprt.get("log_likelihood_ratio", 0.0))
    llr += sprt_log_contribution(
        win=win,
        p0=calibration.p0,
        p1=calibration.p1,
    )
    eligible_n = int(sprt.get("eligible_n", 0)) + 1
    win_n = int(sprt.get("win_n", 0)) + (1 if win else 0)

    sprt["log_likelihood_ratio"] = llr
    sprt["eligible_n"] = eligible_n
    sprt["win_n"] = win_n
    sprt["calibration_fingerprint"] = cal_hash

    decision = "CONTINUE"
    evaluated = False
    wilson_report: dict[str, Any] | None = None

    if eligible_n >= calibration.n_min and eligible_n % calibration.batch_size == 0:
        evaluated = True
        decision = classify_sprt_decision(
            log_likelihood_ratio=llr,
            alpha=calibration.alpha,
            beta=calibration.beta,
        )
        lo, hi = _wilson(win_n, eligible_n)
        wilson_report = {
            "wins": win_n,
            "eligible_n": eligible_n,
            "win_rate_point": win_n / eligible_n if eligible_n else None,
            "wilson_95_lo": lo,
            "wilson_95_hi": hi,
            "note": "reporting_only_does_not_override_sprt",
        }
        sprt["last_decision"] = decision
        sprt["last_evaluated_at_eligible_n"] = eligible_n
        sprt["last_evaluated_at_utc"] = utc_now_iso()

    state["sprt"] = sprt
    _atomic_write_json(state_path, state)

    return {
        "sprt_eligible_n": eligible_n,
        "sprt_log_likelihood_ratio": llr,
        "decision": decision,
        "wilson": wilson_report,
        "evaluated": evaluated,
    }


def load_calibration_for_test(path: Path | None = None) -> CalibrationReport:
    p = path or calibration_report_path()
    return load_calibration_report(p)


def export_decision_snapshot(test_id: str, *, artifacts_dir: Path | None = None) -> dict[str, Any]:
    """Read-only snapshot for audit."""
    state = load_state(test_id, artifacts_dir=artifacts_dir)
    return {
        "schema_version": state.get("schema_version", STATE_SCHEMA_VERSION),
        "test_id": test_id,
        "sprt": state.get("sprt"),
        "event_count": len(state.get("event_content_hashes", {})),
    }


def commit_outcome(
    *,
    test_id: str,
    record: dict[str, Any],
    calibration: CalibrationReport,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Append outcome (with duplicate policy) and advance SPRT when append succeeded.

    Caller builds ``record`` via :func:`pair_evaluation.build_outcome_record`.
    """
    from .outcome_manifest import append_outcome_record

    r = append_outcome_record(record, test_id=test_id, artifacts_dir=artifacts_dir)
    if r["status"] == "duplicate_noop":
        return {"append": r, "sprt_advance": None}
    adv = advance_sprt_after_outcome(
        test_id=test_id,
        outcome_record=record,
        calibration=calibration,
        artifacts_dir=artifacts_dir,
    )
    return {"append": r, "sprt_advance": adv}
