"""Anna intelligence visibility — operator-facing status derived from real runtime signals.

Maps to advisor directive: context, learning, LLM, decisioning, baseline comparison,
effectiveness summary, phase story, and honest gap disclosure (W8 / subsystems).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


def _env_llm_on() -> bool:
    return os.environ.get("ANNA_USE_LLM", "1").strip().lower() not in ("0", "false", "no")


def _market_db_has_bars(repo: Path, market_db: Path | None) -> tuple[bool, str]:
    p = market_db or (repo / "data" / "sqlite" / "market_data.db")
    if not p.is_file():
        return False, f"market_data.db missing at {p}"
    try:
        conn = sqlite3.connect(str(p))
        try:
            cur = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='market_bars_5m'"
            )
            if cur.fetchone()[0] == 0:
                return False, "market_bars_5m table missing"
            n = conn.execute("SELECT COUNT(*) FROM market_bars_5m").fetchone()[0]
            if n <= 0:
                return False, "market_bars_5m empty"
            return True, f"{int(n)} bars in {p.name}"
        finally:
            conn.close()
    except sqlite3.Error as e:
        return False, f"sqlite error: {e}"


def _trade_chain_has_economic_anna(tc: dict[str, Any]) -> tuple[bool, bool]:
    """Returns (any_anna_cell, any_economic_anna)."""
    any_anna = False
    economic = False
    rows = tc.get("rows") or []
    if not isinstance(rows, list):
        return False, False
    for r in rows:
        if str(r.get("chain_kind") or "") not in ("anna_test", "anna_strategy"):
            continue
        cells = r.get("cells") or {}
        if not isinstance(cells, dict):
            continue
        for _mid, c in cells.items():
            if not isinstance(c, dict):
                continue
            any_anna = True
            mode = str(c.get("mode") or "")
            pnl = c.get("pnl_usd")
            if mode in ("live", "paper") and pnl is not None:
                economic = True
    return any_anna, economic


def _sprt_promotion_hint(seq: dict[str, Any]) -> str | None:
    s = seq.get("last_sprt_decision")
    if s is None and isinstance(seq.get("last_tick_summary"), dict):
        s = (seq.get("last_tick_summary") or {}).get("last_sprt")
    if isinstance(s, dict):
        return str(s.get("decision") or s.get("status") or "") or None
    if isinstance(s, str) and s.strip():
        return s.strip()
    return None


def build_intelligence_visibility(
    *,
    repo_root: Path,
    seq: dict[str, Any],
    trade_chain: dict[str, Any],
    operator_trading: dict[str, Any],
    learning_summary: dict[str, Any] | None,
    pyth_snapshot: dict[str, Any],
    market_db_path: str | None,
    training_state: dict[str, Any] | None,
    llm_preflight_from_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Assemble plain-language operator visibility from **existing** bundle inputs.
    Does not invent Online without a backing signal.
    """
    ts = training_state if isinstance(training_state, dict) else {}
    lp = llm_preflight_from_state if isinstance(llm_preflight_from_state, dict) else {}

    md_ok, md_detail = _market_db_has_bars(repo_root, Path(market_db_path) if market_db_path else None)
    pyth_age = pyth_snapshot.get("age_seconds")
    pyth_ok = pyth_snapshot.get("status") in ("ok", "healthy", "running", None) and (
        pyth_age is None or (isinstance(pyth_age, (int, float)) and pyth_age < 180)
    )

    if md_ok and pyth_ok:
        ctx_label = "Online"
        ctx_detail = f"Market bars: {md_detail}. Pyth probe age {pyth_age}s acceptable."
    elif md_ok or pyth_ok:
        ctx_label = "Partial"
        ctx_detail = (
            f"{'OK: ' + md_detail if md_ok else 'Bars: ' + md_detail}. "
            f"{'Pyth OK' if pyth_ok else 'Pyth stale or missing — check Hermes artifact'}."
        )
    else:
        ctx_label = "Offline"
        ctx_detail = f"No reliable market context: {md_detail}; fix ingestion / Pyth stream."

    ls = learning_summary if isinstance(learning_summary, dict) else {}
    ui_state = str(seq.get("ui_state") or ls.get("ui_state") or "idle")
    ev_proc = int(seq.get("events_processed_total") or ls.get("events_processed_total") or 0)
    k_iter = int(ts.get("karpathy_loop_iteration") or 0)
    curriculum = str(ts.get("curriculum_id") or "")
    enrolled = bool(curriculum)

    if ui_state == "running" and ev_proc > 0:
        learn_label = "Online"
        learn_detail = f"Sequential learning running; {ev_proc} events processed. ui_state={ui_state}."
    elif ui_state == "running":
        learn_label = "Partial"
        learn_detail = "Sequential UI is running but no events processed yet (or queue empty)."
    elif enrolled or k_iter > 0:
        learn_label = "Partial"
        learn_detail = (
            f"Training state present (curriculum={curriculum or '—'}, karpathy_iteration={k_iter}) "
            "but sequential engine not advancing events — start/resume learning or check queue."
        )
    else:
        learn_label = "Offline"
        learn_detail = "No active learning loop evidence (idle sequential, no curriculum iteration)."

    llm_env = _env_llm_on()
    lp_ok = bool(lp.get("ok"))
    lp_skip = bool(lp.get("skipped"))
    if not llm_env:
        llm_label = "Offline"
        llm_detail = "ANNA_USE_LLM is off — no Ollama analysis path for harness/Telegram defaults."
    elif lp_skip:
        llm_label = "Offline"
        llm_detail = f"LLM skipped: {lp.get('reason') or 'skipped'}."
    elif lp_ok:
        llm_label = "Online"
        llm_detail = f"Ollama probe OK — model {lp.get('ollama_model_configured') or '—'} @ {lp.get('base_url') or '—'}."
    else:
        llm_label = "Partial"
        llm_detail = f"ANNA_USE_LLM on but probe not OK: {lp.get('error') or 'check ollama serve'}."

    any_anna, econ_anna = _trade_chain_has_economic_anna(trade_chain)
    last_dec = seq.get("last_decision_row")
    sprt_d = _sprt_promotion_hint(seq)

    if sprt_d or (isinstance(last_dec, dict) and last_dec):
        dec_label = "Online"
        dec_detail = "Trial decisions / SPRT path active (last decision or SPRT snapshot present)."
    elif econ_anna:
        dec_label = "Online"
        dec_detail = "Economic Anna ledger rows (paper/live) present in trade chain window — decisions materialized as trades."
    elif any_anna:
        dec_label = "Partial"
        dec_detail = "Anna rows exist but mostly eval/stub or non-economic — limited independent trial PnL."
    else:
        dec_label = "Offline"
        dec_detail = "No Anna strategy rows in this window — no trial decision surface in ledger."

    agg = trade_chain.get("anna_vs_baseline_aggregate") or {}
    try:
        w = int(agg.get("wins") or 0)
        nw = int(agg.get("not_wins") or 0)
        exc = int(agg.get("excluded") or 0)
    except (TypeError, ValueError):
        w = nw = exc = 0
    compared = w + nw
    if compared > 0 and exc < compared + w + nw:
        bc_label = "Valid"
        bc_detail = f"Paired comparisons: WIN={w}, NOT={nw}, n/a={exc} — instrument active for this window."
    elif compared > 0:
        bc_label = "Limited"
        bc_detail = "Some pairs exist but many n/a — check MAE/PnL/stub modes (see trade chain legend)."
    elif exc > 0 and compared == 0:
        bc_label = "Limited"
        bc_detail = "Only excluded comparisons — no WIN/NOT yet (instrument weak for this run)."
    else:
        bc_label = "Invalid"
        bc_detail = "No Anna vs baseline pairs in this window — cannot measure relative performance."

    if w > nw and compared >= 3:
        plain = "Ahead of baseline on paired WIN vs NOT in this window."
        ev = "building" if compared < 10 else "strong"
    elif nw > w and compared >= 3:
        plain = "Behind baseline on paired WIN vs NOT in this window."
        ev = "building" if compared < 10 else "strong"
    elif compared > 0:
        plain = "Mixed or tied — need more paired events."
        ev = "weak"
    else:
        plain = "Not enough paired comparison data in this window."
        ev = "weak"

    trust = compared > 0 and bc_label != "Invalid"
    sprt_hint = sprt_d or "CONTINUE"
    if sprt_hint.upper() == "PROMOTE":
        prom = "promotable"
    elif sprt_hint.upper() == "KILL":
        prom = "not_promotable"
    elif compared == 0:
        prom = "not_yet_measurable"
    else:
        prom = "not_yet_measurable"

    des = str((operator_trading or {}).get("designated_strategy_id") or "") or None
    phase = {
        "sandbox_eval": "Anna test rows + paper_stub/eval — experimental; not headline book.",
        "economic_proof": "Anna paper/live rows with derived PnL — economic harness path.",
        "active_strategy": des or "No designated Anna strategy — baseline is default system strategy.",
        "promotion_readiness": f"SPRT/operator: {sprt_hint}; paired evidence: {prom}.",
        "designated_strategy_id": des,
    }

    gap = {
        "implemented": [
            "Execution ledger + trade chain vs baseline (paired cells, scorecard).",
            "Sequential learning control + SPRT decision surfacing when engine runs.",
            "Paper capital + operator trading strategy designation.",
            "Liveness / Pyth / bundle poll heartbeat.",
        ],
        "partial": [
            "Lesson memory + carryforward (not full W8 similarity lesson DB).",
            "LLM when Ollama up — Telegram/harness path; not proven on every tick from this strip alone.",
            "Karpathy loop daemon state — partial overlap with this API snapshot.",
        ],
        "missing": [
            "W8: dedicated structured lesson store + similarity retrieval + T1–T5 proof (see context_memory_contract_w8.md §8).",
            "failure_pattern_key archive differential (ANNA_GOES_TO_SCHOOL).",
            "Full event-centric indicators/narrative per market_event_id (event_market_training_view_framework.md gaps).",
        ],
    }

    return {
        "schema": "anna_intelligence_visibility_v1",
        "status_strip": {
            "context": {
                "label": ctx_label,
                "plain": "Market data + price probe usable for analysis.",
                "detail": ctx_detail,
                "backend_signals": ["market_bars_5m:" + ("ok" if md_ok else "fail"), f"pyth_age_s:{pyth_age}"],
            },
            "learning": {
                "label": learn_label,
                "plain": "School / sequential loop producing or consuming training artifacts.",
                "detail": learn_detail,
                "backend_signals": [
                    f"sequential_ui_state:{ui_state}",
                    f"events_processed_total:{ev_proc}",
                    f"karpathy_loop_iteration:{k_iter}",
                ],
            },
            "llm_analysis": {
                "label": llm_label,
                "plain": "Ollama-backed analyst path available when enabled.",
                "detail": llm_detail,
                "backend_signals": [
                    f"ANNA_USE_LLM:{int(llm_env)}",
                    f"karpathy_last_llm_preflight.ok:{lp.get('ok')}",
                    f"skipped:{lp_skip}",
                ],
            },
            "decisioning": {
                "label": dec_label,
                "plain": "Trial decisions visible as ledger/SPRT outcomes.",
                "detail": dec_detail,
                "backend_signals": [
                    f"has_economic_anna_rows:{econ_anna}",
                    f"last_sprt:{sprt_d or 'none'}",
                ],
            },
            "baseline_comparison": {
                "label": bc_label,
                "plain": "Anna measured vs baseline on same market_event_id (MAE gate).",
                "detail": bc_detail,
                "backend_signals": [f"anna_vs_baseline_aggregate:{agg}"],
            },
        },
        "effectiveness_summary": {
            "vs_baseline_plain": plain,
            "comparison_trustworthy": trust,
            "why_trust": "Trustworthy when WIN+NOT > 0 and exclusions are not the only outcome."
            if trust
            else "Not trustworthy until paired WIN/NOT exist.",
            "evidence_strength": ev,
            "promotion_readiness": prom,
        },
        "phase_story": phase,
        "subsystem_gaps": gap,
    }
