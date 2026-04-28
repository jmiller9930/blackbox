#!/usr/bin/env python3
"""
FinQuant-1 — pull real sources and emit structured training JSONL (no training).

Deploy target on lab host: /data/finquant-1/training/source_to_training.py

Requires: pip install -r finquant/requirements-finquant.txt
Optional SSL: export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")

Subcommands:
  pull   — download HF caches, exchange docs, Wikipedia REST summaries
  build  — build datasets/finquant_source_v0.1.jsonl from pulled material + DB
  all    — pull then build

Environment:
  FINQUANT_BASE           — root (default: parent of finquant/ in repo, i.e. repo_root/finquant)
  BLACKBOX_MARKET_DATA_PATH — SQLite market_data.db (see scripts/runtime/_paths.py)
  BLACKBOX_REPO_ROOT      — repo root for DB default resolution
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
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

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


# --- HTTP ---

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


# --- Exchange docs URL list (official doc roots + key endpoints) ---

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
    """Best-effort; often 403 from bots. Record outcome only."""
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


# --- Hugging Face preload ---


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


# --- SQL aggregates (no raw sequence export; summary stats only) ---


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
    """Single aggregate snapshot per symbol from ticks + optional bars."""
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
            state["symbols"][sym] = {
                "tick_count": len(series),
                "ticks_with_primary_price": len(closes),
                "t_first": ts_first,
                "t_last": ts_last,
                "price_mean": sum(closes) / len(closes),
                "price_min": min(closes),
                "price_max": max(closes),
                "log_return_std_sample": vol,
                "comparator_spread_mean": (sum(spread) / len(spread)) if spread else None,
                "rsi_proxy_period_adaptive": rsi,
                "regime_vol_bucket": "high" if vol > 0.001 else "low",
            }
        else:
            # Real rows exist but price legs are NULL — still emit warehouse telemetry (no invented prices).
            state["symbols"][sym] = {
                "tick_count": len(series),
                "ticks_with_primary_price": 0,
                "t_first": ts_first,
                "t_last": ts_last,
                "note": "primary_price comparators empty — DATA ingestion issue; refuse price-level inference.",
            }

    cur2 = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='market_bars_5m'")
    if cur2.fetchone()[0]:
        n = conn.execute("SELECT COUNT(*) FROM market_bars_5m").fetchone()[0]
        state["bars_available"] = int(n) > 0
        state["bars_5m_count"] = int(n)

    return state


_SQL_TEMPLATE_SPIN = [
    "Given ONLY aggregate statistics from our warehouse (no raw candle strings exported), state whether mean-reversion assumptions are justified.",
    "Risk officer asks: is realized volatility bucket consistent with leverage policy? Use aggregates below.",
    "Treasury wants regime label — classify using volatility bucket and spread telemetry.",
    "Audit: confirm DATA lineage — cite whether comparator feed exists and spread summary.",
    "Stress test mental model: if tick_count is small, what must we refuse to claim?",
]


def build_sql_records(state: dict[str, Any], n: int, seed: int) -> list[dict[str, Any]]:
    syms = sorted(state.get("symbols") or ())
    if not syms:
        raise RuntimeError(
            "No rows in market_ticks — populate BLACKBOX_MARKET_DATA_PATH or ingest ticks."
        )
    start = seed % len(syms)
    out: list[dict[str, Any]] = []
    for i in range(n):
        sym = syms[(i + start) % len(syms)]
        agg = dict(state["symbols"][sym])
        tmpl = _SQL_TEMPLATE_SPIN[i % len(_SQL_TEMPLATE_SPIN)]
        summary = json.dumps(agg, indent=2, sort_keys=True)[:6000]
        instruction = (
            f"[sql-scenario-{i}] {tmpl} "
            f"Symbol lens: {sym}. Training record uses aggregated warehouse stats only."
        )
        inp = (
            "MARKET_STATE_AGGREGATE_JSON:\n"
            + summary
            + "\n\nNOT EXPORTED: raw tick sequence / full OHLCV history (policy: aggregates only)."
        )
        out_txt = textwrap.dedent(
            f"""\
            Claim reviewed: Interpret regime from aggregates for {sym}.
            Math verdict: Volatility proxy from log returns is finite; sample size n_ticks={agg.get('tick_count')}.
            Risk/PnL verdict: Position sizing needs fresh VAR — aggregates insufficient alone.
            Indicator validity: RSI proxy may be unreliable when tick_count < 15; flag if needed.
            Regime considerations: regime_vol_bucket={agg.get('regime_vol_bucket')}.
            Failure modes: Sparse ticks; missing comparator; stale inserted_at vs decision time.
            DATA evidence required: Re-query latest ticks and bars with explicit time window.
            Final verifier status: needs proof unless live query confirms.
            """
        ).strip()
        out.append(
            {
                "instruction": instruction,
                "input": inp,
                "output": out_txt,
                "source": "sql",
            }
        )
    return out


# --- Synthetic adversarial ---


def build_synthetic_adversarial(n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    traps = [
        (
            "Analyst claims annualized Sharpe 4.2 from 6 daily samples without subtracting risk-free rate.",
            "Reject: insufficient sample; Sharpe definition mis-applied; needs full return series and rf curve.",
        ),
        (
            "Promo material states perpetual funding 'always pays longs' in crypto.",
            "False: funding sign depends on premium/discount; cite venue formula with receipts.",
        ),
        (
            "Strategy uses RSI(14) crossing 70 on 1m bars to short macro BTC.",
            "Mismatch: indicator timeframe vs thesis timeframe; multiple testing on 1m.",
        ),
    ]
    out: list[dict[str, Any]] = []
    for i in range(n):
        a, critique = traps[i % len(traps)]
        instruction = f"[adv-{i}] Challenge this quantitative claim (adversarial trap)."
        inp = f"Claim bundle #{i}: {a}"
        out.append(
            {
                "instruction": instruction,
                "input": inp,
                "output": textwrap.dedent(
                    f"""\
                    Verdict: fail / needs proof.
                    Reasoning: {critique}
                    Failure modes: cherry-picked windows, fee omission, regime shift.
                    DATA requirements: Download labeled fills and marks from venue API for full window.
                    """
                ).strip(),
                "source": "synthetic",
            }
        )
        rng.random()
    return out


# --- HF + wiki + exchange structured ---


def _norm_finqa_row(row: dict[str, Any]) -> tuple[str, str, str]:
    q = str(row.get("question") or row.get("pre_text") or "")
    tb = str(row.get("table") or "")
    ans = str(row.get("answer") or "")
    return q, tb, ans


def build_hf_finqa(n: int, seed: int) -> list[dict[str, Any]]:
    configure_ssl()
    from datasets import load_dataset  # type: ignore

    rng = random.Random(seed)
    ds = load_dataset("ibm-research/finqa", trust_remote_code=True)
    train = ds["train"]
    out: list[dict[str, Any]] = []
    # shuffle indices deterministically
    idxs = list(range(len(train)))
    rng.shuffle(idxs)
    for j in range(min(n, len(idxs))):
        row = train[idxs[j]]
        q, tb, ans = _norm_finqa_row(row)
        instruction = (
            "Solve the financial QA task using the provided table. Show reasoning steps; cite cells conceptually."
        )
        inp = f"hf_dataset=ibm-research/finqa row_index={idxs[j]}\nQuestion:\n{q}\n\nTable:\n{tb[:8000]}"
        output = (
            f"Reference answer (supervision target from dataset): {ans[:2000]}\n"
            "Trainee must verify arithmetic against table cells; failure modes: wrong row lookup, unit mismatch."
        )
        out.append({"instruction": instruction, "input": inp, "output": output, "source": "finqa"})
    return out


def build_hf_math(n: int, seed: int) -> list[dict[str, Any]]:
    configure_ssl()
    from datasets import load_dataset  # type: ignore

    rng = random.Random(seed + 3)
    # Hub id `hendrycks/competition_math` is unavailable in many environments; canonical mirror:
    ds = load_dataset("EleutherAI/hendrycks_math", "algebra")
    train = ds["train"]
    idxs = list(range(len(train)))
    rng.shuffle(idxs)
    out: list[dict[str, Any]] = []
    for j in range(min(n, len(idxs))):
        row = train[idxs[j]]
        prob = str(row.get("problem", ""))
        sol = str(row.get("solution", row.get("answer", "")))
        instruction = "Solve the competition mathematics problem with rigorous steps."
        inp = (
            "hf_dataset=EleutherAI/hendrycks_math config=algebra "
            f"level={row.get('level')} type={row.get('type')}\n{prob}"
        )
        output = (
            f"Reference solution sketch (dataset field): {sol[:4000]}\n"
            "Cross-check each algebraic step; reject if domain constraints violated."
        )
        out.append({"instruction": instruction, "input": inp, "output": output, "source": "finqa"})
    return out


def build_hf_numina(n: int, seed: int) -> list[dict[str, Any]]:
    configure_ssl()
    from datasets import load_dataset  # type: ignore

    rng = random.Random(seed + 7)
    ds = load_dataset("AI-MO/NuminaMath-CoT", split="train", streaming=True)
    out: list[dict[str, Any]] = []
    it = iter(ds)
    for j in range(n):
        try:
            row = next(it)
        except StopIteration:
            break
        prob = str(row.get("problem", row.get("question", "")))
        sol = str(row.get("solution", ""))
        instruction = "Solve with chain-of-thought discipline; flag ambiguous premises."
        inp = f"hf_dataset=AI-MO/NuminaMath-CoT stream_offset={j}\n{prob[:12000]}"
        output = f"Reference (subset): {sol[:4000]}"
        out.append({"instruction": instruction, "input": inp, "output": output, "source": "finqa"})
        rng.random()
    return out


def build_wikipedia_records(raw_dir: Path, n: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    files = sorted(raw_dir.glob("*.json"))
    if not files:
        return out
    variants = [
        "Explain for a quant risk committee.",
        "Give failure modes when applying this concept to intraday crypto.",
        "Contrast academic definition vs execution-time observables.",
        "How would you validate empirically before sizing risk?",
        "What DATA would falsify a naive application of this statistic?",
        "Spell out linkage to regime detection.",
        "Challenge an analyst mis-using this concept.",
        "Provide a checklist for implementation QA.",
        "Explain to a compliance reviewer without trading jargon overload.",
        "Relate to cross-venue consistency checks.",
    ]
    idx = 0
    while len(out) < n:
        p = files[idx % len(files)]
        vi = idx // len(files)
        idx += 1
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            if idx > len(files) * (len(variants) + 4):
                break
            continue
        title = doc.get("title", p.stem)
        extract = doc.get("extract", "")
        url = ""
        cu = doc.get("content_urls") or {}
        if isinstance(cu, dict):
            desk = cu.get("desktop")
            if isinstance(desk, dict):
                url = str(desk.get("page") or desk.get("href") or "")
        prompt = variants[vi % len(variants)]
        instruction = f"{prompt} Concept: {title}. Varied framing ({vi})."
        inp = (
            f"wikipedia_rest_summary_file={p.name}\n"
            f"canonical_url={url}\n"
            f"extract:\n{extract[:6000]}"
        )
        output = textwrap.dedent(
            """\
            Summary grounded in Wikipedia REST extract only (not live page scrape).
            Failure modes: simplification bias; academic vs market conventions differ.
            DATA requirements: For trading, verify against venue specs + live samples — Wikipedia is not execution truth.
            """
        ).strip()
        out.append({"instruction": instruction, "input": inp, "output": output, "source": "finqa"})
        if idx > len(files) * len(variants) * 4:
            break
    return out[:n]


def build_exchange_doc_records(raw_html_dir: Path, n: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed + 11)
    paths = [p for p in raw_html_dir.glob("*.html") if p.stat().st_size > 40]
    if not paths:
        return []
    out: list[dict[str, Any]] = []
    questions = [
        "Extract the operational definition (how traders observe this quantity on the venue).",
        "List failure modes when relying on default REST polling frequency.",
        "What must be validated against production fills vs documentation?",
    ]
    for i in range(n):
        p = rng.choice(paths)
        raw = p.read_bytes()[:400000]
        text = strip_html(raw)
        instruction = f"[exchange-docs-{i}] {rng.choice(questions)}"
        inp = f"local_doc_file={p.name}\nsha256_prompt=verify_on_disk\nexcerpt:\n{text[:8000]}"
        output = textwrap.dedent(
            """\
            Ground truth requirement: reconcile excerpt with official PDF/HTML revision date on venue.
            Failure modes: doc drift vs API; testnet vs mainnet; symbol mapping errors.
            DATA requirements: Pull authenticated endpoints + compare to documentation statements.
            Verdict: needs proof until live cross-check passes.
            """
        ).strip()
        out.append({"instruction": instruction, "input": inp, "output": output, "source": "exchange_docs"})
    return out


# --- CLI ---


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


def cmd_build(base: Path, seed: int, report_path: Path | None) -> Path:
    configure_ssl()
    raw_exchange = base / "sources" / "raw" / "exchange_docs"
    raw_wiki = base / "sources" / "raw" / "wikipedia_rest"

    db_path = market_db_path()
    if not db_path.is_file():
        raise SystemExit(f"Market DB not found: {db_path} — set BLACKBOX_MARKET_DATA_PATH.")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        state = extract_market_state(conn)
    finally:
        conn.close()

    sql_recs = build_sql_records(state, 500, seed)
    syn_recs = build_synthetic_adversarial(500, seed + 1)

    # Bucket 3 split (must sum to 500): HF FinQA + MATH + Numina + Wikipedia REST + venue HTML excerpts
    n_finqa, n_math, n_numina, n_wiki, n_exchange = 180, 120, 100, 50, 50

    finqa_recs = build_hf_finqa(n_finqa, seed)
    math_recs = build_hf_math(n_math, seed)
    numina_recs = build_hf_numina(n_numina, seed)
    wiki_recs = build_wikipedia_records(raw_wiki, n_wiki)
    ex_recs = build_exchange_doc_records(raw_exchange, n_exchange, seed)

    corpus = finqa_recs + math_recs + numina_recs + wiki_recs + ex_recs
    if len(corpus) < 500:
        pad = 500 - len(corpus)
        extra = build_hf_numina(pad, seed + 99)
        corpus.extend(extra)
    corpus = corpus[:500]

    all_recs = sql_recs + syn_recs + corpus
    if len(all_recs) != 1500:
        raise RuntimeError(f"expected 1500 records, got {len(all_recs)}")

    out_path = base / "datasets" / "finquant_source_v0.1.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in all_recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    counts = Counter(r["source"] for r in all_recs)
    print(json.dumps({"written": str(out_path), "counts": dict(counts)}, indent=2))

    rp = report_path or (base / "reports" / "source_acquisition_report_v0.1.md")
    rp.parent.mkdir(parents=True, exist_ok=True)
    man_path = base / "sources" / "manifest.json"
    man_txt = man_path.read_text(encoding="utf-8") if man_path.is_file() else "{}"

    sample_lines = []
    for src in ("sql", "synthetic", "finqa", "exchange_docs"):
        one = next((r for r in all_recs if r["source"] == src), None)
        if one:
            sample_lines.append(f"### source={src}\n```json\n{json.dumps(one, indent=2)[:3500]}\n```\n")

    report_md = "\n".join(
        [
            "# FinQuant-1 Source Acquisition Report v0.1",
            "",
            "**Training:** not started (dataset construction only).",
            "",
            "## Paths",
            "",
            f"- Base: `{base}`",
            f"- Output JSONL: `{out_path}`",
            f"- Manifest: `{man_path}`",
            f"- Market DB used: `{market_db_path()}`",
            "",
            "## What was pulled",
            "",
            "See `sources/manifest.json` for HTTP/HF outcomes. Inline snapshot (may be truncated):",
            "",
            "```json",
            man_txt[:12000],
            "```",
            "",
            "## Transformation",
            "",
            "- **sql:** Aggregates from `market_ticks` / optional `market_bars_5m`. No raw price sequences exported — only summary JSON in `input`. If price legs are NULL, scenarios flag ingestion gaps explicitly.",
            "- **synthetic:** Deterministic adversarial finance traps (seeded).",
            "- **finqa:** `ibm-research/finqa`; competition math via **`EleutherAI/hendrycks_math`** (`algebra` config — canonical Hub mirror when `hendrycks/competition_math` is unavailable); `AI-MO/NuminaMath-CoT` (streaming subset); Wikipedia REST summaries. Schema uses `source`: `finqa` for this bucket — HF dataset ids appear in `input`.",
            "- **exchange_docs:** HTML under `sources/raw/exchange_docs/` from venue documentation URLs; QA from on-disk excerpts.",
            "",
            "## Record counts",
            "",
            "| source | count |",
            "|--------|------:|",
        ]
        + [f"| `{k}` | {counts[k]} |" for k in sorted(counts)]
        + ["", "## Samples", ""]
        + sample_lines
        + [
            "",
            "## Gaps / follow-ups",
            "",
            "- Investopedia often blocks automated fetch — use browser export if human-curated RSI/ATR copy required.",
            "- Funding / open interest not in default `market_data.db` schema — add venue futures tables if needed.",
            "- Expand exchange pulls beyond landing pages for liquidation/fee formulas.",
            "- Deploy: copy `finquant/training/source_to_training.py` to `/data/finquant-1/training/` on the lab host; set `FINQUANT_BASE=/data/finquant-1`.",
            "",
            "## Readiness",
            "",
            "Sources are real (HF + REST + on-disk docs + DB telemetry). Suitable for QA review before training.",
            "",
        ]
    )
    rp.write_text(report_md, encoding="utf-8")
    print(f"wrote {rp}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant-1 source pull + JSONL build")
    ap.add_argument("command", choices=("pull", "build", "all"))
    ap.add_argument("--base", type=Path, default=None, help="FINQUANT root (default: env FINQUANT_BASE or finquant/)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    base = (args.base or default_finquant_base()).resolve()

    if args.command == "pull":
        cmd_pull(base)
    elif args.command == "build":
        cmd_build(base, args.seed, None)
    else:
        cmd_pull(base)
        cmd_build(base, args.seed, None)


if __name__ == "__main__":
    main()
