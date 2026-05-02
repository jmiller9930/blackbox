"""
FinQuant — Operator Decision Ledger

Generates a human-readable audit trail of every decision the module made:
  - OHLC + indicators at the decision bar
  - Market regime and trajectory context
  - Two hypotheses considered (per R-002)
  - Which ToT branch won and why
  - Memory records used (if any)
  - Outcome: win / loss / no_trade_correct / no_trade_missed
  - PnL on each trade

Output:
  - CSV: one row per decision — importable to Excel/Sheets
  - JSON: full structured detail for programmatic review
  - Markdown summary: human-readable narrative with key stats

Usage:
  python3 operator_ledger.py --loop-dir outputs/train_20260502_xxxxx --out ledger/
  python3 operator_ledger.py --loop-dir outputs/train_20260502_xxxxx --out ledger/ --format csv
  python3 operator_ledger.py --latest --output-dir outputs --out ledger/
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Ledger row builder
# ---------------------------------------------------------------------------

def _bar_summary(bar: dict[str, Any]) -> dict[str, Any]:
    """Extract OHLC + indicators from a candle dict."""
    close = float(bar.get("close", 0.0) or 0.0)
    atr = bar.get("atr_14")
    atr_pct = round(float(atr) / close * 100, 4) if atr and close > 0 else None
    return {
        "timestamp": bar.get("timestamp", ""),
        "open": bar.get("open"),
        "high": bar.get("high"),
        "low": bar.get("low"),
        "close": close,
        "volume": bar.get("volume"),
        "rsi_14": bar.get("rsi_14"),
        "ema_20": bar.get("ema_20"),
        "atr_14": atr,
        "atr_pct": atr_pct,
    }


def build_ledger_row(
    *,
    case_id: str,
    cycle: int,
    bar: dict[str, Any],
    decision: dict[str, Any],
    outcome: dict[str, Any],
    memory_used: list[dict[str, Any]],
    regime: str,
) -> dict[str, Any]:
    """Build one ledger row for a single decision."""
    bar_data = _bar_summary(bar)
    action = str(decision.get("action") or "NO_TRADE")
    source = str(decision.get("decision_source_v1") or decision.get("source") or "rule")
    thesis = str(decision.get("thesis_v1") or decision.get("thesis") or "")
    invalidation = str(decision.get("invalidation_v1") or decision.get("invalidation") or "")
    # confidence_band_v1 is a string ("high"/"medium"/"low") — map to float
    _band_map = {"high": 0.80, "medium": 0.60, "low": 0.35}
    raw_conf = decision.get("confidence_band_v1") or decision.get("confidence") or 0.0
    if isinstance(raw_conf, str):
        confidence = _band_map.get(raw_conf.lower(), 0.35)
    else:
        confidence = float(raw_conf)

    # Hypothesis fields — from R-002 normalized output (llm_adapter) or ToT branches
    h1_raw = decision.get("hypothesis_1_v1") or {}
    h2_raw = decision.get("hypothesis_2_v1") or {}
    confidence_spread = decision.get("confidence_spread_v1")
    r_multiple = decision.get("planned_r_multiple_v1")
    winning_branch = decision.get("llm_raw_action_v1") or ""

    # Fall back to tot_branches if present (RMv2 path)
    tot_branches = decision.get("tot_branches_v1") or []
    if not h1_raw and tot_branches:
        winner = max(tot_branches, key=lambda b: float(b.get("evidence_score") or 0))
        winning_branch = winner.get("branch", "")
        h1_raw = winner.get("hypothesis_1") or {}
        h2_raw = winner.get("hypothesis_2") or {}
        confidence_spread = winner.get("confidence_spread")
        r_multiple = winner.get("planned_r_multiple")

    h1 = {"thesis": str(h1_raw.get("thesis") or ""), "confidence": h1_raw.get("confidence")} if h1_raw else {}
    h2 = {"thesis": str(h2_raw.get("thesis") or ""), "confidence": h2_raw.get("confidence")} if h2_raw else {}

    # Outcome
    outcome_kind = str(outcome.get("outcome_kind_v1") or "")
    pnl = float(outcome.get("pnl_v1") or 0.0)
    verdict = str(outcome.get("verdict_v1") or "")

    # Memory
    mem_count = len(memory_used)
    mem_win_rates = [float(r.get("pattern_win_rate_v1") or 0) for r in memory_used]
    avg_mem_wr = round(sum(mem_win_rates) / len(mem_win_rates), 4) if mem_win_rates else None

    # Decision quality flag
    is_good = outcome_kind in ("win", "no_trade_correct")

    return {
        "cycle": cycle,
        "case_id": case_id,
        # OHLC + indicators
        "timestamp": bar_data["timestamp"],
        "open": bar_data["open"],
        "high": bar_data["high"],
        "low": bar_data["low"],
        "close": bar_data["close"],
        "volume": bar_data["volume"],
        "rsi_14": bar_data["rsi_14"],
        "ema_20": bar_data["ema_20"],
        "atr_14": bar_data["atr_14"],
        "atr_pct": bar_data["atr_pct"],
        "regime": regime,
        # Decision
        "action": action,
        "source": source,
        "thesis": thesis[:200],
        "invalidation": invalidation[:100],
        "confidence": confidence,
        # Hypotheses (R-002)
        "hypothesis_1": h1.get("thesis", "")[:150],
        "h1_confidence": h1.get("confidence"),
        "hypothesis_2": h2.get("thesis", "")[:150],
        "h2_confidence": h2.get("confidence"),
        "confidence_spread": confidence_spread,
        "winning_branch": winning_branch,
        "planned_r_multiple": r_multiple,
        # Memory
        "memory_records_used": mem_count,
        "avg_memory_win_rate": avg_mem_wr,
        # Outcome
        "outcome_kind": outcome_kind,
        "pnl": pnl,
        "verdict": verdict,
        "is_good_decision": is_good,
    }


# ---------------------------------------------------------------------------
# Extract decisions from a training loop output directory
# ---------------------------------------------------------------------------

def _derive_outcome(evaluation: dict[str, Any], actions: list[str]) -> dict[str, Any]:
    """
    Derive outcome_kind and verdict from evaluation.json fields.
    Works whether or not falsification data is present in the record.
    """
    entry_quality = evaluation.get("entry_quality_v1") or ""
    no_trade = evaluation.get("no_trade_correctness_v1") or ""
    final_status = evaluation.get("final_status_v1") or "INFO"

    has_entry = any(a in ("ENTER_LONG", "ENTER_SHORT") for a in actions)

    if has_entry:
        if entry_quality == "entered_as_expected" and final_status == "PASS":
            kind = "win"
        elif entry_quality in ("entered_as_expected",) and final_status == "FAIL":
            kind = "loss"
        elif entry_quality == "unexpected_entry":
            kind = "loss"
        else:
            kind = "win" if final_status == "PASS" else "loss"
    else:
        # No entry taken
        if no_trade in ("correctly_stood_down", "traded_as_expected") or entry_quality == "correctly_abstained":
            kind = "no_trade_correct"
        elif entry_quality == "missed_entry":
            kind = "no_trade_missed"
        else:
            kind = "no_trade_correct" if final_status != "FAIL" else "no_trade_missed"

    return {
        "outcome_kind_v1": kind,
        "pnl_v1": 0.0,  # PnL available in newer runs via shared JSONL
        "verdict_v1": final_status,
    }


def extract_from_loop_dir(loop_dir: Path) -> list[dict[str, Any]]:
    """
    Extract decision rows from a training loop output directory.
    Reads per-run decision_trace.json + evaluation.json.
    """
    report_path = loop_dir / "training_loop_report.json"
    if not report_path.exists():
        return []

    rows = []
    runs_dir = loop_dir / "runs"
    if not runs_dir.exists():
        return []

    # Build case_id → PnL map from shared JSONL if available
    shared_jsonl = loop_dir / "shared_learning_records_training.jsonl"
    pnl_by_case: dict[str, float] = {}
    outcome_by_case: dict[str, str] = {}
    if shared_jsonl.exists():
        for line in shared_jsonl.read_text().splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    cid = rec.get("case_id")
                    if cid and rec.get("pnl_v1") is not None:
                        pnl_by_case[cid] = float(rec["pnl_v1"])
                    if cid and rec.get("outcome_kind_v1"):
                        outcome_by_case[cid] = rec["outcome_kind_v1"]
                except Exception:
                    pass

    for cycle_dir in sorted(runs_dir.iterdir()):
        if not cycle_dir.is_dir():
            continue
        try:
            cycle_num = int(cycle_dir.name.split("_")[1])
        except (IndexError, ValueError):
            cycle_num = 0

        for run_dir in sorted(cycle_dir.iterdir()):
            if not run_dir.is_dir():
                continue

            trace_path = run_dir / "decision_trace.json"
            eval_path = run_dir / "evaluation.json"
            summary_path = run_dir / "run_summary.json"
            retrieval_path = run_dir / "retrieval_trace.json"

            if not trace_path.exists():
                continue

            try:
                decisions = json.loads(trace_path.read_text())
                if not isinstance(decisions, list):
                    decisions = [decisions]
            except Exception:
                continue

            evaluation = {}
            if eval_path.exists():
                try:
                    evaluation = json.loads(eval_path.read_text())
                except Exception:
                    pass

            summary = {}
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text())
                except Exception:
                    pass

            case_id = summary.get("case_id") or evaluation.get("case_id") or run_dir.name

            # Retrieve memory records used
            memory_used = []
            if retrieval_path.exists():
                try:
                    rt = json.loads(retrieval_path.read_text())
                    for entry in (rt.get("entries") or []):
                        if entry.get("reason") == "retrieved":
                            memory_used.append({
                                "record_id": entry.get("record_id"),
                                "pattern_win_rate_v1": None,
                            })
                except Exception:
                    pass

            # Derive outcome
            actions = [str(d.get("action") or "") for d in decisions]
            outcome = _derive_outcome(evaluation, actions)

            # Override with shared JSONL data if available (newer runs)
            if case_id in outcome_by_case:
                outcome["outcome_kind_v1"] = outcome_by_case[case_id]
            if case_id in pnl_by_case:
                outcome["pnl_v1"] = pnl_by_case[case_id]

            # Get bar context from first decision's input packet
            regime = "unknown"
            full_bar: dict[str, Any] = {"timestamp": case_id}
            if decisions:
                d0 = decisions[0]
                pkt = d0.get("input_packet_v1") or {}
                math = pkt.get("market_math_v1") or {}
                regime = pkt.get("regime_v1") or "unknown"
                # Use observed_context for actual timestamp
                obs_ctx = d0.get("observed_context_v1") or {}
                # Try to get actual bar timestamp from the case via run_summary
                bar_ts = summary.get("bar_timestamp") or case_id
                # Some runs store timestamp in observed_context
                if isinstance(obs_ctx, dict) and obs_ctx.get("last_timestamp"):
                    bar_ts = obs_ctx["last_timestamp"]
                full_bar = {
                    "timestamp": bar_ts,
                    "close": math.get("close_v1"),
                    "rsi_14": math.get("rsi_14_v1"),
                    "ema_20": None,
                    "atr_14": math.get("atr_14_v1"),
                    "volume": None,
                }

            for d in decisions:
                row = build_ledger_row(
                    case_id=case_id,
                    cycle=cycle_num,
                    bar=full_bar,
                    decision=d,
                    outcome=outcome,
                    memory_used=memory_used,
                    regime=regime,
                )
                rows.append(row)

    return rows


def extract_from_observations(loop_dir: Path) -> list[dict[str, Any]]:
    """
    Faster extraction from per-cycle observation JSONL files.
    These are written by training_loop.py directly.
    """
    rows = []

    # Find cycle report files
    report_path = loop_dir / "training_loop_report.json"
    if not report_path.exists():
        return []

    report = json.loads(report_path.read_text())
    cycle_reports = report.get("cycle_reports_v1") or []

    for cycle_report in cycle_reports:
        cycle_num = cycle_report.get("cycle_v1", 0)
        metrics = cycle_report.get("metrics_v1") or {}

    # Fall back to run dirs
    return extract_from_loop_dir(loop_dir)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_summary(
    rows: list[dict[str, Any]],
    loop_dir: Path,
    out_path: Path,
) -> None:
    if not rows:
        return

    # Aggregate stats
    by_cycle: dict[int, list[dict]] = {}
    for row in rows:
        c = row["cycle"]
        by_cycle.setdefault(c, []).append(row)

    lines = [
        f"# FinQuant Decision Audit Ledger",
        f"",
        f"**Source:** `{loop_dir.name}`  ",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  ",
        f"**Total decisions:** {len(rows)}",
        f"",
        f"---",
        f"",
        f"## Summary by Cycle",
        f"",
        f"| Cycle | Cases | Entries | Wins | Losses | Win Rate | No-Trade Correct | No-Trade Missed | Decision Quality | PnL |",
        f"|-------|-------|---------|------|--------|----------|-----------------|----------------|-----------------|-----|",
    ]

    for cycle_num, cycle_rows in sorted(by_cycle.items()):
        entries = [r for r in cycle_rows if r["action"] in ("ENTER_LONG", "ENTER_SHORT")]
        wins = sum(1 for r in cycle_rows if r["outcome_kind"] == "win")
        losses = sum(1 for r in cycle_rows if r["outcome_kind"] == "loss")
        ntc = sum(1 for r in cycle_rows if r["outcome_kind"] == "no_trade_correct")
        ntm = sum(1 for r in cycle_rows if r["outcome_kind"] == "no_trade_missed")
        decided = wins + losses
        win_rate = f"{wins/decided:.1%}" if decided else "N/A"
        good = wins + ntc
        dqr = f"{good/len(cycle_rows):.1%}" if cycle_rows else "N/A"
        pnl = sum(float(r.get("pnl") or 0) for r in cycle_rows)
        lines.append(
            f"| {cycle_num} | {len(cycle_rows)} | {len(entries)} | {wins} | {losses} | "
            f"{win_rate} | {ntc} | {ntm} | {dqr} | {pnl:+.4f} |"
        )

    lines += [
        f"",
        f"---",
        f"",
        f"## Prime Directive Metrics",
        f"",
        f"**Decision quality rate** = (wins + no_trade_correct) ÷ all opportunities",
        f"This is the correct metric per prime directive P-6: optimize across ALL opportunities, not just entries taken.",
        f"",
        f"**Positive expectancy** requires: avg_win × win_rate > avg_loss × loss_rate",
        f"",
    ]

    # Sample decisions table
    lines += [
        f"---",
        f"",
        f"## Decision Detail (first 20 rows)",
        f"",
        f"| Cycle | Case | Timestamp | Close | RSI | ATR% | Regime | Action | Source | Outcome | PnL | H1 conf | H2 conf | Spread |",
        f"|-------|------|-----------|-------|-----|------|--------|--------|--------|---------|-----|---------|---------|--------|",
    ]

    def _fmt(v, fmt=""):
        if v is None or v == "":
            return ""
        try:
            return format(v, fmt)
        except Exception:
            return str(v)

    for row in rows[:20]:
        lines.append(
            f"| {row['cycle']} | {row['case_id'][:20]} | {str(row.get('timestamp',''))[:16]} | "
            f"{_fmt(row.get('close'), '.4f')} | "
            f"{_fmt(row.get('rsi_14'), '.1f')} | "
            f"{_fmt(row.get('atr_pct'), '.3f')} | "
            f"{row.get('regime','')} | **{row.get('action','')}** | {row.get('source','')} | "
            f"{row.get('outcome_kind','')} | {_fmt(row.get('pnl'), '+.4f')} | "
            f"{_fmt(row.get('h1_confidence'), '.2f')} | "
            f"{_fmt(row.get('h2_confidence'), '.2f')} | "
            f"{_fmt(row.get('confidence_spread'), '.2f')} |"
        )

    lines += [
        f"",
        f"*Full detail in accompanying CSV and JSON files.*",
        f"",
        f"---",
        f"",
        f"## How to Read This Ledger",
        f"",
        f"- **Action**: ENTER_LONG = agent entered a long position; NO_TRADE = agent stood down; INSUFFICIENT_DATA = agent lacked confidence to decide (R-002 gate)",
        f"- **Source**: rule = deterministic rules; llm_tot = Qwen Tree of Thought; hybrid = memory-backed; guard_vetoed = rule overrode LLM",
        f"- **H1/H2 confidence**: the two competing hypotheses the agent considered (per R-002). Spread < 0.20 triggers INSUFFICIENT_DATA.",
        f"- **Outcome**: win = profitable entry; loss = losing entry; no_trade_correct = correctly stood down; no_trade_missed = missed good opportunity",
        f"- **Decision quality** = (wins + no_trade_correct) ÷ all cases — the honest metric across all market opportunities",
    ]

    out_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def find_latest_loop_dir(output_dir: Path) -> Path | None:
    candidates = [
        d for d in output_dir.iterdir()
        if d.is_dir() and d.name.startswith("train_")
        and (d / "training_loop_report.json").exists()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


def main() -> None:
    parser = argparse.ArgumentParser(description="FinQuant operator decision ledger")
    parser.add_argument("--loop-dir", help="Path to training loop output directory")
    parser.add_argument("--output-dir", default="prove_learning/finquant/unified/agent_lab/outputs",
                        help="Base output dir (used with --latest)")
    parser.add_argument("--latest", action="store_true", help="Use the most recent loop dir")
    parser.add_argument("--out", default="ledger", help="Output directory for ledger files")
    args = parser.parse_args()

    if args.latest:
        base = Path(args.output_dir)
        loop_dir = find_latest_loop_dir(base)
        if not loop_dir:
            print(f"No training loop dirs found under {base}", file=sys.stderr)
            sys.exit(1)
    elif args.loop_dir:
        loop_dir = Path(args.loop_dir)
    else:
        parser.error("Either --loop-dir or --latest is required")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[ledger] reading loop: {loop_dir}")
    rows = extract_from_observations(loop_dir)

    if not rows:
        print("[ledger] No decision rows extracted. Check loop dir structure.")
        sys.exit(1)

    print(f"[ledger] extracted {len(rows)} decision rows")

    # Write outputs
    csv_path = out_dir / f"{loop_dir.name}_decisions.csv"
    json_path = out_dir / f"{loop_dir.name}_decisions.json"
    md_path = out_dir / f"{loop_dir.name}_summary.md"

    write_csv(rows, csv_path)
    json_path.write_text(json.dumps(rows, indent=2))
    write_markdown_summary(rows, loop_dir, md_path)

    print(f"[ledger] CSV:      {csv_path}")
    print(f"[ledger] JSON:     {json_path}")
    print(f"[ledger] Markdown: {md_path}")

    # Print quick summary
    wins = sum(1 for r in rows if r["outcome_kind"] == "win")
    losses = sum(1 for r in rows if r["outcome_kind"] == "loss")
    ntc = sum(1 for r in rows if r["outcome_kind"] == "no_trade_correct")
    ntm = sum(1 for r in rows if r["outcome_kind"] == "no_trade_missed")
    good = wins + ntc
    total = len(rows)
    decided = wins + losses
    pnl = sum(float(r.get("pnl") or 0) for r in rows)

    print(f"\n{'='*50}")
    print(f"  Total opportunities : {total}")
    print(f"  Entries taken       : {decided} ({decided/total:.1%} of all)")
    print(f"  Wins                : {wins}")
    print(f"  Losses              : {losses}")
    print(f"  No-trade correct    : {ntc}")
    print(f"  No-trade missed     : {ntm}")
    print(f"  Win rate (entries)  : {wins/decided:.1%}" if decided else "  Win rate: N/A")
    print(f"  Decision quality    : {good/total:.1%} ({good}/{total} good decisions)")
    print(f"  Total PnL           : {pnl:+.4f}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
