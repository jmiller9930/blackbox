"""
run_memory.py

Append-only JSONL memory for replay runs: hypothesis + indicator context + Referee metrics.

Structured records support audit and optional **memory bundles** (see ``memory_bundle.py``) that
merge whitelisted parameters into the manifest before replay — those merges **do** affect outcomes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.context_memory import CONTEXT_SILO_ID, assess_indicator_context

SCHEMA = "renaissance_v4_run_memory_v1"
OUTCOME_MEASURES_SCHEMA = "outcome_measures_v1"


def build_outcome_measures_v1(referee: dict[str, Any] | None) -> dict[str, Any]:
    """
    Multi-dimensional outcome view derived from the same Referee row as ``referee`` in run_memory.

    **Binary WIN/LOSS counts** answer one question; **portfolio metrics** (PnL, expectancy, drawdown)
    answer others. This block makes “was anything good here?” legible without inventing a second source
    of truth — it only **interprets** fields already on the summary row.
    """
    base: dict[str, Any] = {
        "schema": OUTCOME_MEASURES_SCHEMA,
        "from_referee_row": bool(referee),
    }
    if not referee:
        base["lenses"] = {}
        base["positive_signals"] = []
        base["positive_any"] = False
        base["note"] = "No referee summary — run failed or summary missing."
        return base

    r = referee
    wins = r.get("wins")
    losses = r.get("losses")
    trades = r.get("trades")
    wr = r.get("win_rate")
    cum = r.get("cumulative_pnl")
    exp = r.get("expectancy")
    avg = r.get("average_pnl")
    mdd = r.get("max_drawdown")

    base["binary_scorecard"] = {
        k: v
        for k, v in (("wins", wins), ("losses", losses), ("trades", trades), ("win_rate", wr))
        if v is not None
    }
    base["portfolio"] = {
        k: v
        for k, v in (
            ("cumulative_pnl", cum),
            ("expectancy", exp),
            ("average_pnl", avg),
            ("max_drawdown", mdd),
        )
        if v is not None
    }

    lenses: dict[str, str] = {}
    signals: list[str] = []

    def _num(x: Any) -> float | None:
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return float(x)
        return None

    c = _num(cum)
    if c is not None:
        if c > 0:
            lenses["money"] = "positive"
            signals.append("cumulative_pnl_positive")
        elif c == 0:
            lenses["money"] = "flat"
            signals.append("cumulative_pnl_non_negative")
        else:
            lenses["money"] = "negative"

    e = _num(exp)
    if e is not None:
        if e > 0:
            lenses["edge"] = "positive"
            signals.append("expectancy_positive")
        else:
            lenses["edge"] = "non_positive"

    ap = _num(avg)
    if ap is not None and ap > 0:
        signals.append("average_trade_pnl_positive")

    wn = _num(wr)
    if wn is not None:
        if wn > 0.5:
            lenses["win_rate_vs_coinflip"] = "above"
            signals.append("win_rate_above_half")
        else:
            lenses["win_rate_vs_coinflip"] = "at_or_below"

    d = _num(mdd)
    if d is not None:
        # Convention: drawdown often stored as negative distance from peak; 0 means no DD in window.
        if d >= 0.0:
            lenses["drawdown"] = "none_or_flat"
            signals.append("no_negative_drawdown_in_metrics")
        else:
            lenses["drawdown"] = "experienced_drawdown"

    # De-dupe preserving order
    seen: set[str] = set()
    uniq = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            uniq.append(s)

    base["lenses"] = lenses
    base["positive_signals"] = uniq
    base["positive_any"] = len(uniq) > 0
    base["note"] = (
        "Lenses interpret the same Referee row — not a second ledger. "
        "win_rate is binary scorecard; money/edge/drawdown are separate questions."
    )
    return base


def build_decision_audit(
    *,
    prior_run_id: str | None,
    memory_bundle_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Explicit audit: what inputs drove execution vs metadata-only links.

    If ``memory_bundle_audit`` is set, parameters from a promoted **memory bundle** were merged into
    the manifest before replay — that **does** affect behavior for whitelisted keys (e.g. ATR).
    """
    pid = (prior_run_id or "").strip() or None
    loaded = memory_bundle_audit is not None
    out: dict[str, Any] = {
        "prior_outcomes_or_parameters_loaded_into_replay_engine": loaded,
        "prior_run_id_provided": pid,
        "memory_bundle": memory_bundle_audit,
    }
    if loaded:
        out["human_readable_summary"] = (
            "A **memory bundle** was merged into the manifest before replay. "
            "Keys listed in memory_bundle.keys_applied (e.g. ATR multiples) **changed execution** for this run. "
            "Signals, fusion math, and risk policy still come from the manifest and engine except for those merged keys."
        )
        out["if_prior_run_id_is_set"] = (
            f"You may also have set prior_run_id={pid!r} for traceability between experiments."
            if pid
            else "No prior_run_id; behavioral memory came only from the memory bundle merge."
        )
    else:
        out["human_readable_summary"] = (
            "Trade decisions came from: (1) manifest JSON on disk, "
            "(2) optional CLI/scenario ATR overrides (applied after any bundle), "
            "(3) bar data forward in time. "
            "No memory bundle was merged. run_memory JSONL / prior session folders are **not** auto-read to alter execution."
        )
        out["if_prior_run_id_is_set"] = (
            f"prior_run_id={pid!r} is metadata for your review only — it was **not** loaded as simulation input."
            if pid
            else "No prior_run_id was supplied."
        )
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_hypothesis_bundle(
    scenario: dict[str, Any] | None,
    *,
    hypothesis_cli: str | None = None,
    indicator_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Prefer explicit CLI args; else read ``agent_explanation.hypothesis`` and
    ``agent_explanation.indicator_context`` from a scenario dict.
    """
    hyp = (hypothesis_cli or "").strip()
    ctx: dict[str, Any] = dict(indicator_context or {})
    if scenario:
        ae = scenario.get("agent_explanation")
        if isinstance(ae, dict):
            if not hyp:
                h2 = ae.get("hypothesis")
                if isinstance(h2, str) and h2.strip():
                    hyp = h2.strip()
            if not ctx and isinstance(ae.get("indicator_context"), dict):
                ctx = dict(ae["indicator_context"])
    return {"hypothesis": hyp or None, "indicator_context": ctx or None}


def build_run_memory_record(
    *,
    source: str,
    manifest_path: str,
    json_summary_row: dict[str, Any] | None,
    scenario: dict[str, Any] | None = None,
    hypothesis_cli: str | None = None,
    indicator_context: dict[str, Any] | None = None,
    prior_run_id: str | None = None,
    atr_stop_mult: float | None = None,
    atr_target_mult: float | None = None,
    parallel_error: str | None = None,
    memory_bundle_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One JSON object suitable for a single JSONL line."""
    mp = Path(manifest_path).expanduser().resolve()
    bundle = extract_hypothesis_bundle(
        scenario,
        hypothesis_cli=hypothesis_cli,
        indicator_context=indicator_context,
    )
    run_id = str(uuid.uuid4())
    rec: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "manifest_path": str(mp),
        "manifest_sha256": sha256_file(mp) if mp.is_file() else None,
        "hypothesis": bundle["hypothesis"],
        "indicator_context": bundle["indicator_context"],
        "context_silo": CONTEXT_SILO_ID,
        "indicator_context_quality": assess_indicator_context(bundle["indicator_context"]),
        "prior_run_id": prior_run_id,
        "atr_stop_mult": atr_stop_mult,
        "atr_target_mult": atr_target_mult,
        "referee": json_summary_row,
        "outcome_measures": build_outcome_measures_v1(json_summary_row),
        "decision_audit": build_decision_audit(
            prior_run_id=prior_run_id,
            memory_bundle_audit=memory_bundle_audit,
        ),
        "post_mortem": {
            "why": None,
            "next_hypothesis": None,
            "note": "Fill after review; optional Anna/human — does not affect Referee.",
        },
    }
    if parallel_error:
        rec["error"] = parallel_error
    return rec


def append_run_memory(path: Path | str, record: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_run_memory_tail(path: Path | str, n: int = 20) -> list[dict[str, Any]]:
    """Last n JSON objects from JSONL (best-effort; loads whole file if small)."""
    p = Path(path)
    if not p.is_file():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    tail = lines[-n:] if n > 0 else lines
    out: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
