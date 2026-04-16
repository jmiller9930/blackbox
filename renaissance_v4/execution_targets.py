"""
Execution target registry for Quant Research Kitchen (DV-ARCH-KITCHEN-EXECUTION-TARGET-055).

Only ``jupiter`` and ``blackbox`` are supported. Baseline artifacts are per-target; no cross-system fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EXECUTION_JUPITER = "jupiter"
EXECUTION_BLACKBOX = "blackbox"
ALLOWED = frozenset({EXECUTION_JUPITER, EXECUTION_BLACKBOX})

# Human labels for UI and reports
LABELS = {
    EXECUTION_JUPITER: "Jupiter",
    EXECUTION_BLACKBOX: "BlackBox",
}
BASELINE_COMPARED_LABELS = {
    EXECUTION_JUPITER: "Jupiter Baseline",
    EXECUTION_BLACKBOX: "BlackBox Baseline",
}
# Technical strategy / baseline tags returned in API payloads
BASELINE_TAGS = {
    EXECUTION_JUPITER: "RenaissanceV4_baseline_v1",
    EXECUTION_BLACKBOX: "BlackBox_baseline_v1",
}


def normalize_execution_target(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return EXECUTION_JUPITER
    if s in ALLOWED:
        return s
    raise ValueError(f"invalid_execution_target:{raw!r}")


def paths_for_execution_target(repo: Path, target: str) -> dict[str, Path]:
    """
    Same keys as :func:`renaissance_v4.ui_api.rv4_paths` where baseline files differ by target.
    """
    repo = repo.resolve()
    rv4 = repo / "renaissance_v4"
    base = {
        "root": rv4,
        "reports": rv4 / "reports",
        "state": rv4 / "state",
        "diag_post": rv4 / "reports" / "diagnostic_quality_post_DV013.md",
        "correction_q": rv4 / "reports" / "correction_quality_v1.md",
        "experiment_index": rv4 / "state" / "experiment_index.json",
        "job_queue": rv4 / "state" / "ui_job_queue.json",
        "experiments_dir": rv4 / "reports" / "experiments",
    }
    if target == EXECUTION_JUPITER:
        return {
            **base,
            "baseline_md": rv4 / "reports" / "baseline_v1.md",
            "baseline_mc_md": rv4 / "reports" / "monte_carlo" / "monte_carlo_baseline_v1_reference.md",
            "baseline_det": rv4 / "state" / "baseline_deterministic.json",
            "baseline_mc": rv4 / "state" / "baseline_monte_carlo_summary.json",
            "baseline_trades_json": rv4 / "reports" / "experiments" / "baseline_v1_trades.json",
        }
    if target == EXECUTION_BLACKBOX:
        return {
            **base,
            "baseline_md": rv4 / "reports" / "blackbox_baseline_v1.md",
            "baseline_mc_md": rv4 / "reports" / "monte_carlo" / "blackbox_monte_carlo_baseline_reference.md",
            "baseline_det": rv4 / "state" / "blackbox_baseline_deterministic.json",
            "baseline_mc": rv4 / "state" / "blackbox_baseline_monte_carlo_summary.json",
            "baseline_trades_json": rv4 / "reports" / "experiments" / "blackbox_baseline_v1_trades.json",
        }
    raise ValueError(f"unknown_execution_target:{target!r}")


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def baseline_artifacts_present(repo: Path, target: str) -> tuple[bool, str]:
    """
    Returns (True, "") if deterministic and/or Monte Carlo baseline artifacts exist for ``target``.
    Otherwise (False, human-readable reason). No silent fallback across targets.
    """
    p = paths_for_execution_target(repo, target)
    det_path = p["baseline_det"]
    mc_path = p["baseline_mc"]
    det = _read_json(det_path) if det_path.is_file() else None
    mc = _read_json(mc_path) if mc_path.is_file() else None

    det_ok = False
    if isinstance(det, dict):
        d = det.get("deterministic")
        if isinstance(d, dict) and len(d) > 0:
            det_ok = True

    mc_ok = False
    if isinstance(mc, dict):
        if isinstance(mc.get("deterministic"), dict) and len(mc["deterministic"]) > 0:
            mc_ok = True
        elif isinstance(mc.get("monte_carlo"), dict) and len(mc["monte_carlo"]) > 0:
            mc_ok = True

    if det_ok or mc_ok:
        return True, ""

    rel_det = p["baseline_det"].relative_to(repo.resolve())
    rel_mc = p["baseline_mc"].relative_to(repo.resolve())
    return (
        False,
        f"No baseline artifacts for {LABELS.get(target, target)}. "
        f"Expected at least one of: {rel_det}, {rel_mc} with deterministic or monte_carlo data.",
    )


def assert_baseline_for_intake(repo: Path, target: str) -> None:
    """Raises ValueError with a clear message if baseline is missing for evaluation."""
    ok, msg = baseline_artifacts_present(repo, target)
    if not ok:
        raise ValueError(msg)
