"""
GT_DIRECTIVE_030 — Pattern memory & comprehension (deterministic, inside RM path).

``perps_pattern_signature_v1`` + **distance-based** similarity vs historical
``student_learning_records_v1.jsonl`` rows that carry compatible signatures.
Additive score nudge only — does not replace ``indicator_score`` /
``decision_synthesis_v1`` math beyond ``final_score`` composition.

GT053 — Similarity v2: weighted Euclidean distance on a normalized continuous feature vector
(ATR-normalized returns, EMA slope, RSI distance, volatility/structure); inverted to [0,1]
similarity (1 = identical). Legacy discrete bucket overlap remains available as
``pattern_similarity_score_v1`` for backward-compatible tests.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from statistics import pvariance
from typing import Any

SCHEMA_PERPS_PATTERN_SIGNATURE_V1 = "perps_pattern_signature_v1"
SCHEMA_PATTERN_MEMORY_EVAL_V1 = "pattern_memory_eval_v1"
SCHEMA_PATTERN_SIMILARITY_VECTOR_V2 = "pattern_similarity_vector_v2"

# Legacy discrete bucket weights (sum = 1.0)
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

# GT053 — distance weights on [0,1] normalized features (sum = 1.0)
_VECTOR_WEIGHTS_V2: dict[str, float] = {
    "ret3_n": 0.14,
    "ret5_n": 0.14,
    "ret10_n": 0.14,
    "trend_slope_n": 0.15,
    "rsi_mid_dist_n": 0.15,
    "volatility_norm_n": 0.14,
    "structure_n": 0.14,
}

_STRUCTURE_STATE_TO_N: dict[str, float] = {
    "chop": 0.22,
    "trend": 0.78,
    "breakout": 0.95,
    "exhaustion": 0.48,
}

_VOL_STATE_TO_N: dict[str, float] = {
    "low_volatility": 0.25,
    "normal_volatility": 0.52,
    "high_volatility": 0.88,
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


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _tanh01(x: float) -> float:
    return _clamp01((math.tanh(float(x)) + 1.0) / 2.0)


def build_pattern_similarity_vector_v2(
    *,
    indicator_context_eval_v1: dict[str, Any],
    perps_state_model_v1: dict[str, Any],
    bars: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """
    Normalized feature vector for distance-based similarity (entry-time features).

    Includes optional outcome-derived scalars for persistence on closed trades when passed via
    ``referee_outcome_subset``-style dict through future hooks; matching at entry uses the same
    keys with neutral placeholders when unknown.
    """
    ictx = indicator_context_eval_v1 if isinstance(indicator_context_eval_v1, dict) else {}
    ps = perps_state_model_v1 if isinstance(perps_state_model_v1, dict) else {}

    rsi = ictx.get("rsi_last")
    try:
        rsi_f = float(rsi) if rsi is not None and not (isinstance(rsi, float) and math.isnan(rsi)) else 50.0
    except (TypeError, ValueError):
        rsi_f = 50.0
    rsi_mid_dist_n = _clamp01(abs(rsi_f - 50.0) / 50.0)

    atr = float(ictx.get("atr_last") or 0.0)
    ema_now = float(ictx.get("ema_last") or 0.0)
    ema_prev = float(ictx.get("ema_prev") or ema_now)
    atr_safe = max(atr, 1e-12)

    closes: list[float] = []
    if isinstance(bars, list) and bars:
        try:
            closes = [float(b.get("close") or 0.0) for b in bars]
        except (TypeError, ValueError):
            closes = []

    last = closes[-1] if closes else float(ema_now)
    last_safe = max(abs(last), 1e-12)

    def _ret_atr_norm(k: int) -> float:
        if len(closes) <= k or k < 1:
            return 0.5
        prev = closes[-1 - k]
        if prev == 0:
            return 0.5
        raw_ret = (closes[-1] / prev) - 1.0
        denom = atr_safe / last_safe
        if denom <= 0:
            return 0.5
        z = raw_ret / denom
        return _tanh01(z * 0.85)

    ret3_n = _ret_atr_norm(3)
    ret5_n = _ret_atr_norm(5)
    ret10_n = _ret_atr_norm(10)

    slope_raw = (ema_now - ema_prev) / atr_safe
    trend_slope_n = _tanh01(slope_raw * 1.15)

    vs_raw = str(ictx.get("atr_volume_state") or "normal_volatility")
    vol_label_n = _VOL_STATE_TO_N.get(vs_raw, 0.52)
    atr_frac = min(1.0, atr_safe / last_safe * 85.0)
    volatility_norm_n = _clamp01(0.45 * vol_label_n + 0.55 * atr_frac)

    ss = str(ps.get("structure_state") or "chop").strip().lower()
    structure_n = _STRUCTURE_STATE_TO_N.get(ss, _STRUCTURE_STATE_TO_N["chop"])

    # Reserved / outcome-aligned slots — neutral at entry; populated when data exists elsewhere.
    mfe_mae_profile_n = 0.5
    bars_held_n = 0.0

    vec = {
        "schema": SCHEMA_PATTERN_SIMILARITY_VECTOR_V2,
        "contract_version": 1,
        "ret3_n": round(ret3_n, 6),
        "ret5_n": round(ret5_n, 6),
        "ret10_n": round(ret10_n, 6),
        "trend_slope_n": round(trend_slope_n, 6),
        "rsi_mid_dist_n": round(rsi_mid_dist_n, 6),
        "volatility_norm_n": round(volatility_norm_n, 6),
        "structure_n": round(structure_n, 6),
        "mfe_mae_profile_n": round(mfe_mae_profile_n, 6),
        "bars_held_n": round(bars_held_n, 6),
    }
    return vec


def _vector_from_signature_record_v2(psig: dict[str, Any]) -> dict[str, Any] | None:
    raw = psig.get("pattern_similarity_vector_v2")
    if isinstance(raw, dict) and str(raw.get("schema") or "") == SCHEMA_PATTERN_SIMILARITY_VECTOR_V2:
        return raw
    return None


def _fallback_vector_from_discrete_signature_v2(psig: dict[str, Any]) -> dict[str, Any]:
    """Approximate continuous vector from legacy bucket-only signatures (migration / old JSONL)."""

    def _buck(key: str, salt: str) -> float:
        s = str(psig.get(key) or "")
        h = hashlib.sha256((salt + "|" + s).encode()).digest()
        return int.from_bytes(h[:2], "big") / 65535.0

    return {
        "schema": SCHEMA_PATTERN_SIMILARITY_VECTOR_V2,
        "contract_version": 1,
        "ret3_n": round(_buck("rsi_bucket", "r3"), 6),
        "ret5_n": round(_buck("ema_trend_bucket", "r5"), 6),
        "ret10_n": round(_buck("atr_bucket", "r10"), 6),
        "trend_slope_n": round(_buck("trend_state", "ts"), 6),
        "rsi_mid_dist_n": round(_buck("rsi_bucket", "rsi"), 6),
        "volatility_norm_n": round(_buck("atr_bucket", "vol"), 6),
        "structure_n": round(_buck("structure_bucket", "st"), 6),
        "mfe_mae_profile_n": 0.5,
        "bars_held_n": 0.0,
    }


def resolve_pattern_similarity_vector_v2_for_record(
    psig: dict[str, Any],
    *,
    referee_outcome_subset: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Vector used when comparing a learning-record signature to the current bar packet.

    Prefer embedded v2 vector; else discrete fallback. Optionally refine outcome slots from subset.
    """
    base = _vector_from_signature_record_v2(psig)
    if base is None:
        base = _fallback_vector_from_discrete_signature_v2(psig)
    out = dict(base)
    sub = referee_outcome_subset if isinstance(referee_outcome_subset, dict) else {}
    mfe = sub.get("mfe")
    mae = sub.get("mae")
    try:
        mfe_f = float(mfe) if mfe is not None else 0.0
        mae_f = float(mae) if mae is not None else 0.0
    except (TypeError, ValueError):
        mfe_f = mae_f = 0.0
    if mfe_f > 0 or mae_f > 0:
        out["mfe_mae_profile_n"] = round(_clamp01(mfe_f / (mfe_f + mae_f + 1e-9)), 6)
    et = sub.get("entry_time_ms")
    ex = sub.get("exit_time_ms")
    try:
        if et is not None and ex is not None:
            dt = max(0, int(ex) - int(et))
            # Without candle TF here, only map duration → [0,1] softly
            out["bars_held_n"] = round(_clamp01(1.0 - math.exp(-dt / (3600.0 * 1000.0))), 6)
    except (TypeError, ValueError):
        pass
    return out


def pattern_similarity_distance_weighted_v2(a: dict[str, Any], b: dict[str, Any]) -> float:
    """
    Weighted Euclidean distance on v2 active dimensions (smaller = closer).
    Uses ``_VECTOR_WEIGHTS_V2`` keys only (entry-time generalization).
    """
    acc = 0.0
    for k, w in _VECTOR_WEIGHTS_V2.items():
        try:
            fa = float(a.get(k) if k in a else 0.5)
            fb = float(b.get(k) if k in b else 0.5)
        except (TypeError, ValueError):
            fa = fb = 0.5
        acc += float(w) * (fa - fb) ** 2
    return math.sqrt(acc)


def pattern_similarity_score_distance_v2(a: dict[str, Any], b: dict[str, Any]) -> float:
    """
    Continuous similarity in [0, 1] from weighted distance: 1 = identical, 0 = far.
    """
    d = pattern_similarity_distance_weighted_v2(a, b)
    raw = math.exp(-3.45 * d)
    return round(max(0.0, min(1.0, raw)), 6)


def build_perps_pattern_signature_v1(
    *,
    indicator_context_eval_v1: dict[str, Any],
    perps_state_model_v1: dict[str, Any],
    symbol: str,
    candle_timeframe_minutes: int,
    bars: list[dict[str, Any]] | None = None,
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

    psv2 = build_pattern_similarity_vector_v2(
        indicator_context_eval_v1=ictx,
        perps_state_model_v1=ps,
        bars=bars,
    )

    return {
        "schema": SCHEMA_PERPS_PATTERN_SIGNATURE_V1,
        "contract_version": 1,
        **core,
        "signature_hash_v1": sig_hash,
        "pattern_similarity_vector_v2": psv2,
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
    """Aggregate referee subset outcomes weighted by similarity (GT053)."""
    pnls: list[float] = []
    wins = 0
    w_sum = 0.0
    w_pnl_sum = 0.0
    w_win = 0.0
    for rec, sim in matched:
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        if "pnl" not in sub:
            continue
        p = float(sub.get("pnl") or 0.0)
        w = max(0.0, float(sim))
        pnls.append(p)
        if p > 0:
            wins += 1
        w_sum += w
        w_pnl_sum += w * p
        if p > 0:
            w_win += w
    n = len(pnls)
    wr = (wins / n) if n else 0.0
    avg = sum(pnls) / n if n else 0.0
    w_wr = (w_win / w_sum) if w_sum > 0 else 0.0
    w_avg = (w_pnl_sum / w_sum) if w_sum > 0 else 0.0
    var = pvariance(pnls) if n >= 2 else 0.0
    return {
        "schema": "pattern_outcome_stats_v1",
        "count": n,
        "wins_total_fraction_v1": round(wr, 6),
        "wins_similarity_weighted_fraction_v1": round(w_wr, 6),
        "avg_pnl": round(avg, 6),
        "avg_pnl_similarity_weighted_v1": round(w_avg, 6),
        "pnl_variance_v1": round(var, 8),
        "similarity_weight_sum_v1": round(w_sum, 6),
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
    Low sample → 0. Deterministic. Uses similarity-weighted win bias when available.
    """
    n = int(stats.get("count") or 0)
    if n < int(min_sample):
        return 0.0
    raw_wr = stats.get("wins_similarity_weighted_fraction_v1")
    if raw_wr is None:
        wr = float(stats.get("wins_total_fraction_v1") or 0.0)
    else:
        wr = float(raw_wr)
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
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build signature, scan store for historical signatures, distance-based similarity, stats, effect.
    """
    sig = build_perps_pattern_signature_v1(
        indicator_context_eval_v1=indicator_context_eval_v1,
        perps_state_model_v1=perps_state_model_v1,
        symbol=symbol,
        candle_timeframe_minutes=int(candle_timeframe_minutes),
        bars=bars,
    )
    cur_vec = (
        sig.get("pattern_similarity_vector_v2")
        if isinstance(sig.get("pattern_similarity_vector_v2"), dict)
        else {}
    )

    if not pattern_memory_enabled_v1():
        return {
            "schema": SCHEMA_PATTERN_MEMORY_EVAL_V1,
            "contract_version": 2,
            "similarity_metric_v1": "pattern_similarity_score_distance_v2",
            "disabled_reason_v1": "pattern_memory_disabled_by_env",
            "perps_pattern_signature_v1": sig,
            "matched_count_v1": 0,
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

    scored: list[tuple[dict[str, Any], float, float, dict[str, Any]]] = []
    for rec in rows:
        if rid_self and str(rec.get("run_id") or "").strip() == rid_self:
            continue
        if not _eligible_for_pattern_stats_v1(rec):
            continue
        psig = rec.get("perps_pattern_signature_v1")
        if not isinstance(psig, dict) or str(psig.get("schema") or "") != SCHEMA_PERPS_PATTERN_SIGNATURE_V1:
            continue
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        mem_vec = resolve_pattern_similarity_vector_v2_for_record(psig, referee_outcome_subset=sub)
        sim = pattern_similarity_score_distance_v2(cur_vec, mem_vec)
        dist = pattern_similarity_distance_weighted_v2(cur_vec, mem_vec)
        if sim < floor:
            continue
        scored.append((rec, sim, dist, mem_vec))

    scored.sort(key=lambda x: (x[2], str(x[0].get("record_id") or "")))
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

    matched_count_v1 = len(scored)

    top_payload = []
    for rec, sim, dist, _mv in top[:8]:
        psig = rec.get("perps_pattern_signature_v1")
        rid = str(rec.get("record_id") or "")
        sub = rec.get("referee_outcome_subset") if isinstance(rec.get("referee_outcome_subset"), dict) else {}
        top_payload.append(
            {
                "record_id": rid,
                "similarity_v1": sim,
                "distance_v2": round(dist, 6),
                "historical_signature_hash_v1": (psig or {}).get("signature_hash_v1") if isinstance(psig, dict) else None,
                "historical_pnl": sub.get("pnl"),
            }
        )

    return {
        "schema": SCHEMA_PATTERN_MEMORY_EVAL_V1,
        "contract_version": 2,
        "similarity_metric_v1": "pattern_similarity_score_distance_v2",
        "store_path_resolved_v1": str(sp),
        "perps_pattern_signature_v1": sig,
        "pattern_similarity_vector_v2": cur_vec,
        "similarity_floor_v1": floor,
        "matched_count_v1": int(matched_count_v1),
        "top_matches_v1": top_payload,
        "pattern_outcome_stats_v1": pst,
        "mean_similarity_top_v1": mean_sim,
        "pattern_effect_to_score_v1": eff,
        "min_sample_config_v1": min_n,
    }


__all__ = [
    "SCHEMA_PATTERN_MEMORY_EVAL_V1",
    "SCHEMA_PATTERN_SIMILARITY_VECTOR_V2",
    "SCHEMA_PERPS_PATTERN_SIGNATURE_V1",
    "build_pattern_similarity_vector_v2",
    "build_perps_pattern_signature_v1",
    "evaluate_pattern_memory_v1",
    "pattern_effect_to_score_v1",
    "pattern_memory_enabled_v1",
    "pattern_outcome_stats_v1",
    "pattern_similarity_distance_weighted_v2",
    "pattern_similarity_score_distance_v2",
    "pattern_similarity_score_v1",
    "resolve_pattern_similarity_vector_v2_for_record",
]
