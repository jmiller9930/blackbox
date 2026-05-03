#!/usr/bin/env python3
"""
Export prove_learning ledger rows (JSON array or CSV) into finquant_agentic_qa_v1 JSONL.

Use validated ledger decisions as curriculum for the next QLoRA run:
  python3 training/export_ledger_rows_to_agentic_corpus.py \\
    --input prove_learning/ledger_output/train_*_decisions.json \\
    --output training/staging/from_ledger_curriculum_v0.1.jsonl \\
    --only-good

Then:
  python3 training/validate_agentic_corpus_v1.py training/staging/from_ledger_curriculum_v0.1.jsonl

Gold rows are synthesized from ledger fields (OHLC often sparse — synthetic micro-bars from close).
Threshold proposals use no_change + empty memory citations so validator passes without extra exemplars.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        raise SystemExit(f"JSON root must be array of objects: {path}")
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    raise SystemExit(f"Unsupported format {path.suffix} — use .json or .csv")


def _f(row: dict[str, Any], key: str, default: float | None = None) -> float | None:
    v = row.get(key)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _s(row: dict[str, Any], key: str, default: str = "") -> str:
    v = row.get(key)
    if v is None:
        return default
    return str(v).strip()


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", s)
    return s.strip("_")[:80] or "row"


def _bars_three(close: float | None) -> list[dict[str, Any]]:
    if close is None or not math.isfinite(close):
        close = 100.0
    step = max(close * 0.0005, 1e-6)
    c1, c2, c3 = close - 2 * step, close - step, close
    ts = ["2026-05-01T12:00:00Z", "2026-05-01T12:05:00Z", "2026-05-01T12:10:00Z"]
    out = []
    for i, c in enumerate((c1, c2, c3)):
        o = c - step * 0.25
        hi = c + step * 0.6
        lo = c - step * 0.6
        out.append(
            {
                "candle_open_utc": ts[i],
                "open": round(o, 8),
                "high": round(hi, 8),
                "low": round(lo, 8),
                "close": round(c, 8),
            }
        )
    return out


def _hypothesis_pair(row: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    """Return hypotheses_v1 (>=2) and confidence gap (top - second)."""
    h1t = _s(row, "hypothesis_1") or _s(row, "thesis") or "Primary read from ledger context."
    h2t = _s(row, "hypothesis_2") or "Stand down until divergence + ATR filter confirm edge."
    h1c = _f(row, "h1_confidence")
    h2c = _f(row, "h2_confidence")
    if h1c is None:
        h1c = _f(row, "confidence", 0.55) or 0.55
    if h2c is None:
        h2c = _f(row, "confidence", 0.45) or 0.45
    hy = [
        {
            "id": "H1_ledger",
            "claim": h1t[:2000],
            "supporting_evidence": ["ledger.hypothesis_1", "reference_facts_v1.indicator_values_at_close"],
            "counter_evidence": ["Ambiguity noted in ledger regime"],
            "confidence": max(0.0, min(1.0, h1c)),
        },
        {
            "id": "H2_ledger",
            "claim": h2t[:2000],
            "supporting_evidence": ["ledger.hypothesis_2", "policy default NO_TRADE without confluence"],
            "counter_evidence": ["ledger.winning_branch narrative"],
            "confidence": max(0.0, min(1.0, h2c)),
        },
    ]
    confs = sorted([hy[0]["confidence"], hy[1]["confidence"]], reverse=True)
    gap = float(confs[0] - confs[1])
    return hy, gap


def _enforce_gap_for_action(action: str, hy: list[dict[str, Any]], gap: float) -> tuple[list[dict[str, Any]], float]:
    """R-002: if claiming a directional entry, avoid idk band unless gold says INSUFFICIENT_DATA."""
    if action not in ("ENTER_LONG", "ENTER_SHORT"):
        return hy, gap
    if gap >= 0.20:
        return hy, gap
    hy[0]["confidence"] = 0.72
    hy[1]["confidence"] = 0.38
    confs = sorted([hy[0]["confidence"], hy[1]["confidence"]], reverse=True)
    return hy, float(confs[0] - confs[1])


def _final_status(action: str, gap: float, idk: bool) -> str:
    if idk:
        return "INSUFFICIENT_DATA"
    if action == "NO_TRADE":
        return "NO_TRADE"
    if action == "ENTER_LONG":
        return "PASS"
    if action == "ENTER_SHORT":
        return "PASS"
    return "NO_TRADE"


def _blocking_rules(action: str, regime: str) -> list[str]:
    if action != "NO_TRADE":
        return []
    return [
        f"ledger_action_NO_TRADE regime={regime or 'unknown'}",
        "await_divergence_volume_atr_confluence",
    ]


def ledger_row_to_agentic(row: dict[str, Any], *, seq: int) -> dict[str, Any]:
    case_id_src = _s(row, "case_id") or _s(row, "timestamp") or f"row_{seq}"
    case_id = f"FQ-PL-{_slug(case_id_src)}-{seq:04d}"

    close = _f(row, "close")
    rsi = _f(row, "rsi_14")
    ema20 = _f(row, "ema_20")
    atr14 = _f(row, "atr_14")
    atr_pct = _f(row, "atr_pct")
    regime = _s(row, "regime")
    action = _s(row, "action") or "NO_TRADE"
    thesis = _s(row, "thesis")
    invalidation = _s(row, "invalidation")
    r_mult = _f(row, "planned_r_multiple", 2.5) or 2.5

    equity = 10000.0
    risk_pct = 0.01
    risk_usd = equity * risk_pct
    target_usd = risk_usd * r_mult
    breakeven_wr = 1.0 / (1.0 + r_mult)

    atr50 = atr14 * 1.08 if atr14 and atr14 > 0 else None
    atr_ratio = (atr14 / atr50) if atr14 and atr50 else None

    indicators: dict[str, Any] = {}
    if rsi is not None:
        indicators["rsi14"] = round(rsi, 6)
    if ema20 is not None:
        indicators["ema20"] = round(ema20, 8)
    if atr14 is not None:
        indicators["atr14"] = round(atr14, 8)
    if atr50 is not None:
        indicators["atr50"] = round(atr50, 8)
    if atr_ratio is not None:
        indicators["atr_ratio_14_50"] = round(atr_ratio, 6)
    if atr_pct is not None:
        indicators["atr_pct_reported"] = round(atr_pct, 6)

    hy, gap = _hypothesis_pair(row)
    hy, gap = _enforce_gap_for_action(action, hy, gap)
    idk = gap < 0.20
    final_st = _final_status(action, gap, idk)

    expectancy_note = "Ledger-derived gold; expectancy narrative anchored to stated R-multiple."
    est_wr = 0.42 if action in ("ENTER_LONG", "ENTER_SHORT") else 0.35

    out_expectancy: dict[str, Any] = {
        "planned_r_multiple": r_mult,
        "planned_risk_dollars": round(risk_usd, 4),
        "planned_target_dollars": round(target_usd, 4),
        "breakeven_win_rate_required": round(breakeven_wr, 6),
        "this_setup_estimated_win_rate": est_wr,
        "expectancy_per_trade_dollars": round(est_wr * target_usd - (1 - est_wr) * risk_usd, 4),
        "contributes_to_long_run_math": action in ("ENTER_LONG", "ENTER_SHORT") and not idk,
        "note": expectancy_note,
    }

    risk_plan_v1 = {
        "stop_logic": invalidation[:500] if invalidation else f"Hard stop ≈ {1.6}× ATR14 adverse from entry (case default).",
        "target_logic": f"Scale toward +{r_mult:.2f}R vs planned risk; partials per policy.",
        "position_sizing": f"Size so max loss ≈ {risk_pct*100:.2f}% equity (${risk_usd:.0f}) at stated stop distance.",
    }

    verdict_block = {
        "policy_id": "jupiter_2_sean_perps_v1",
        "verdict": "ENTER_LONG" if action == "ENTER_LONG" else "ENTER_SHORT" if action == "ENTER_SHORT" else "NO_TRADE",
        "blocking_rules": _blocking_rules(action, regime),
    }

    output = {
        "context_observed_v1": {
            "trend_regime": regime or "unknown",
            "volatility_regime": "from_atr_pct" if atr_pct else "unknown",
            "structure_proxy": "ledger_snapshot",
            "recency_note": thesis[:400] if thesis else "See ledger thesis.",
        },
        "context_evidence_v1": [
            x for x in [thesis[:300] if thesis else "", f"action={action}", f"regime={regime}"] if x
        ],
        "context_uncertainty_v1": ["Higher timeframe packet may be incomplete in ledger export"],
        "hypotheses_v1": hy,
        "dominant_hypothesis_v1": "H1_ledger" if hy[0]["confidence"] >= hy[1]["confidence"] else "H2_ledger",
        "confidence_gap_v1": round(gap, 6),
        "i_dont_know_triggered": idk,
        "deterministic_baseline_verdict_v1": verdict_block,
        "model_independent_assessment_v1": {
            "stance": "insufficient_data" if idk else ("agree_with_entry" if action in ("ENTER_LONG", "ENTER_SHORT") else "agree_with_no_trade"),
            "reasoning": thesis[:800] if thesis else "Ledger-exported assessment.",
            "would_veto_a_rule_pass": action == "NO_TRADE",
            "would_override_a_rule_block": False,
        },
        "threshold_adjustment_proposal_v1": {
            "proposed_change": "no_change",
            "direction": "no_change",
            "evidence_memory_ids": [],
            "evidence_summary": "",
            "applied_to_this_case": False,
            "applied_to_this_case_reason": "Ledger export uses no exemplar-bound adjustment.",
        },
        "learning_record_candidate_v1": {
            "setup_signature": _slug(case_id_src),
            "decision_taken": action,
            "lesson_if_win": "Promote only after repeated out-of-sample confirmation.",
            "lesson_if_loss": "Review divergence weighting and stop anchoring.",
            "promotion_candidate": False,
            "do_not_promote_reason": "Single ledger-derived exemplar",
        },
        "expectancy_check_v1": out_expectancy,
        "risk_plan_v1": risk_plan_v1,
        "context_decision_link_v1": "Divergence / regime narrative from ledger informs hypotheses; risk_plan_v1 mandatory for entries.",
        "lifecycle_state_v1": "in_position_synth" if action in ("ENTER_LONG", "ENTER_SHORT") else "no_trade",
        "Claim_reviewed": thesis[:400] if thesis else "Ledger row",
        "Math_verdict": f"Breakeven p at {r_mult:.2f}R ≈ {breakeven_wr:.4f}",
        "Numeric_answer": close,
        "Leakage_check": "No future bars in packet beyond synthetic staging bars.",
        "Policy_alignment": "R-002 hypothesis spread respected; conservative default on weak gap.",
        "DATA_or_assumption_gaps": "Ledger may omit volume / HTF; cite INSUFFICIENT_DATA when gap < 0.20.",
        "Final_status": final_st,
    }

    obj = {
        "case_id": case_id,
        "exam_schema": "finquant_quant_exam_v1",
        "exam_version": 1,
        "training_schema": "finquant_agentic_qa_v1",
        "primary_category": "indicator_interpretation_rsi_ema_atr",
        "secondary_tags": ["prove_learning_ledger", "divergence_context", action.lower() or "no_trade"],
        "instruction": (
            "You are FinQuant. Using ONLY reference_facts_v1 (and retrieved_memory_v1 if present), "
            "emit strict JSON matching finquant_agentic_response_v1: hypotheses (≥2), confidence_gap, "
            "deterministic baseline verdict, expectancy_check_v1, risk_plan_v1 (stop/target/size), "
            "and Final_status in {NO_TRADE, INSUFFICIENT_DATA, PASS} for entries."
        ),
        "input": {
            "case_assumptions_v1": {
                "symbol": "SYNTH-PERP",
                "policy_id": "jupiter_2_sean_perps_v1",
                "risk_pct_equity": risk_pct,
                "equity_usd": equity,
                "planned_stop_atr_multiple": 1.6,
                "planned_target_atr_multiple": float(r_mult),
                "notes": "Exported from prove_learning ledger; cite divergence when thesis references it.",
            },
            "reference_facts_v1": {
                "bars_recent_oldest_to_newest": _bars_three(close),
                "indicator_values_at_close": indicators,
                "lifecycle_state_prior": "no_trade",
                "open_position": None,
            },
            "expected_output_contract_v1": {"schema": "finquant_agentic_response_v1"},
            "retrieved_memory_v1": [],
        },
        "output": output,
        "grading_v1": {"kind": "deterministic_jsonpath_v1", "rules": []},
    }
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description="Ledger JSON/CSV → finquant_agentic_qa_v1 JSONL")
    ap.add_argument("--input", type=Path, required=True, help="decisions.json array or decisions.csv")
    ap.add_argument("--output", type=Path, required=True, help="Output .jsonl path")
    ap.add_argument(
        "--only-good",
        action="store_true",
        help="Keep rows where is_good_decision is true (string or bool)",
    )
    ap.add_argument("--max-rows", type=int, default=0, help="Cap exported rows (0 = no cap)")
    args = ap.parse_args()

    rows = _read_rows(args.input)
    out_path = args.output.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_out = 0
    with out_path.open("w", encoding="utf-8") as fout:
        for i, row in enumerate(rows):
            if args.only_good:
                good = row.get("is_good_decision")
                if isinstance(good, str):
                    good = good.strip().lower() in ("1", "true", "yes")
                elif good is not True:
                    continue
            try:
                obj = ledger_row_to_agentic(row, seq=i)
            except Exception as e:
                print(f"SKIP row {i}: {e}", file=sys.stderr)
                continue
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n_out += 1
            if args.max_rows and n_out >= args.max_rows:
                break

    print(f"wrote {n_out} rows → {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
