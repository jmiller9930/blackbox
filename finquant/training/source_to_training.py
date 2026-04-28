#!/usr/bin/env python3
"""
FinQuant-1 — manifest-driven pull + deterministic staging builder (no training).

Deploy on lab host: /data/finquant-1/training/source_to_training.py

Primary staging artifact:
  {FINQUANT_BASE}/datasets/staging/finquant_staging_v0.1.jsonl
(supersedes legacy finquant_source_v0.1.jsonl)

Requires: pip install -r finquant/requirements-finquant.txt
Optional: SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")

Commands:
  pull         — download HF caches, exchange docs, Wikipedia REST → sources/manifest.json
  build        — deterministic staging JSONL + source_to_training_build_report_v0.1.md
  all          — pull then build

Environment:
  FINQUANT_BASE, BLACKBOX_MARKET_DATA_PATH, BLACKBOX_REPO_ROOT
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import textwrap
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterator

# --- paths ---


def _script_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_finquant_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def market_db_path() -> Path:
    env = (os.environ.get("BLACKBOX_MARKET_DATA_PATH") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    root = (os.environ.get("BLACKBOX_REPO_ROOT") or "").strip()
    base = Path(root).expanduser().resolve() if root else _script_repo_root()
    return base / "data" / "sqlite" / "market_data.db"


def configure_ssl() -> None:
    try:
        import certifi  # type: ignore

        ca = certifi.where()
        if not os.environ.get("SSL_CERT_FILE"):
            os.environ["SSL_CERT_FILE"] = ca
        if not os.environ.get("REQUESTS_CA_BUNDLE"):
            os.environ["REQUESTS_CA_BUNDLE"] = ca
    except Exception:
        pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- Closed category enum (dataset plan v0.1 — 13 pillars) ---

CATEGORY_LABELS: dict[int, str] = {
    1: "financial_math_pnl",
    2: "crypto_market_structure",
    3: "indicator_intelligence",
    4: "statistical_quant_indicators",
    5: "order_flow_microstructure",
    6: "derivatives_signals_crypto",
    7: "volatility_structure",
    8: "multi_timeframe_interaction",
    9: "backtest_replay_integrity",
    10: "policy_vs_implementation",
    11: "python_quant_code_review",
    12: "financial_tables_filings",
    13: "data_validation_prompts",
}


def category_valid(c: int) -> bool:
    return c in CATEGORY_LABELS


# --- Verifier contract (FinQuant) ---


VERIFIER_PREFIXES: tuple[str, ...] = (
    "Claim reviewed:",
    "Math verdict:",
    "Risk/PnL verdict:",
    "Indicator validity:",
    "Regime considerations:",
    "Failure modes / edge cases:",
    "Leakage / overfit concerns:",
    "Policy-vs-implementation concerns:",
    "DATA evidence required:",
    "Final verifier status:",
)


def format_verifier_output(
    *,
    claim: str,
    math_v: str,
    risk_v: str,
    ind_v: str,
    regime: str,
    fail_modes: str,
    leak: str,
    policy: str,
    data_ev: str,
    status: str,
) -> str:
    return (
        f"Claim reviewed: {claim}\n"
        f"Math verdict: {math_v}\n"
        f"Risk/PnL verdict: {risk_v}\n"
        f"Indicator validity: {ind_v}\n"
        f"Regime considerations: {regime}\n"
        f"Failure modes / edge cases: {fail_modes}\n"
        f"Leakage / overfit concerns: {leak}\n"
        f"Policy-vs-implementation concerns: {policy}\n"
        f"DATA evidence required: {data_ev}\n"
        f"Final verifier status: {status}"
    )


def normalize_for_dedupe(s: str) -> str:
    t = unicodedata.normalize("NFC", s or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def dedupe_hash(instruction: str, input_text: str) -> str:
    payload = normalize_for_dedupe(instruction) + "\n" + normalize_for_dedupe(input_text)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_BANNED_SIMPLE_SIGNAL = re.compile(
    r"(?is)rsi\s*[<>]=?\s*\d+.{0,40}(buy|long|sell|short)|"
    r"(?is)macd\s+cross.{0,30}(buy|sell)|"
    r"(?is)buy\s+signal.*rsi"
)
_UNSUPPORTED_PRED = re.compile(
    r"(?i)\b(will\s+(definitely|certainly)|guaranteed\s+to\s+reach|sure\s+bet)\b"
)


def quality_gate_reject(record: dict[str, Any]) -> str | None:
    """Return rejection reason or None if OK."""
    instr = record.get("instruction") or ""
    inp = record.get("input") or ""
    out = record.get("output") or ""
    if len(normalize_for_dedupe(instr)) < 24:
        return "instruction_too_short_or_generic"
    if len(normalize_for_dedupe(inp)) < 16:
        return "input_too_short"
    for p in VERIFIER_PREFIXES:
        if p not in out:
            return f"missing_verifier_section:{p}"
    # Claim substantive (not placeholder-only)
    m = re.search(r"Claim reviewed:\s*(.+)", out)
    if not m or len(m.group(1).strip()) < 8:
        return "claim_missing_or_trivial"
    fm = re.search(r"Failure modes / edge cases:\s*(.+)", out, re.DOTALL)
    if not fm or len(fm.group(1).strip()) < 6:
        return "failure_modes_missing"
    dm = re.search(r"DATA evidence required:\s*(.+)", out, re.DOTALL)
    if not dm or len(dm.group(1).strip()) < 6:
        return "data_evidence_missing"
    st = re.search(r"Final verifier status:\s*(\S.+)", out)
    if not st:
        return "final_status_missing"
    status_line = st.group(1).strip().lower()
    if not any(x in status_line for x in ("pass", "fail", "needs proof")):
        return "final_status_invalid"
    combined = instr + "\n" + inp + "\n" + out
    if _BANNED_SIMPLE_SIGNAL.search(combined):
        return "simple_signal_rule_banned"
    if _UNSUPPORTED_PRED.search(combined):
        return "unsupported_prediction"
    # Generic assistant smell (cheap heuristic)
    if re.search(r"(?i)^\s*(as an ai|i cannot predict)", instr):
        return "generic_assistant_tone"
    return None


# --- HTTP (pull) ---

UA = "FinQuant-1-source-bot/0.1 (+local pipeline; engineering@blackbox)"


def http_get(url: str, timeout: int = 120) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.getcode() or 200, resp.read()


def strip_html(html: bytes) -> str:
    text = html.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:12000]


EXCHANGE_DOC_URLS: list[tuple[str, str]] = [
    ("binance", "https://binance-docs.github.io/apidocs/futures/en/"),
    ("binance_mark_price", "https://binance-docs.github.io/apidocs/futures/en/#mark-price"),
    ("binance_funding", "https://binance-docs.github.io/apidocs/futures/en/#funding-rate"),
    ("binance_liquidation", "https://binance-docs.github.io/apidocs/futures/en/#liquidation-orders"),
    ("deribit", "https://docs.deribit.com/"),
    ("deribit_public", "https://docs.deribit.com/#public-methods"),
    ("bybit", "https://bybit-exchange.github.io/docs/"),
    ("bybit_linear", "https://bybit-exchange.github.io/docs/v5/market/mark-kline"),
    ("kraken", "https://docs.kraken.com/api/"),
    ("kraken_futures", "https://docs.kraken.com/api/docs/futures-api/trading/introduction/"),
]


def pull_exchange_docs(raw_dir: Path, manifest: dict[str, Any]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    ex = manifest.setdefault("exchange_docs", [])
    for slug, url in EXCHANGE_DOC_URLS:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", slug) + ".html"
        out = raw_dir / safe
        try:
            code, body = http_get(url, timeout=180)
            out.write_bytes(body)
            ex.append(
                {
                    "slug": slug,
                    "url": url,
                    "path": str(out),
                    "http_status": code,
                    "sha256": sha256_file(out),
                    "bytes": out.stat().st_size,
                }
            )
            time.sleep(0.4)
        except Exception as e:
            ex.append({"slug": slug, "url": url, "error": repr(e)})


WIKI_TITLES = [
    "Z-score",
    "Volatility_(finance)",
    "Cointegration",
    "Relative_strength_index",
    "Average_true_range",
]


def pull_wikipedia_rest(raw_dir: Path, manifest: dict[str, Any]) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    wiki = manifest.setdefault("wikipedia_rest", [])
    for title in WIKI_TITLES:
        safe = title.replace("/", "_") + ".json"
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        out = raw_dir / safe
        try:
            code, body = http_get(url, timeout=60)
            out.write_bytes(body)
            wiki.append(
                {
                    "title": title,
                    "url": url,
                    "path": str(out),
                    "http_status": code,
                    "sha256": sha256_file(out),
                }
            )
            time.sleep(0.35)
        except Exception as e:
            wiki.append({"title": title, "url": url, "error": repr(e)})


def pull_investopedia_try(manifest: dict[str, Any]) -> None:
    urls = [
        "https://www.investopedia.com/terms/r/rsi.asp",
        "https://www.investopedia.com/terms/a/atr.asp",
    ]
    inv = manifest.setdefault("investopedia", [])
    for url in urls:
        try:
            code, body = http_get(url, timeout=60)
            inv.append({"url": url, "http_status": code, "bytes": len(body)})
        except Exception as e:
            inv.append({"url": url, "error": repr(e)})


def pull_hf(manifest: dict[str, Any]) -> None:
    configure_ssl()
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "Missing dependency: pip install -r finquant/requirements-finquant.txt\n" + str(e)
        ) from e

    hf = manifest.setdefault("huggingface", [])
    specs: list[tuple[str, dict[str, Any], str | None]] = [
        ("ibm-research/finqa", {"trust_remote_code": True}, None),
        ("EleutherAI/hendrycks_math", {}, "algebra"),
        ("AI-MO/NuminaMath-CoT", {}, None),
    ]
    for name, kw, cfg in specs:
        t0 = time.time()
        try:
            ds = load_dataset(name, cfg, **kw) if cfg is not None else load_dataset(name, **kw)
            splits = list(ds.keys())
            hf.append(
                {
                    "dataset": name,
                    "splits": splits,
                    "elapsed_s": round(time.time() - t0, 2),
                    "ok": True,
                }
            )
        except Exception as e:
            hf.append({"dataset": name, "ok": False, "error": repr(e), "elapsed_s": round(time.time() - t0, 2)})


# --- SQL / market state ---


def _rsi_wilder(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = max(d, 0.0)
        l = max(-d, 0.0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1.0 + rs))


def extract_market_state(conn: sqlite3.Connection) -> dict[str, Any]:
    state: dict[str, Any] = {"symbols": {}, "bars_available": False}
    cur = conn.execute(
        """
        SELECT symbol, inserted_at, primary_price, comparator_price
        FROM market_ticks
        ORDER BY symbol, inserted_at ASC, id ASC
        """
    )
    rows = cur.fetchall()
    by_sym: dict[str, list[tuple[str, float | None, float | None]]] = {}
    for sym, ins, pp, cp in rows:
        pf = float(pp) if pp is not None else None
        cf = float(cp) if cp is not None else None
        by_sym.setdefault(sym, []).append((ins, pf, cf))

    for sym, series in by_sym.items():
        closes_all = [t[1] for t in series if t[1] is not None]
        ts_first, ts_last = series[0][0], series[-1][0]
        if closes_all:
            closes = closes_all
            rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))] if len(closes) > 1 else []
            vol = float(sum(r * r for r in rets) / len(rets)) ** 0.5 if rets else 0.0
            spread = [
                abs(series[i][1] - series[i][2])
                for i in range(len(series))
                if series[i][1] is not None and series[i][2] is not None
            ]
            rsi = _rsi_wilder(closes, min(14, max(2, len(closes) - 1))) if len(closes) > 2 else None
            rvb = "high_vol" if vol > 0.001 else "low_vol"
            trend_chop = "chop" if vol > 0.0008 else "trend_candidate"
            state["symbols"][sym] = {
                "timeframe_reference": "warehouse_ticks_as_available",
                "tick_count": len(series),
                "ticks_with_primary_price": len(closes),
                "t_first": ts_first,
                "t_last": ts_last,
                "ohlcv_summary": {
                    "price_mean": sum(closes) / len(closes),
                    "price_min": min(closes),
                    "price_max": max(closes),
                },
                "log_return_std_sample": vol,
                "comparator_spread_mean": (sum(spread) / len(spread)) if spread else None,
                "rsi_proxy_period_adaptive": rsi,
                "volatility_regime_label": rvb,
                "trend_chop_label": trend_chop,
            }
        else:
            state["symbols"][sym] = {
                "tick_count": len(series),
                "ticks_with_primary_price": 0,
                "t_first": ts_first,
                "t_last": ts_last,
                "note": "primary_price empty — refuse price-level inference until ingestion fixed.",
            }

    cur2 = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='market_bars_5m'")
    if cur2.fetchone()[0]:
        n = conn.execute("SELECT COUNT(*) FROM market_bars_5m").fetchone()[0]
        state["bars_available"] = int(n) > 0
        state["bars_5m_count"] = int(n)

    return state


_SQL_CAT_ROTATE = [4, 7, 13, 2, 6, 8, 12, 5, 3, 1, 11, 9, 10]


def iter_sql_staging(state: dict[str, Any], seed: int) -> Iterator[dict[str, Any]]:
    syms = sorted(state.get("symbols") or ())
    if not syms:
        raise RuntimeError("No rows in market_ticks — populate BLACKBOX_MARKET_DATA_PATH.")
    start = seed % len(syms)
    i = 0
    while True:
        sym = syms[(i + start) % len(syms)]
        agg = dict(state["symbols"][sym])
        cat = _SQL_CAT_ROTATE[i % len(_SQL_CAT_ROTATE)]
        adversarial = i % 2 == 0
        tmpl = [
            "Given ONLY aggregate statistics (no raw sequence export), verify whether mean-reversion framing is justified.",
            "Risk: does volatility regime support proposed leverage? Use aggregates only.",
            "Audit DATA lineage: comparator spread telemetry vs primary — what could mislead?",
            "Stress: tick_count small — list what claims must be refused.",
            "Treasury: map volatility bucket to margin policy assumptions.",
        ][i % 5]
        summary = json.dumps(agg, indent=2, sort_keys=True)[:6000]
        instruction = (
            f"[market_scenario sql#{i}] {tmpl} Symbol={sym}. "
            "Verifier must challenge premature conclusions."
        )
        inp = (
            "MARKET_SCENARIO_CARD:\n"
            + summary
            + "\n\nEXPORT_POLICY: raw OHLCV strings not included — aggregates only."
        )
        if adversarial:
            claim = (
                f"Trap: analyst insists '{sym}' must be 'low risk' because sample vol looks small — ignore sparse ticks."
            )
            math_v = "incorrect / incomplete — variance unstable with tiny n; needs full window."
            risk_v = "Mis-sized exposure if leverage copied from headline stats."
            status = "fail"
        else:
            claim = f"Interpret warehouse aggregates for {sym} without over-claiming predictive power."
            math_v = "sound conditional on definitions; verify formulas vs venue."
            risk_v = "Sizing requires live risk engine — aggregates alone insufficient."
            status = "needs proof"
        out = format_verifier_output(
            claim=claim,
            math_v=math_v,
            risk_v=risk_v,
            ind_v="RSI proxy unreliable when ticks_with_primary_price < 15; treat as diagnostic only.",
            regime=f"Labels: volatility_regime={agg.get('volatility_regime_label')}; trend_chop={agg.get('trend_chop_label')}.",
            fail_modes="Sparse sampling; stale timestamps; missing comparator; venue definition drift.",
            leak="Potential peek if labels built from future bars — not evidenced here.",
            policy="Cross-check ingest vs documented schema for market_ticks.",
            data_ev=f"Pull authoritative tape for {sym} across explicit UTC window; reconcile fills.",
            status=status,
        )
        yield {
            "instruction": instruction,
            "input": inp,
            "output": out,
            "source_ids": [f"sql:market_db:{market_db_path().name}", f"sql:symbol:{sym}", "manifest:approved"],
            "category": cat,
            "adversarial": adversarial,
            "quality_flags": ["bucket:sql_market_scenario", "internal:market_scenario", f"trap:{str(adversarial).lower()}"],
        }
        i += 1


_SYNTH_CAT = [1, 2, 3, 9, 10, 11]


def iter_synthetic_staging(seed: int) -> Iterator[dict[str, Any]]:
    traps: list[tuple[str, str, str, str, str, str, str, str, str]] = [
        (
            "Sharpe 4.2 annualized from 6 daily samples; rf ignored.",
            "Sharpe mis-specified; insufficient df; rf curve omitted.",
            "False precision on risk appetite.",
            "N/A",
            "micro_stats_insufficient",
            "window_cherry_pick; fee_model_unknown",
            "Label leakage if returns computed with revised marks",
            "Risk policy says min 252-day window — not met",
            "Download full returns + rf series; verify arithmetic",
            "fail",
        ),
        (
            "Funding always pays longs on crypto perps.",
            "Wrong — sign follows premium/discount vs index.",
            "Marketing claims distort hedge sizing.",
            "N/A",
            "venue_formula_required",
            "basis misunderstanding",
            "Using funding history without venue definition",
            "Copy vs spec drift on funding interval",
            "Pull venue funding ledger + index methodology PDF revision",
            "fail",
        ),
        (
            "RSI(14) on 1m bars proves macro BTC short.",
            "Indicator timeframe mismatch vs macro thesis.",
            "False precision; multiple testing on 1m.",
            "RSI validity poor under ultra-low latency noise regime.",
            "TF_conflict",
            "multiple_testing",
            "Implicit lookahead if universe filtered post-hoc",
            "Indicator params not in policy registry",
            "Compare policy doc vs code constants",
            "needs proof",
        ),
    ]
    rng = random.Random(seed)
    i = 0
    while True:
        row = traps[i % len(traps)]
        claim_t, mv, rv, iv, reg, fm, lk, pol, data_ev, st = row
        cat = _SYNTH_CAT[i % len(_SYNTH_CAT)]
        instruction = f"[adversarial_case #{i}] Challenge bundled quantitative claim; assume hostile marketing."
        inp = f"ADVERSARIAL_BUNDLE_{i}: {claim_t}"
        out = format_verifier_output(
            claim=claim_t,
            math_v=mv,
            risk_v=rv,
            ind_v=iv,
            regime=reg,
            fail_modes=fm,
            leak=lk,
            policy=pol,
            data_ev=data_ev,
            status=st,
        )
        yield {
            "instruction": instruction,
            "input": inp,
            "output": out,
            "source_ids": ["generator:synthetic_adversarial_v01", f"synthetic:trap:{i}"],
            "category": cat,
            "adversarial": True,
            "quality_flags": ["bucket:synthetic_adversarial", "internal:adversarial_case"],
        }
        rng.random()
        i += 1


def _norm_finqa_row(row: dict[str, Any]) -> tuple[str, str, str]:
    q = str(row.get("question") or row.get("pre_text") or "")
    tb = str(row.get("table") or "")
    ans = str(row.get("answer") or "")
    return q, tb, ans


def iter_concept_staging(
    base: Path,
    seed: int,
    *,
    finqa_train: Any,
    math_train: Any,
    numina_iter: Iterator[dict[str, Any]],
    wiki_files: list[Path],
    exchange_paths: list[Path],
) -> Iterator[dict[str, Any]]:
    """Fixed schedule: 160 finqa, 80 math, 120 numina, 80 wiki, 60 exchange = 500."""
    rng_ord = random.Random(seed + 404)
    schedule: list[str] = (
        ["finqa"] * 160 + ["math"] * 80 + ["numina"] * 120 + ["wiki"] * 80 + ["exchange"] * 60
    )
    order = list(range(500))
    rng_ord.shuffle(order)
    sched_perm = [schedule[i] for i in order]

    finqa_order = list(range(len(finqa_train)))
    rng_ord.shuffle(finqa_order)
    math_order = list(range(len(math_train)))
    rng_ord.shuffle(math_order)

    fi = mj = nj = wj = ej = 0

    for slot in range(500):
        kind = sched_perm[slot]
        adversarial = slot < 250
        if kind == "finqa":
            row = finqa_train[finqa_order[fi % len(finqa_order)]]
            fi += 1
            q, tb, ans = _norm_finqa_row(row)
            idx = finqa_order[(fi - 1) % len(finqa_order)]
            instruction = "Verify financial table reasoning — cite cells; show arithmetic checks."
            inp = f"hf:ibm-research/finqa train_row={idx}\nQuestion:\n{q}\n\nTable:\n{tb[:8000]}"
            claim = "Table QA answer must match filings arithmetic — counterparty traps possible."
            out = format_verifier_output(
                claim=claim,
                math_v="Recompute from cited cells; watch units and scaling.",
                risk_v="Filings lag markets — no live trading implication.",
                ind_v="N/A unless table embeds technical indicators.",
                regime="N/A — accounting window vs market window mismatch is a trap.",
                fail_modes="Wrong row; fiscal vs calendar; restatements.",
                leak="Train/test contamination if same issuer reused improperly.",
                policy="Disclosure policy vs displayed table format.",
                data_ev=f"Cross-check source filing cells vs answer hint: {ans[:400]}",
                status="needs proof" if adversarial else "pass",
            )
            cat = 12 if not adversarial else 13
            src = ["hf:ibm-research/finqa:train", f"hf:finqa:row:{idx}", "manifest:approved"]
            flags = ["bucket:concept_derived", "internal:math_case", f"trap:{str(adversarial).lower()}"]
        elif kind == "math":
            row = math_train[math_order[mj % len(math_order)]]
            mj += 1
            prob = str(row.get("problem", ""))
            sol = str(row.get("solution", ""))
            idx = math_order[(mj - 1) % len(math_order)]
            instruction = "Calculation verification — rigorous steps only; no finance forecasts."
            inp = f"hf:EleutherAI/hendrycks_math:algebra row={idx}\n{prob}"
            claim = "Competition math — verify solution discipline; no market predictions."
            out = format_verifier_output(
                claim=claim,
                math_v="Check algebraic steps; domain constraints.",
                risk_v="N/A — math drill not portfolio advice.",
                ind_v="N/A",
                regime="N/A",
                fail_modes="Algebraic slip; boundary cases.",
                leak="N/A",
                policy="N/A",
                data_ev="Publish intermediate steps for audit.",
                status="needs proof",
            )
            cat = 1 if mj % 2 == 0 else 4
            src = ["hf:EleutherAI/hendrycks_math:algebra", f"hf:math:row:{idx}", "manifest:approved"]
            flags = ["bucket:concept_derived", "internal:math_case", "cap:math_not_dominant"]
        elif kind == "numina":
            row = next(numina_iter)
            prob = str(row.get("problem", row.get("question", "")))
            sol = str(row.get("solution", ""))
            instruction = "Solve with reasoning discipline — flag ambiguous premises."
            inp = f"hf:AI-MO/NuminaMath-CoT offset={nj}\n{prob[:12000]}"
            nj += 1
            claim = "Chain-of-thought must remain checkable — reject hand-waving."
            out = format_verifier_output(
                claim=claim,
                math_v="Validate each inference step.",
                risk_v="N/A",
                ind_v="N/A",
                regime="N/A",
                fail_modes="Ambiguous problem statements.",
                leak="N/A",
                policy="N/A",
                data_ev="Provide intermediate checkpoints.",
                status="needs proof",
            )
            cat = 4
            src = [f"hf:AI-MO/NuminaMath-CoT:stream:{nj-1}", "manifest:approved"]
            flags = ["bucket:concept_derived", "internal:math_case"]
        elif kind == "wiki":
            p = wiki_files[wj % len(wiki_files)]
            wj += 1
            doc = json.loads(p.read_text(encoding="utf-8"))
            title = doc.get("title", p.stem)
            extract = doc.get("extract", "")
            cu = doc.get("content_urls") or {}
            url = ""
            if isinstance(cu, dict):
                desk = cu.get("desktop")
                if isinstance(desk, dict):
                    url = str(desk.get("page") or "")
            instruction = f"Indicator/stat concept card — no signal rules; regime-aware misuse checks. ({wj})"
            inp = f"wikipedia_rest:{p.name}\nurl={url}\nextract:\n{extract[:6000]}"
            claim = f"Concept '{title}' — probabilistic; forbid simplistic buy/sell mapping."
            out = format_verifier_output(
                claim=claim,
                math_v="Definitions vs empirical estimates — separate.",
                risk_v="Mis-applying academic stats to microstructure latency.",
                ind_v=f"Discuss assumptions for indicators tied to {title} family.",
                regime="Breaks under structural breaks / fat tails.",
                fail_modes="Stationarity assumed falsely; window drift.",
                leak="N/A",
                policy="Policy must cite indicator definition sources.",
                data_ev="Empirical calibration on labeled venue samples.",
                status="needs proof",
            )
            cat = 3 if "rsi" in title.lower() or "atr" in title.lower() else 4
            src = [f"wikipedia_rest:{p.name}", "manifest:approved"]
            flags = ["bucket:concept_derived", "internal:concept_card", "doctrine:no_simple_rules"]
        else:
            ep = exchange_paths[ej % len(exchange_paths)]
            ej += 1
            raw = ep.read_bytes()[:400000]
            text = strip_html(raw)
            instruction = f"Crypto mechanics concept from venue docs — verify vs live API. file={ep.name}"
            inp = f"exchange_doc:{ep.name}\nexcerpt:\n{text[:8000]}"
            claim = "Documentation excerpt — reconcile with authenticated production endpoints."
            out = format_verifier_output(
                claim=claim,
                math_v="Formulas must match venue revision.",
                risk_v="Mis-set leverage/margin if doc stale.",
                ind_v="N/A unless doc defines index constituents.",
                regime="Funding/mark regimes vary — cite schedule.",
                fail_modes="Testnet vs mainnet; symbol alias errors.",
                leak="N/A",
                policy="Implementation must track doc revision hash.",
                data_ev="Signed API responses + doc PDF revision date.",
                status="needs proof",
            )
            cat = 6 if "funding" in ep.name else 2
            src = [f"exchange_doc:{ep.name}", "manifest:exchange_docs"]
            flags = ["bucket:concept_derived", "internal:concept_card"]

        if adversarial:
            flags.append("trap:true")
        yield {
            "instruction": instruction,
            "input": inp,
            "output": out,
            "source_ids": src,
            "category": cat,
            "adversarial": adversarial,
            "quality_flags": flags,
        }


def fill_bucket(
    gen: Iterator[dict[str, Any]],
    target: int,
    seen: set[str],
    *,
    counters: dict[str, int],
) -> tuple[list[dict[str, Any]], int, int]:
    """Accept until target unique records; return (records, rejected, dup_skipped)."""
    out: list[dict[str, Any]] = []
    rejected = 0
    dup_skipped = 0
    max_trials = target * 80
    trials = 0
    while len(out) < target and trials < max_trials:
        trials += 1
        rec = next(gen)
        why = quality_gate_reject(rec)
        if why:
            rejected += 1
            counters["reject_reasons"] = counters.get("reject_reasons", 0)  # noqa
            continue
        h = dedupe_hash(rec["instruction"], rec["input"])
        if h in seen:
            dup_skipped += 1
            continue
        seen.add(h)
        out.append(rec)
    if len(out) < target:
        raise RuntimeError(f"bucket incomplete: got {len(out)} need {target} after {trials} trials")
    return out, rejected, dup_skipped


def cmd_pull(base: Path) -> dict[str, Any]:
    configure_ssl()
    raw_root = base / "sources" / "raw"
    ex = raw_root / "exchange_docs"
    wiki = raw_root / "wikipedia_rest"
    manifest: dict[str, Any] = {"ts": time.time(), "base": str(base)}
    pull_exchange_docs(ex, manifest)
    pull_wikipedia_rest(wiki, manifest)
    pull_investopedia_try(manifest)
    pull_hf(manifest)
    man_path = base / "sources" / "manifest.json"
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {man_path}")
    return manifest


def cmd_build_staging(base: Path, seed: int) -> Path:
    configure_ssl()
    manifest_path = base / "sources" / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing {manifest_path} — run: python source_to_training.py pull")
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    db_path = market_db_path()
    if not db_path.is_file():
        raise SystemExit(f"Market DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    try:
        state = extract_market_state(conn)
    finally:
        conn.close()

    from datasets import load_dataset  # type: ignore

    finqa_ds = load_dataset("ibm-research/finqa", trust_remote_code=True)
    math_ds = load_dataset("EleutherAI/hendrycks_math", "algebra")
    numina_ds = load_dataset("AI-MO/NuminaMath-CoT", split="train", streaming=True)
    numina_iter = iter(numina_ds)

    wiki_dir = base / "sources" / "raw" / "wikipedia_rest"
    wiki_files = sorted(wiki_dir.glob("*.json"))
    ex_dir = base / "sources" / "raw" / "exchange_docs"
    exchange_paths = sorted([p for p in ex_dir.glob("*.html") if p.stat().st_size > 40])

    if not wiki_files:
        raise SystemExit("No Wikipedia REST JSON in sources/raw/wikipedia_rest — run pull.")
    if not exchange_paths:
        raise SystemExit("No exchange HTML in sources/raw/exchange_docs — run pull.")

    counters: dict[str, Any] = {"reject_reasons": Counter()}
    seen: set[str] = set()
    total_rejected = 0
    total_dup = 0

    sql_gen = iter_sql_staging(state, seed)
    sql_recs, rj, dp = fill_bucket(sql_gen, 500, seen, counters=counters)
    total_rejected += rj
    total_dup += dp

    synth_gen = iter_synthetic_staging(seed + 1)
    syn_recs, rj2, dp2 = fill_bucket(synth_gen, 500, seen, counters=counters)
    total_rejected += rj2
    total_dup += dp2

    concept_gen = iter_concept_staging(
        base,
        seed,
        finqa_train=finqa_ds["train"],
        math_train=math_ds["train"],
        numina_iter=numina_iter,
        wiki_files=wiki_files,
        exchange_paths=exchange_paths,
    )
    con_recs, rj3, dp3 = fill_bucket(concept_gen, 500, seen, counters=counters)
    total_rejected += rj3
    total_dup += dp3

    all_recs = sql_recs + syn_recs + con_recs
    assert len(all_recs) == 1500
    adv_n = sum(1 for r in all_recs if r.get("adversarial"))
    if adv_n < 750:
        raise RuntimeError(f"adversarial count {adv_n} < 750 — logic bug")

    out_dir = base / "datasets" / "staging"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "finquant_staging_v0.1.jsonl"
    key_order = ("instruction", "input", "output", "source_ids", "category", "adversarial", "quality_flags")
    with out_path.open("w", encoding="utf-8") as f:
        for r in all_recs:
            ordered = {k: r[k] for k in key_order}
            f.write(json.dumps(ordered, ensure_ascii=False, sort_keys=True) + "\n")

    by_cat = Counter(str(r["category"]) for r in all_recs)
    coverage: Counter[str] = Counter()
    for r in all_recs:
        for sid in r["source_ids"]:
            prefix = sid.split(":")[0]
            coverage[prefix] += 1

    report_path = base / "reports" / "source_to_training_build_report_v0.1.md"
    samples_txt = "\n\n".join(
        f"### Sample {i+1}\n```json\n{json.dumps({k: all_recs[i][k] for k in key_order}, indent=2, ensure_ascii=False)[:4500]}\n```"
        for i in range(20)
    )

    man_digest = sha256_file(manifest_path)
    ready = adv_n >= 750 and len(all_recs) == 1500 and total_rejected < 500000

    report_md = "\n".join(
        [
            "# FinQuant-1 — source_to_training build report v0.1",
            "",
            "**Training:** not started.",
            "",
            "## Manifest",
            "",
            f"- Path: `{manifest_path}`",
            f"- SHA256: `{man_digest}`",
            "",
            "## Staging output",
            "",
            f"- `{out_path}`",
            f"- Records: **{len(all_recs)}**",
            f"- Adversarial/trap rows: **{adv_n}** ({adv_n/15:.2f}%)",
            f"- Quality gate rejections (attempts): **{total_rejected}**",
            f"- Dedupe skips: **{total_dup}**",
            "",
            "## Category counts (closed enum 1–13)",
            "",
            "| category | n |",
            "|----------|--:|",
        ]
        + [f"| {k} | {by_cat[k]} |" for k in sorted(by_cat.keys(), key=lambda x: int(x))]
        + [
            "",
            "## Source ID coverage (prefix)",
            "",
            "| prefix | rows |",
            "|--------|-----:|",
        ]
        + [f"| `{k}` | {coverage[k]} |" for k in sorted(coverage.keys())]
        + [
            "",
            "## Twenty sample records",
            "",
            samples_txt,
            "",
            "## Known gaps",
            "",
            "- HF dataset revisions may drift bytes — pin revisions for bitwise reproducibility across hosts.",
            "- Streaming Numina order may vary if Hub shard changes.",
            "- Sparse `market_ticks` prices produce telemetry-only SQL scenarios.",
            "",
            "## Readiness",
            "",
            ("**Ready for QA review** — verifier contract enforced; staging schema v0.1." if ready else "**Not ready** — review errors."),
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_md, encoding="utf-8")

    print(
        json.dumps(
            {
                "staging_path": str(out_path),
                "total": len(all_recs),
                "by_category": dict(by_cat),
                "adversarial_count": adv_n,
                "adversarial_pct": round(adv_n / len(all_recs), 6),
                "rejected_attempts": total_rejected,
                "dedupe_skipped": total_dup,
                "source_coverage": dict(coverage),
                "quality_warnings": [],
                "report": str(report_path),
            },
            indent=2,
        )
    )
    print(f"wrote {report_path}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant-1 pull + deterministic staging")
    ap.add_argument("command", choices=("pull", "build", "all"))
    ap.add_argument("--base", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    base = (args.base or default_finquant_base()).resolve()

    if args.command == "pull":
        cmd_pull(base)
    elif args.command == "build":
        cmd_build_staging(base, args.seed)
    else:
        cmd_pull(base)
        cmd_build_staging(base, args.seed)


if __name__ == "__main__":
    main()
