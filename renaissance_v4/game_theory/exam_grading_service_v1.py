"""
Exam grading service — **GT_DIRECTIVE_007** / architecture **§11.5**.

Computes **E** (economic), **P** (process 0..1), and **PASS** from **exam_pack** grading config only
(no hardcoded thresholds). Reads committed ``decision_frame[]``, frame-0 deliberation export, and
downstream payloads; does not recompute indicators or re-derive decisions.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from renaissance_v4.game_theory.exam_deliberation_capture_v1 import ExamDeliberationPayloadV1
from renaissance_v4.game_theory.exam_state_machine_v1 import ExamPhase


class ExpectancyEconomicV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["expectancy"] = "expectancy"
    min_expectancy: float = Field(description="E passes when realized expectancy >= this (from pack).")
    realized_expectancy_context_key: str = Field(
        min_length=1,
        max_length=128,
        description="Key under each downstream frame ``payload.downstream_context``; last downstream wins.",
    )


class ProfitFactorDrawdownEconomicV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["profit_factor_drawdown"] = "profit_factor_drawdown"
    min_profit_factor: float = Field(gt=0)
    max_drawdown: float = Field(ge=0.0, le=1.0, description="Max allowed drawdown fraction (pack).")
    profit_factor_context_key: str = Field(min_length=1, max_length=128)
    max_drawdown_context_key: str = Field(min_length=1, max_length=128)


class NoTradeNeutralEconomicV1(BaseModel):
    """Economic dimension waived for NO_TRADE path; pack must explicitly select this mode."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["no_trade_neutral"] = "no_trade_neutral"
    neutral_economic_result: float = Field(default=1.0, description="Reported E scalar when waived (pack).")
    e_passes: bool = Field(default=True, description="Whether E leg counts as pass (pack; normally true).")


EconomicModeConfigV1 = Annotated[
    ExpectancyEconomicV1 | ProfitFactorDrawdownEconomicV1 | NoTradeNeutralEconomicV1,
    Field(discriminator="mode"),
]


class WinRatePassOverlayV1(BaseModel):
    """Optional: win rate may influence pass **only** when pack defines these (never sole condition alone)."""

    model_config = ConfigDict(extra="forbid")

    context_key: str = Field(min_length=1, max_length=128)
    min_win_rate: float = Field(ge=0.0, le=1.0)
    require_also_base_pass: bool = Field(
        default=True,
        description="When true, win-rate is AND with base E pass (never sole pass condition).",
    )


class ProcessWeightsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    p1_weight: float = Field(default=1.0 / 3.0, ge=0.0, le=1.0)
    p2_weight: float = Field(default=1.0 / 3.0, ge=0.0, le=1.0)
    p3_weight: float = Field(default=1.0 / 3.0, ge=0.0, le=1.0)


class ExamPackGradingConfigV1(BaseModel):
    """Pinned pack grading contract (dev store until pack registry exists)."""

    model_config = ConfigDict(extra="forbid")

    economic: EconomicModeConfigV1
    p_min: float = Field(ge=0.0, le=1.0)
    process_weights: ProcessWeightsV1 = Field(default_factory=ProcessWeightsV1)
    win_rate_overlay: WinRatePassOverlayV1 | None = None


_PACK_CONFIGS: dict[tuple[str, str], ExamPackGradingConfigV1] = {}
_LOCK = threading.Lock()


def register_exam_pack_grading_config_v1(
    exam_pack_id: str,
    exam_pack_version: str,
    config: ExamPackGradingConfigV1 | dict[str, Any],
) -> None:
    pid = exam_pack_id.strip()
    ver = exam_pack_version.strip()
    if not pid or not ver:
        raise ValueError("exam_pack_id_and_version_required")
    cfg = config if isinstance(config, ExamPackGradingConfigV1) else ExamPackGradingConfigV1.model_validate(config)
    with _LOCK:
        _PACK_CONFIGS[(pid, ver)] = cfg


def get_exam_pack_grading_config_v1(exam_pack_id: str, exam_pack_version: str) -> ExamPackGradingConfigV1 | None:
    with _LOCK:
        return _PACK_CONFIGS.get((exam_pack_id.strip(), exam_pack_version.strip()))


def reset_exam_pack_grading_configs_for_tests_v1() -> None:
    with _LOCK:
        _PACK_CONFIGS.clear()


def _grading_mode_label(economic: Any) -> str:
    return str(getattr(economic, "mode", "unknown"))


def _last_downstream_context(timeline_frames: list[dict[str, Any]]) -> dict[str, Any]:
    for fr in reversed(timeline_frames):
        if fr.get("frame_type") == "downstream":
            pl = fr.get("payload") or {}
            ctx = pl.get("downstream_context")
            if isinstance(ctx, dict):
                return ctx
    return {}


def _economic_grade_v1(
    *,
    enter: bool,
    economic: Any,
    timeline_frames: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Returns (economic_result dict, e_passes)."""
    mode = getattr(economic, "mode", None)
    if mode == "no_trade_neutral":
        if enter:
            raise ValueError("economic_mode_no_trade_neutral_requires_enter_false")
        nt = economic
        passes = bool(nt.e_passes)
        return (
            {
                "mode": "no_trade_neutral",
                "value": float(nt.neutral_economic_result),
                "passes": passes,
                "threshold": None,
            },
            passes,
        )
    if not enter:
        raise ValueError("economic_mode_requires_enter_true_for_downstream_e")
    ctx = _last_downstream_context(timeline_frames)
    if mode == "expectancy":
        ex = economic
        key = ex.realized_expectancy_context_key
        if key not in ctx:
            raise ValueError(f"missing_economic_context_key:{key}")
        raw = ctx[key]
        if not isinstance(raw, (int, float)):
            raise ValueError(f"economic_context_not_numeric:{key}")
        val = float(raw)
        passes = val >= float(ex.min_expectancy)
        return (
            {
                "mode": "expectancy",
                "value": val,
                "passes": passes,
                "threshold": float(ex.min_expectancy),
                "context_key": key,
            },
            passes,
        )
    if mode == "profit_factor_drawdown":
        pf = economic
        pk, dk = pf.profit_factor_context_key, pf.max_drawdown_context_key
        if pk not in ctx or dk not in ctx:
            raise ValueError(f"missing_economic_context_keys:{pk!r},{dk!r}")
        pfv = ctx[pk]
        ddv = ctx[dk]
        if not isinstance(pfv, (int, float)) or not isinstance(ddv, (int, float)):
            raise ValueError("economic_context_not_numeric_pf_dd")
        pfv_f = float(pfv)
        ddv_f = float(ddv)
        passes_pf = pfv_f >= float(pf.min_profit_factor)
        passes_dd = ddv_f <= float(pf.max_drawdown)
        passes = passes_pf and passes_dd
        return (
            {
                "mode": "profit_factor_drawdown",
                "profit_factor": pfv_f,
                "max_drawdown": ddv_f,
                "passes": passes,
                "threshold_profit_factor": float(pf.min_profit_factor),
                "threshold_max_drawdown": float(pf.max_drawdown),
            },
            passes,
        )
    raise ValueError(f"unknown_economic_mode:{mode!r}")


def _p1_hypothesis_completeness_v1(delib: ExamDeliberationPayloadV1) -> float:
    """0..1 — H1–H3 present with substance; H4 complete."""
    checks: list[bool] = []
    ids = {h.hypothesis_id for h in delib.hypotheses}
    for hid in ("H1", "H2", "H3"):
        h = next((x for x in delib.hypotheses if x.hypothesis_id == hid), None)
        if h is None:
            checks.append(False)
            continue
        checks.append(
            len(h.market_interpretation.strip()) >= 20
            and len(h.indicator_support.strip()) >= 20
            and len(h.falsification_condition.strip()) >= 20
        )
    checks.append(len(delib.h4.comparative_evaluation.strip()) >= 40)
    checks.append(len(delib.h4.bounded_reasoning.strip()) >= 40)
    checks.append(delib.h4.primary_selection in ids or delib.h4.primary_selection == "NO_TRADE")
    return sum(1 for c in checks if c) / max(len(checks), 1)


def _p2_decision_consistency_v1(delib: ExamDeliberationPayloadV1, enter: bool) -> float:
    """0..1 — sealed action aligns with H4 primary thesis arm."""
    sel = delib.h4.primary_selection
    if sel == "NO_TRADE":
        return 1.0 if not enter else 0.0
    hypo = next((h for h in delib.hypotheses if h.hypothesis_id == sel), None)
    if hypo is None:
        return 0.0
    ra = hypo.resulting_action
    if not enter:
        return 1.0 if ra == "NO_TRADE" else 0.0
    return 1.0 if ra in ("ENTER_LONG", "ENTER_SHORT") else 0.0


def _p3_mechanism_adherence_v1(timeline_frames: list[dict[str, Any]], enter: bool) -> float:
    """0..1 — downstream ordering, snapshots present for ENTER; monotone bar closes."""
    if not timeline_frames:
        return 0.0
    scores: list[float] = []
    ts_list = [str(f.get("timestamp") or "") for f in timeline_frames]
    scores.append(1.0 if ts_list == sorted(ts_list) else 0.0)
    downstream = [f for f in timeline_frames if f.get("frame_type") == "downstream"]
    if enter:
        scores.append(1.0 if len(downstream) >= 1 else 0.0)
        snaps_ok = all(
            isinstance((f.get("payload") or {}).get("price_snapshot"), dict)
            and isinstance(((f.get("payload") or {}).get("price_snapshot") or {}).get("close"), (int, float))
            for f in downstream
        )
        scores.append(1.0 if snaps_ok else 0.0)
    else:
        scores.append(1.0)
        scores.append(1.0 if len(downstream) == 0 else 0.0)
    return sum(scores) / max(len(scores), 1)


def _process_score_v1(
    delib: ExamDeliberationPayloadV1,
    enter: bool,
    timeline_frames: list[dict[str, Any]],
    weights: ProcessWeightsV1,
) -> tuple[float, dict[str, float]]:
    p1 = _p1_hypothesis_completeness_v1(delib)
    p2 = _p2_decision_consistency_v1(delib, enter)
    p3 = _p3_mechanism_adherence_v1(timeline_frames, enter)
    wsum = weights.p1_weight + weights.p2_weight + weights.p3_weight
    if wsum <= 0:
        raise ValueError("process_weights_sum_must_be_positive")
    p = (weights.p1_weight * p1 + weights.p2_weight * p2 + weights.p3_weight * p3) / wsum
    p = max(0.0, min(1.0, float(p)))
    return p, {"p1_hypothesis_completeness": p1, "p2_decision_consistency": p2, "p3_mechanism_adherence": p3}


def compute_exam_grade_v1(
    *,
    exam_unit_id: str,
    exam_phase: ExamPhase,
    enter: bool | None,
    exam_pack_id: str | None,
    exam_pack_version: str | None,
    timeline_committed: dict[str, Any] | None,
    deliberation_export: dict[str, Any] | None,
    pack_config: ExamPackGradingConfigV1,
) -> dict[str, Any]:
    """
    Full grade payload including audit. Raises ``ValueError`` with stable message prefixes for HTTP mapping.

    Preconditions (caller enforced): sealed timeline + deliberation present for non-placeholder grading.
    """
    if exam_pack_id is None or not str(exam_pack_id).strip():
        raise ValueError("missing_exam_pack_id")
    if exam_pack_version is None or not str(exam_pack_version).strip():
        raise ValueError("missing_exam_pack_version")
    if enter is None:
        raise ValueError("missing_enter_decision")
    if timeline_committed is None:
        raise ValueError("missing_committed_timeline")
    if deliberation_export is None:
        raise ValueError("missing_deliberation")
    if exam_phase.value in (
        ExamPhase.CREATED.value,
        ExamPhase.OPENING_SHOWN.value,
        ExamPhase.HYPOTHESES_H1_H3.value,
        ExamPhase.H4_COMPLETE.value,
    ):
        raise ValueError("exam_unit_incomplete_for_grading")

    frames = list(timeline_committed.get("decision_frames") or [])
    if len(frames) < 1:
        raise ValueError("timeline_missing_frames")

    delib = ExamDeliberationPayloadV1.model_validate(deliberation_export)

    econ = pack_config.economic
    econ_result, e_passes = _economic_grade_v1(enter=enter, economic=econ, timeline_frames=frames)

    win_overlay = pack_config.win_rate_overlay
    if win_overlay is not None:
        ctx = _last_downstream_context(frames)
        wk = win_overlay.context_key
        if wk not in ctx:
            raise ValueError(f"missing_win_rate_context_key:{wk}")
        wr = ctx[wk]
        if not isinstance(wr, (int, float)):
            raise ValueError("win_rate_context_not_numeric")
        wr_f = float(wr)
        win_ok = wr_f >= float(win_overlay.min_win_rate)
        if win_overlay.require_also_base_pass:
            e_passes = bool(e_passes and win_ok)
        else:
            e_passes = bool(win_ok)
        econ_result["win_rate"] = wr_f
        econ_result["win_rate_min"] = float(win_overlay.min_win_rate)

    p_val, p_breakdown = _process_score_v1(delib, enter, frames, pack_config.process_weights)
    passes = bool(e_passes and p_val >= float(pack_config.p_min))

    graded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return {
        "ok": True,
        "exam_unit_id": exam_unit_id.strip(),
        "exam_pack_id": exam_pack_id.strip(),
        "exam_pack_version": exam_pack_version.strip(),
        "economic_result": econ_result,
        "process_score": p_val,
        "pass": passes,
        "process_breakdown": p_breakdown,
        "audit": {
            "exam_pack_id": exam_pack_id.strip(),
            "exam_pack_version": exam_pack_version.strip(),
            "graded_at": graded_at,
            "grading_mode": _grading_mode_label(econ),
        },
    }


__all__ = [
    "ExamPackGradingConfigV1",
    "ExpectancyEconomicV1",
    "NoTradeNeutralEconomicV1",
    "ProfitFactorDrawdownEconomicV1",
    "ProcessWeightsV1",
    "WinRatePassOverlayV1",
    "compute_exam_grade_v1",
    "get_exam_pack_grading_config_v1",
    "register_exam_pack_grading_config_v1",
    "reset_exam_pack_grading_configs_for_tests_v1",
]
