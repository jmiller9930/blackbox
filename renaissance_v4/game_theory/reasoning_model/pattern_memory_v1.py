"""
GT_DIRECTIVE_030 — Pattern memory & comprehension (deterministic, inside RM path).

``perps_pattern_signature_v1`` + similarity vs historical ``student_learning_records_v1.jsonl`` rows
that carry ``perps_pattern_signature_v1``. Additive score nudge only — does not replace
``indicator_score`` / ``decision_synthesis_v1`` math beyond ``final_score`` composition.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from statistics import pvariance
from typing import Any

SCHEMA_PERPS_PATTERN_SIGNATURE_V1 = "perps_pattern_signature_v1"
SCHEMA_PATTERN_MEMORY_EVAL_V1 = "pattern_memory_eval_v1"

# Field weights for discrete bucket match (sum = 1.0)
_WEIGHTS: dict[str, float] = {
    "rsi_bucket": 0.15,
    "ema_trend_bucket": 0.15,
    "atr_bucket": 0.12,
    "volume_bucket": 0.12,
    "structure_bucket": 0.12,
    "trend_state": 0.12,
    "volatility_state": 0.10,
    "momentum_state": 0.12,
}


def pattern_memory_enabled_v1() -> bool:
    v = (os.environ.get("PATTERN_GAME_PATTERN_MEMORY_V1") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def pattern_memory_min_sample_v1() -> int:
    raw = (os.environ.get("PATTERN_GAME_PATTERN_MEMORY_MIN_SAMPLE") or "3").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 3
    return max(1, min(n, 64))


def pattern_memory_top_n_v1() -> int:
    raw = (os.environ.get("PATTERN_GAME_PATTERN_MEMORY_TOP_N") or "12").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 12
    return max(1, min(n, 256))


def pattern_memory_effect_cap_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_PATTERN_MEMORY_EFFECT_CAP") or "0.12").strip()
    try:
        c = float(raw)
    except ValueError:
        c = 0.12
    return max(0.0, min(c, 0.35))


def pattern_similarity_floor_v1() -> float:
    raw = (os.environ.get("PATTERN_GAME_PATTERN_MEMORY_SIMILARITY_FLOOR") or "0.35").strip()
    try:
        f = float(raw)
    except ValueError:
        f = 0.35
    return max(0.0, min(f, 1.0))


def build_perps_pattern_signature_v1(
    *,
    indicator_context_eval_v1: dict[str, Any],
    perps_state_model_v1: dict[str, Any],
    symbol: str,
    candle_timeframe_minutes: int,
) -> dict[str, Any]:
    """Normalized, hashable snapshot for pattern matching (deterministic)."""
    ictx = indicator_context_eval_v1 if isinstance(indicator_context_eval_v1, dict) else {}
    ps = perps_state_model_v1 if isinstance(perps_state_model_v1, dict) else {}

    rsi_b = str(ictx.get("rsi_state") or "neutral")
    ema_b = str(ictx.get("ema_trend") or "neutral_trend")
    atr_b = str(ictx.get("atr_volume_state") or "normal_volatility")
    vol_raw = ictx.get("volume_state")
    vol_b = "none" if vol_raw is None else str(vol_raw)

    trend_st = str(ps.get("trend_state") or "neutral")
    volreg_st = str(ps.get("volatility_state") or "normal_volatility")
    struct_st = str(ps.get("structure_state") or "unknown")
    mom_st = str(ps.get("momentum_state") or "neutral")

    core = {
        "symbol": str(symbol or "").strip().upper(),
        "timeframe_minutes": int(candle_timeframe_minutes),
        "rsi_bucket": rsi_b,
        "ema_trend_bucket": ema_b,
        "atr_bucket": atr_b,
        "volume_bucket": vol_b,
        "structure_bucket": struct_st,
        "trend_state": trend_st,
        "volatility_state": volreg_st,
        "momentum_state": mom_st,
    }
    canon = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    sig_hash = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:40]

    return {
        "schema": SCHEMA_PERPS_PATTERN_SIGNATURE_V1,
        "contract_version": 1,
        **core,
        "signature_hash_v1": sig_hash,
    }


def pattern_similarity_score_v1(a: dict[str, Any], b: dict[str, Any]) -> float:
    """
    Weighted [0,1] similarity on discrete buckets (deterministic; no embeddings).
    Requires same symbol and timeframe; else 0.
    """
    if str(a.get("schema") or "") != SCHEMA_PERPS_PATTERN_SIGNATURE_V1:
        return 0.0
    if str(b.get("schema") or "") != SCHEMA_PERPS_PATTERN_SIGNATURE_V1:
        return 0.0
    if str(a.get("symbol") or "").strip().upper() != str(b.get("symbol") or "").strip().upper():
        return 0.0
    if int(a.get("timeframe_minutes") or 0) != int(b.get("timeframe_minutes") or 0):
        return 0.0
    s = 0.0
    for k, w in _WEIGHTS.items():
        if str(a.get(k) or "") == str(b.get(k) or ""):
            s += w
    return round(max(0.0, min(1.0, s)), 6)


def _load_learning_records_for_pattern_memory_v1(store_path: Path) -> list[dict[str, Any]]:
    from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
        load_student_learning_records_v1,
    )

    if not store_path.is_file():
        return []
    return load_student_learning_records_v1(store_path)


def _eligible_for_pattern_stats_v1(rec: dict[str, Any]) -> bool:
    from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
        memory_retrieval_eligible_v1,
    )

    return bool(memory_retrieval_eligible_v1(rec))


def pattern_outcome_stats_v1(
    matched: list[tuple[dict[str, Any], float]],
) -> dict[str, Any]:
    """Aggregate referee subset outcomes for similar rows (unweighted on wins; sim listed per row)."""
    pnls: list[float] = []
    wins = 0
    for rec, _sim in matched:
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        if "pnl" not in sub:
            continue
        p = float(sub.get("pnl") or 0.0)
        pnls.append(p)
        if p > 0:
            wins += 1
    n = len(pnls)
    wr = (wins / n) if n else 0.0
    avg = sum(pnls) / n if n else 0.0
    var = pvariance(pnls) if n >= 2 else 0.0
    return {
        "schema": "pattern_outcome_stats_v1",
        "count": n,
        "wins_total_fraction_v1": round(wr, 6),
        "avg_pnl": round(avg, 6),
        "pnl_variance_v1": round(var, 8),
    }


def pattern_effect_to_score_v1(
    *,
    stats: dict[str, Any],
    mean_similarity: float,
    min_sample: int,
    cap: float,
) -> float:
    """
    Map historical outcomes + match quality to [-cap, cap] additive score contribution.
    Low sample → 0. Deterministic.
    """
    n = int(stats.get("count") or 0)
    if n < int(min_sample):
        return 0.0
    wr = float(stats.get("wins_total_fraction_v1") or 0.0)
    # Center around 0.5: winning history nudges positive.
    center = (wr - 0.5) * 2.0
    ms = max(0.0, min(1.0, float(mean_similarity)))
    raw = center * 0.28 * ms
    if n < min_sample + 2:
        raw *= 0.65
    raw = max(-cap, min(cap, raw))
    return round(raw, 6)


def evaluate_pattern_memory_v1(
    *,
    indicator_context_eval_v1: dict[str, Any],
    perps_state_model_v1: dict[str, Any],
    symbol: str,
    candle_timeframe_minutes: int,
    store_path: Path | str | None,
    current_run_id: str,
) -> dict[str, Any]:
    """
    Build signature, scan store for historical signatures, similarity, stats, effect.
    """
    sig = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=indicator_context_eval_v1,
        perps_state_model_v1=perps_state_model_v1,
        symbol=symbol,
        candle_timeframe_minutes=int(candle_timeframe_minutes),
    )
    if not pattern_memory_enabled_v1():
        return {
            "schema": SCHEMA_PATTERN_MEMORY_EVAL_V1,
            "contract_version": 1,
            "disabled_reason_v1": "pattern_memory_disabled_by_env",
            "perps_pattern_signature_v1": sig,
            "top_matches_v1": [],
            "pattern_outcome_stats_v1": {"schema": "pattern_outcome_stats_v1", "count": 0},
            "pattern_effect_to_score_v1": 0.0,
            "mean_similarity_top_v1": 0.0,
        }

    from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
        default_student_learning_store_path_v1,
    )

    sp = Path(store_path).expanduser().resolve() if store_path else default_student_learning_store_path_v1()
    rows = _load_learning_records_for_pattern_memory_v1(sp)
    rid_self = str(current_run_id or "").strip()
    floor = pattern_similarity_floor_v1()
    top_n = pattern_memory_top_n_v1()

    scored: list[tuple[dict[str, Any], float, dict[str, Any]]] = []
    for rec in rows:
        if rid_self and str(rec.get("run_id") or "").strip() == rid_self:
            continue
        if not _eligible_for_pattern_stats_v1(rec):
            continue
        psig = rec.get("perps_pattern_signature_v1")
        if not isinstance(psig, dict) or str(psig.get("schema") or "") != SCHEMA_PERPS_PATTERN_SIGNATURE_V1:
            continue
        sim = pattern_similarity_score_v1(sig, psig)
        if sim < floor:
            continue
        scored.append((rec, sim, psig))

    scored.sort(key=lambda x: (-x[1], str(x[0].get("record_id") or "")))
    top = scored[:top_n]
    matched = [(t[0], t[1]) for t in top]
    sims = [t[1] for t in matched]
    mean_sim = round(sum(sims) / len(sims), 6) if sims else 0.0

    pst = pattern_outcome_stats_v1(matched)
    min_n = pattern_memory_min_sample_v1()
    cap = pattern_memory_effect_cap_v1()
    eff = pattern_effect_to_score_v1(
        stats=pst,
        mean_similarity=mean_sim,
        min_sample=min_n,
        cap=cap,
    )

    top_payload = []
    for rec, sim in matched[:8]:
        psig = rec.get("perps_pattern_signature_v1")
        rid = str(rec.get("record_id") or "")
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        top_payload.append(
            {
                "record_id": rid,
                "similarity_v1": sim,
                "historical_signature_hash_v1": (psig or {}).get("signature_hash_v1") if isinstance(psig, dict) else None,
                "historical_pnl": sub.get("pnl"),
            }
        )

    return {
        "schema": SCHEMA_PATTERN_MEMORY_EVAL_V1,
        "contract_version": 1,
        "store_path_resolved_v1": str(sp),
        "perps_pattern_signature_v1": sig,
        "similarity_floor_v1": floor,
        "top_matches_v1": top_payload,
        "pattern_outcome_stats_v1": pst,
        "mean_similarity_top_v1": mean_sim,
        "pattern_effect_to_score_v1": eff,
        "min_sample_config_v1": min_n,
    }


__all__ = [
    "SCHEMA_PATTERN_MEMORY_EVAL_V1",
    "SCHEMA_PERPS_PATTERN_SIGNATURE_V1",
    "build_perps_pattern_signature_v1",
    "evaluate_pattern_memory_v1",
    "pattern_effect_to_score_v1",
    "pattern_memory_enabled_v1",
    "pattern_outcome_stats_v1",
    "pattern_similarity_score_v1",
]
