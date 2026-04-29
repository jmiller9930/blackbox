#!/usr/bin/env python3
"""
GT051 — Generalization / \"market rhymes\" report from GT048 artifacts (no trading-logic changes).

Reads ``student_learning_records_v1.jsonl`` produced by ``run_trade_cycle_gt048_v1.py`` and emits:

1. Near-match sensitivity — bucket by ``mean_similarity_top_v1`` (high / mid / low).
2. Regime split — ``perps_state_model_v1.structure_state`` → trend vs chop-like buckets.
3. EV bins — ``expected_value_risk_cost_v1.ev_best_value_v1`` vs Referee PnL.
4. Out-of-sample — pass2 rows ordered by ``decision_at_ms``: last 40%% as test.

Usage::

  PYTHONPATH=. python3 scripts/analyze_gt051_generalization_v1.py --job-id d9-generalization-proof-001
  PYTHONPATH=. python3 scripts/analyze_gt051_generalization_v1.py \\
    --store /path/to/student_learning_records_v1.jsonl \\
    --job-id my-job-id
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent


def _entry_reasoning(rec: dict[str, Any]) -> dict[str, Any]:
    so = rec.get("student_output")
    if not isinstance(so, dict):
        return {}
    ere = so.get("entry_reasoning_eval_v1")
    return ere if isinstance(ere, dict) else {}


def _referee_pnl(rec: dict[str, Any]) -> float | None:
    ref = rec.get("referee_outcome_subset")
    if not isinstance(ref, dict):
        return None
    try:
        return float(ref.get("pnl"))
    except (TypeError, ValueError):
        return None


def _student_action(rec: dict[str, Any]) -> str:
    so = rec.get("student_output")
    if not isinstance(so, dict):
        return ""
    return str(so.get("student_action_v1") or "").strip().lower()


def _pattern_memory(rec: dict[str, Any]) -> dict[str, Any]:
    ere = _entry_reasoning(rec)
    pme = ere.get("pattern_memory_eval_v1")
    return pme if isinstance(pme, dict) else {}


def _decision_at_ms(rec: dict[str, Any]) -> int:
    so = rec.get("student_output")
    if isinstance(so, dict):
        try:
            return int(so.get("decision_at_ms") or 0)
        except (TypeError, ValueError):
            pass
    return 0


def _is_gt050_avoid(rec: dict[str, Any]) -> bool:
    """Same structural gate as GT050 runner (pass2 memory-aware abstention)."""
    pme = _pattern_memory(rec)
    stats = pme.get("pattern_outcome_stats_v1") if isinstance(pme.get("pattern_outcome_stats_v1"), dict) else {}
    try:
        avg_pnl = float(stats.get("avg_pnl") or 0.0)
    except (TypeError, ValueError):
        avg_pnl = 0.0
    try:
        wins_frac = float(stats.get("wins_total_fraction_v1") or 1.0)
    except (TypeError, ValueError):
        wins_frac = 1.0
    try:
        cnt_st = int(stats.get("count") or 0)
    except (TypeError, ValueError):
        cnt_st = 0
    losing_history = avg_pnl < 0 or (cnt_st >= 3 and wins_frac < 0.5)
    try:
        mc = int(pme.get("matched_count_v1") or 0)
    except (TypeError, ValueError):
        mc = 0
    return _student_action(rec) == "no_trade" and mc >= 1 and losing_history


def _similarity_tier(mean_sim: float) -> str:
    if mean_sim >= 0.67:
        return "high"
    if mean_sim >= 0.35:
        return "mid"
    return "low"


def _regime_label(ere: dict[str, Any]) -> str:
    ps = ere.get("perps_state_model_v1") if isinstance(ere.get("perps_state_model_v1"), dict) else {}
    ss = str(ps.get("structure_state") or "").strip().lower()
    # Trend-seeking tape vs chop/range-like states (EMA/ATR-derived in perps_state_model_v1).
    if ss in ("trend", "breakout"):
        return "trend"
    return "chop"


def _ev_best(ere: dict[str, Any]) -> float | None:
    ev = ere.get("expected_value_risk_cost_v1")
    if not isinstance(ev, dict) or not ev.get("available_v1"):
        return None
    try:
        return float(ev.get("ev_best_value_v1"))
    except (TypeError, ValueError):
        return None


def analyze_gt051_generalization_v1(
    *,
    store_path: Path,
    job_id: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    with Path(store_path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    pass2 = f"{job_id}-pass2"
    p2 = [r for r in records if str(r.get("run_id") or "") == pass2]
    p2.sort(key=_decision_at_ms)

    # --- 1) Similarity buckets: loss avoided rate
    sim_stats: dict[str, dict[str, float]] = {}
    for tier in ("high", "mid", "low"):
        sim_stats[tier] = {"avoided": 0.0, "n": 0.0, "loss_avoided_rate": 0.0}

    for r in p2:
        pme = _pattern_memory(r)
        try:
            ms = float(pme.get("mean_similarity_top_v1") or 0.0)
        except (TypeError, ValueError):
            ms = 0.0
        tier = _similarity_tier(ms)
        sim_stats[tier]["n"] += 1.0
        if _is_gt050_avoid(r):
            sim_stats[tier]["avoided"] += 1.0

    for tier in sim_stats:
        n = sim_stats[tier]["n"]
        sim_stats[tier]["loss_avoided_rate"] = (sim_stats[tier]["avoided"] / n) if n > 0 else 0.0

    # --- 2) Regime split (Referee PnL aggregate)
    regime_trend_pnl = 0.0
    regime_trend_n = 0
    regime_chop_pnl = 0.0
    regime_chop_n = 0
    for r in p2:
        ere = _entry_reasoning(r)
        rp = _referee_pnl(r)
        if rp is None:
            continue
        tag = _regime_label(ere)
        if tag == "trend":
            regime_trend_pnl += rp
            regime_trend_n += 1
        else:
            regime_chop_pnl += rp
            regime_chop_n += 1

    # --- 3) EV bins (mean Referee PnL conditional on ev_best sign), pass2 only
    ev_pos_pnls: list[float] = []
    ev_neg_pnls: list[float] = []
    ev_zero_pnls: list[float] = []
    eps = 1e-9
    for r in p2:
        ere = _entry_reasoning(r)
        evb = _ev_best(ere)
        rp = _referee_pnl(r)
        if evb is None or rp is None:
            continue
        if evb > eps:
            ev_pos_pnls.append(rp)
        elif evb < -eps:
            ev_neg_pnls.append(rp)
        else:
            ev_zero_pnls.append(rp)

    def _avg(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    # --- 4) Out-of-sample (last 40% of pass2 chronologically)
    n = len(p2)
    split = int(math.floor(0.6 * n))
    test_slice = p2[split:] if n else []
    oos_pnl = sum((_referee_pnl(r) or 0.0) for r in test_slice)
    oos_avoided = sum(1 for r in test_slice if _is_gt050_avoid(r))

    high_r = sim_stats["high"]["loss_avoided_rate"]
    low_r = sim_stats["low"]["loss_avoided_rate"]

    avg_pos = _avg(ev_pos_pnls)
    avg_neg = _avg(ev_neg_pnls)

    acceptance = {
        "high_similarity_avoidance_gt_low": bool(high_r > low_r),
        "ev_positive_avg_pnl_gt_ev_negative": bool(
            avg_pos is not None and avg_neg is not None and avg_pos > avg_neg
        ),
        "out_of_sample_pnl_non_negative": bool(oos_pnl >= 0.0),
        "met": False,
    }
    acceptance["met"] = bool(
        acceptance["high_similarity_avoidance_gt_low"]
        and acceptance["ev_positive_avg_pnl_gt_ev_negative"]
        and acceptance["out_of_sample_pnl_non_negative"]
    )

    return {
        "job_id": job_id,
        "store_path": str(store_path.resolve()),
        "pass2_rows": len(p2),
        "similarity_high": {"loss_avoided_rate": round(high_r, 6)},
        "similarity_mid": {"loss_avoided_rate": round(sim_stats["mid"]["loss_avoided_rate"], 6)},
        "similarity_low": {"loss_avoided_rate": round(low_r, 6)},
        "similarity_buckets_detail": {
            k: {"n": int(sim_stats[k]["n"]), "avoided": int(sim_stats[k]["avoided"])}
            for k in ("high", "mid", "low")
        },
        "regime_trend": {"pnl": round(regime_trend_pnl, 10), "trade_count": regime_trend_n},
        "regime_chop": {"pnl": round(regime_chop_pnl, 10), "trade_count": regime_chop_n},
        "ev_positive": {"avg_pnl": avg_pos},
        "ev_negative": {"avg_pnl": avg_neg},
        "ev_near_zero_count": len(ev_zero_pnls),
        "out_of_sample": {"pnl": round(oos_pnl, 10), "loss_avoided_count": oos_avoided, "test_rows": len(test_slice)},
        "acceptance": acceptance,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-id", type=str, required=True, dest="job_id")
    ap.add_argument(
        "--store",
        type=str,
        default="",
        help="Path to student_learning_records_v1.jsonl (default: runtime/gt048_cycle/<job-id>/)",
    )
    args = ap.parse_args()
    jid = str(args.job_id).strip()
    if not jid:
        print("ERROR: --job-id required", file=sys.stderr)
        return 2

    if args.store:
        store = Path(args.store).expanduser()
    else:
        store = _REPO / "runtime" / "gt048_cycle" / jid / "student_learning_records_v1.jsonl"

    if not store.is_file():
        print(f"ERROR: store not found: {store}", file=sys.stderr)
        return 2

    rep = analyze_gt051_generalization_v1(store_path=store, job_id=jid)
    print(json.dumps(rep, indent=2))
    return 0 if rep.get("acceptance", {}).get("met") else 3


if __name__ == "__main__":
    raise SystemExit(main())
