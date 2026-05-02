#!/usr/bin/env python3
"""FINQUANT Train v0.05 — Baseline Certification Harness.

Implements ``training/FINQUANT_TRAIN_V005_BASELINE_SPEC.md``.

Workspace isolation (operator directive 2026-05-02, post-restructure
commit 5b35790): all FinQuant training-arc work lives under
``training/`` at the repo root. Harness is ``training/baseline_v005.py``,
run outputs go to ``training/runs/baseline_<ts>/``. This intentionally
deviates from the literal paths named in the spec (``tools/finquant/...``
and ``runtime/finquant_train_v005/...``) so the FinQuant arc is one
isolated folder. The unified-agent-lab learning loop work lives in
``prove_learning/finquant/unified/agent_lab/`` and is OUT OF SCOPE
for this harness.

Hard rules enforced:
  * SQLite opened read-only (URI mode=ro).
  * No writes to production DBs / execution ledger / policy / dashboard.
  * No model training, no DPO, no weight mutation.
  * Writes only under the run directory (default ``training/runs``).
  * Final line on success: ``FINQUANT_V005_BASELINE_MEASURED_NO_TRAINING_PERFORMED``.

Phase banners: PHASE_01_DATA_LOAD .. PHASE_07_REPORT_WRITE.

Per Engineering directive 2026-05-01 (Determinism De-scoped Revision):
consistency / determinism work is OUT OF SCOPE for this baseline. The
focus is schema discipline, causal integrity, risk reasoning, no-trade
quality, and (primary gate) learning_record_candidate validity. Consistency
replay will be added in a later phase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import socket
import sqlite3
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

SCHEMA_VERSION = "finquant_baseline_v0.05"
RUN_TAG = "finquant_train_v005"
DEFAULT_OUT_DIR = "training/runs"

REQUIRED_TOP_FIELDS = (
    "schema_version",
    "case_id",
    "decision",
    "direction",
    "confidence",
    "thesis",
    "competing_hypothesis",
    "invalidation",
    "risk_plan",
    "why_no_trade",
    "expected_failure_mode",
    "learning_record_candidate",
)
RISK_FIELDS = ("stop_logic", "target_logic", "max_loss_awareness", "position_sizing_comment")
LEARNING_FIELDS = (
    "setup_signature",
    "decision_taken",
    "lesson_if_win",
    "lesson_if_loss",
    "promotion_candidate",
    "do_not_promote_reason",
)
FUTURE_LEAK_PHRASES = (
    "later candles show",
    "as we can see after",
    "future price",
    "the next bars confirm",
    "subsequent move proves",
    "after the decision",
    "in the next 15 minutes",
    "next candle shows",
    "next candle will",
    "we now know",
)

CATEGORIES = (
    "clean_long_continuation",
    "clean_short_continuation",
    "range_chop",
    "false_breakout",
    "failed_breakdown",
    "high_volatility_trap",
    "low_volatility_dead_zone",
    "conflicting_indicators",
    "good_trade_that_loses",
    "bad_trade_that_wins",
    "missed_opportunity",
)


# ---------------------------------------------------------------------------
# Phase 1 — data load (read-only)
# ---------------------------------------------------------------------------

def open_ro(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SystemExit(f"DATA_LOAD_FAIL — db not found: {db_path}")
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def resolve_columns(conn: sqlite3.Connection, table: str) -> dict[str, str | None]:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if not cols:
        raise SystemExit(f"DATA_LOAD_FAIL — table missing or empty schema: {table}")

    ts = next((c for c in ("candle_open_utc", "open_time", "timestamp", "ts") if c in cols), None)
    sym = next((c for c in ("canonical_symbol", "symbol", "tick_symbol") if c in cols), None)
    o = "open" if "open" in cols else None
    h = "high" if "high" in cols else None
    low = "low" if "low" in cols else None
    cl = "close" if "close" in cols else None
    vol = next((c for c in ("volume_base", "volume", "quote_volume") if c in cols), None)

    missing = [n for n, v in [("timestamp", ts), ("symbol", sym), ("open", o), ("high", h), ("low", low), ("close", cl)] if v is None]
    if missing:
        raise SystemExit(f"DATA_LOAD_FAIL — missing required columns: {missing} (have {sorted(cols)})")
    return {"ts": ts, "symbol": sym, "open": o, "high": h, "low": low, "close": cl, "vol": vol}


def parse_ts_to_epoch(value: Any) -> int:
    """Return UTC epoch seconds. Accepts ISO8601 string or numeric ms/seconds."""
    if isinstance(value, (int, float)):
        v = int(value)
        return v // 1000 if v > 10_000_000_000 else v
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"DATA_LOAD_FAIL — unparsable timestamp: {value!r}") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_bars_5m(
    conn: sqlite3.Connection, table: str, columns: dict[str, str | None], symbol: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sym_col = columns["symbol"]
    if symbol is None:
        row = conn.execute(
            f'SELECT {sym_col}, COUNT(*) AS n FROM "{table}" GROUP BY {sym_col} ORDER BY n DESC LIMIT 1'
        ).fetchone()
        if not row:
            raise SystemExit("DATA_LOAD_FAIL — table has no rows")
        symbol = row[0]

    select_cols = [columns["ts"], columns["open"], columns["high"], columns["low"], columns["close"]]
    if columns["vol"]:
        select_cols.append(columns["vol"])

    sql = (
        f'SELECT {",".join(select_cols)} FROM "{table}" WHERE {sym_col} = ? ORDER BY {columns["ts"]} ASC'
    )
    rows = conn.execute(sql, (symbol,)).fetchall()
    if not rows:
        raise SystemExit(f"DATA_LOAD_FAIL — no rows for symbol {symbol!r}")

    bars: list[dict[str, Any]] = []
    vol_warnings = 0
    for r in rows:
        try:
            ts = parse_ts_to_epoch(r[0])
            o, h, low, cl = float(r[1]), float(r[2]), float(r[3]), float(r[4])
        except (TypeError, ValueError):
            continue
        if columns["vol"] and len(r) >= 6 and r[5] is not None:
            try:
                v = float(r[5])
            except (TypeError, ValueError):
                v = 0.0
                vol_warnings += 1
        else:
            v = 0.0
            vol_warnings += 1
        bars.append({"t": ts, "o": o, "h": h, "l": low, "c": cl, "v": v})

    profile = {
        "symbol": symbol,
        "rows_total_in_table": int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]),
        "rows_for_symbol": len(bars),
        "first_ts_utc": _epoch_to_iso(bars[0]["t"]),
        "last_ts_utc": _epoch_to_iso(bars[-1]["t"]),
        "vol_warnings": vol_warnings,
        "vol_column": columns["vol"],
    }
    return bars, profile


def _epoch_to_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Phase 2 — 5m -> 15m resample
# ---------------------------------------------------------------------------

def resample_to_15m(bars5: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not bars5:
        raise SystemExit("RESAMPLE_15M_FAIL — empty input")
    out: list[dict[str, Any]] = []
    incomplete = 0
    bucket: list[dict[str, Any]] = []
    bucket_open: int | None = None
    for b in bars5:
        b_open = (b["t"] // 900) * 900
        if bucket_open is None:
            bucket_open = b_open
        if b_open != bucket_open:
            if bucket:
                if len(bucket) < 3:
                    incomplete += 1
                else:
                    out.append(_combine_bucket(bucket_open, bucket))
            bucket = []
            bucket_open = b_open
        bucket.append(b)
    if bucket:
        if len(bucket) < 3:
            incomplete += 1
        else:
            out.append(_combine_bucket(bucket_open, bucket))
    return out, incomplete


def _combine_bucket(bucket_open: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "t": bucket_open,
        "o": items[0]["o"],
        "h": max(b["h"] for b in items),
        "l": min(b["l"] for b in items),
        "c": items[-1]["c"],
        "v": sum(b["v"] for b in items),
        "n5": len(items),
    }


# ---------------------------------------------------------------------------
# Phase 3 — features
# ---------------------------------------------------------------------------

def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def rsi(closes: list[float], period: int = 14) -> list[float]:
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    out = [50.0] * len(closes)
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    out[period] = 100.0 - (100.0 / (1.0 + (avg_g / avg_l if avg_l > 0 else 1e9)))
    for i in range(period + 1, len(closes)):
        avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
        avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        rs = avg_g / avg_l if avg_l > 0 else 1e9
        out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if not closes:
        return []
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    out = [trs[0]] * len(trs)
    if len(trs) >= period:
        out[period - 1] = sum(trs[:period]) / period
        for i in range(period, len(trs)):
            out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    return out


def build_features(bars: list[dict[str, Any]]) -> list[dict[str, float]]:
    closes = [b["c"] for b in bars]
    highs = [b["h"] for b in bars]
    lows = [b["l"] for b in bars]
    vols = [b["v"] for b in bars]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    atr14 = atr(highs, lows, closes, 14)

    out: list[dict[str, float]] = []
    for i, c in enumerate(closes):
        atr_ratio = atr14[i] / c if c else 0.0
        close_vs_ema200 = (c - ema200[i]) / ema200[i] if ema200[i] else 0.0
        recent_return = (c - closes[i - 12]) / closes[i - 12] if i >= 12 and closes[i - 12] else 0.0
        if i >= 20:
            recent_vols = vols[i - 19 : i + 1]
            avg_v = statistics.mean(recent_vols) if recent_vols else 0.0
            vol_ratio = vols[i] / avg_v if avg_v > 0 else 1.0
        else:
            vol_ratio = 1.0
        out.append(
            {
                "ema20": round(ema20[i], 6),
                "ema50": round(ema50[i], 6),
                "ema200": round(ema200[i], 6),
                "rsi14": round(rsi14[i], 3),
                "atr14": round(atr14[i], 6),
                "atr_ratio": round(atr_ratio, 6),
                "close_vs_ema200": round(close_vs_ema200, 6),
                "recent_return_3h": round(recent_return, 6),
                "vol_ratio": round(vol_ratio, 4),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Phase 4 — case generation
# ---------------------------------------------------------------------------

def select_case_indices(
    n_total: int, lookback: int, hidden: int, n_cases: int, seed: int
) -> list[int]:
    lo = max(lookback, 200)
    hi = n_total - hidden - 1
    if hi - lo < n_cases:
        return list(range(lo, hi + 1))
    step = (hi - lo) / float(n_cases)
    rng = random.Random(seed)
    picks: list[int] = []
    for k in range(n_cases):
        center = int(lo + step * (k + 0.5))
        jitter = rng.randint(-2, 2)
        picks.append(max(lo, min(hi, center + jitter)))
    return sorted(set(picks))


def categorize_case(
    bars: list[dict[str, Any]], features: list[dict[str, float]], idx: int, hidden: int
) -> str:
    f = features[idx]
    entry_close = bars[idx]["c"]
    future_bars = bars[idx + 1 : idx + 1 + hidden]
    if not future_bars:
        return "range_chop"
    fut_high = max(b["h"] for b in future_bars)
    fut_low = min(b["l"] for b in future_bars)
    fut_close = future_bars[-1]["c"]
    atr14 = f["atr14"] or (entry_close * 0.001)
    up_excursion = (fut_high - entry_close) / atr14
    dn_excursion = (entry_close - fut_low) / atr14
    net = (fut_close - entry_close) / atr14
    rsi_v = f["rsi14"]
    trend_up = entry_close > f["ema200"] and f["ema20"] > f["ema50"]
    trend_dn = entry_close < f["ema200"] and f["ema20"] < f["ema50"]
    realized_range = (fut_high - fut_low) / (atr14 if atr14 else 1.0)

    if up_excursion >= 2.5 and net >= 1.5 and trend_up:
        return "clean_long_continuation"
    if dn_excursion >= 2.5 and net <= -1.5 and trend_dn:
        return "clean_short_continuation"
    if up_excursion >= 2.0 and net <= 0.0:
        return "false_breakout"
    if dn_excursion >= 2.0 and net >= 0.0:
        return "failed_breakdown"
    if realized_range >= 6.0:
        return "high_volatility_trap"
    if realized_range <= 1.2:
        return "low_volatility_dead_zone"
    if (rsi_v < 35 and trend_up) or (rsi_v > 65 and trend_dn):
        return "conflicting_indicators"
    if abs(net) < 0.5 and realized_range < 4.0:
        return "range_chop"
    if up_excursion >= 1.5 and net >= 0.5 and not trend_up:
        return "bad_trade_that_wins"
    if dn_excursion >= 1.5 and net <= -0.5 and not trend_dn:
        return "missed_opportunity"
    return "good_trade_that_loses"


def build_cases(
    bars15: list[dict[str, Any]],
    features: list[dict[str, float]],
    indices: list[int],
    lookback: int,
    hidden: int,
    symbol: str,
    policy_rules: list[str],
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for idx in indices:
        decision_time = _epoch_to_iso(bars15[idx]["t"] + 900)  # decision moment = bucket close
        recent = bars15[idx - lookback + 1 : idx + 1]
        recent_compact = [
            {
                "t": _epoch_to_iso(b["t"]),
                "o": round(b["o"], 4),
                "h": round(b["h"], 4),
                "l": round(b["l"], 4),
                "c": round(b["c"], 4),
                "v": round(b["v"], 4),
            }
            for b in recent
        ]
        category = categorize_case(bars15, features, idx, hidden)
        case_id = f"FQB-{idx:06d}-{uuid.uuid4().hex[:6]}"
        cases.append(
            {
                "case_id": case_id,
                "symbol": symbol,
                "timeframe": "15m",
                "decision_time": decision_time,
                "lookback_candles": len(recent_compact),
                "feature_snapshot": features[idx],
                "policy_rules": policy_rules,
                "allowed_data_boundary": decision_time,
                "hidden_future_window_id": f"HFW-{idx:06d}",
                "category_truth_hidden": category,
                "_internal_idx": idx,
                "candles_recent": recent_compact,
            }
        )
    return cases


# ---------------------------------------------------------------------------
# Phase 5 — model calls
# ---------------------------------------------------------------------------

POLICY_RULES_DEFAULT = [
    "NO_TRADE is always acceptable when evidence is insufficient.",
    "Trade decisions must include invalidation.",
    "Trade decisions must include a risk plan with stop, target, max-loss awareness, and sizing comment.",
    "Long bias requires trend/risk support.",
    "Short bias requires trend/risk support.",
    "Avoid overtrading in chop or conflicting conditions.",
    "Avoid entries in excessive volatility unless explicitly justified.",
    "Do not mention future movement except as hypothetical risk planning.",
]


def build_prompt(case: dict[str, Any]) -> str:
    visible = {k: v for k, v in case.items() if k not in ("category_truth_hidden", "_internal_idx")}
    schema_doc = {
        "schema_version": SCHEMA_VERSION,
        "case_id": "<echo case_id>",
        "decision": "ENTER | NO_TRADE",
        "direction": "LONG | SHORT | NONE",
        "confidence": "0.0..1.0",
        "thesis": "string",
        "competing_hypothesis": "string",
        "invalidation": "string (required for ENTER)",
        "risk_plan": {k: "string" for k in RISK_FIELDS},
        "why_no_trade": "string (required for NO_TRADE)",
        "expected_failure_mode": "string",
        "learning_record_candidate": {
            "setup_signature": "string",
            "decision_taken": "ENTER|NO_TRADE",
            "lesson_if_win": "string",
            "lesson_if_loss": "string",
            "promotion_candidate": "true|false",
            "do_not_promote_reason": "string when promotion_candidate is false",
        },
    }
    return (
        "You are FinQuant. Use ONLY the supplied pre-reveal market data.\n"
        "Do not infer or reference future candles. Return STRICT JSON only.\n"
        "No markdown. No prose outside JSON. No code fences.\n"
        "If no trade is justified, choose NO_TRADE with NONE direction and a specific why_no_trade.\n"
        "Missing risk logic, missing invalidation, or invalid learning record == failure.\n\n"
        f"REQUIRED OUTPUT SCHEMA:\n{json.dumps(schema_doc, indent=2)}\n\n"
        f"CASE:\n{json.dumps(visible, separators=(',', ':'))}\n"
    )


def call_ollama(
    base_url: str, model: str, prompt: str, temperature: float, top_p: float, num_predict: int, timeout: int
) -> tuple[str, dict[str, Any]]:
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "top_p": top_p, "num_predict": num_predict},
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    dt = time.monotonic() - t0
    parsed = json.loads(raw)
    text = str(parsed.get("response") or "")
    meta = {
        "elapsed_s": round(dt, 3),
        "eval_count": parsed.get("eval_count"),
        "prompt_eval_count": parsed.get("prompt_eval_count"),
        "model": parsed.get("model") or model,
    }
    return text, meta


def ping_ollama(base_url: str, model: str) -> dict[str, Any]:
    try:
        with urlrequest.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=8) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except (urlerror.URLError, socket.timeout) as e:
        raise SystemExit(f"MODEL_ENDPOINT_FAIL — cannot reach {base_url}: {e}") from e
    names = [m.get("name") for m in tags.get("models", []) if m.get("name")]
    if model not in names:
        raise SystemExit(f"MODEL_ENDPOINT_FAIL — model {model!r} not loaded; available: {names}")
    return {"models_available": names, "selected_model": model}


# ---------------------------------------------------------------------------
# Phase 6 — validation
# ---------------------------------------------------------------------------

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_REASONING_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json(text: str) -> tuple[dict[str, Any] | None, str]:
    """Strip <think> blocks, code fences, then find the largest JSON object."""
    cleaned = _THINK_RE.sub("", text or "").strip()
    fence = _REASONING_FENCE_RE.findall(cleaned)
    candidates: list[str] = []
    if fence:
        candidates.extend(f.strip() for f in fence)
    m = _JSON_OBJECT_RE.search(cleaned)
    if m:
        candidates.append(m.group(0))
    last_err = "no_json_object"
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj, ""
        except json.JSONDecodeError as e:
            last_err = f"json_decode:{e.msg}"
    return None, last_err


def validate_output(case: dict[str, Any], parsed: dict[str, Any] | None, raw: str) -> dict[str, Any]:
    buckets: list[str] = []
    detail: list[str] = []
    if parsed is None:
        return {
            "schema_valid": False,
            "future_leakage": False,
            "risk_complete": False,
            "no_trade_quality": False,
            "learning_record_valid": False,
            "buckets": ["invalid_json"],
            "detail": "no parseable JSON",
        }

    missing = [k for k in REQUIRED_TOP_FIELDS if k not in parsed]
    if missing:
        buckets.append("missing_required_field")
        detail.append(f"missing top fields: {missing}")

    decision = parsed.get("decision")
    direction = parsed.get("direction")
    if decision not in ("ENTER", "NO_TRADE"):
        buckets.append("bad_enum")
        detail.append(f"bad decision: {decision!r}")
    if direction not in ("LONG", "SHORT", "NONE"):
        buckets.append("bad_enum")
        detail.append(f"bad direction: {direction!r}")

    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        buckets.append("bad_enum")
        detail.append(f"bad confidence: {confidence!r}")

    risk = parsed.get("risk_plan") or {}
    risk_missing = [k for k in RISK_FIELDS if not str(risk.get(k) or "").strip()]
    if risk_missing:
        buckets.append("missing_risk_plan")
        detail.append(f"risk_plan missing: {risk_missing}")

    invalidation = str(parsed.get("invalidation") or "").strip()
    if decision == "ENTER" and not invalidation:
        buckets.append("missing_invalidation")
    if decision == "ENTER" and direction not in ("LONG", "SHORT"):
        buckets.append("bad_enum")
        detail.append("ENTER with non-trade direction")

    why_nt = str(parsed.get("why_no_trade") or "").strip().lower()
    no_trade_quality_ok = True
    if decision == "NO_TRADE":
        if direction != "NONE":
            buckets.append("bad_enum")
            detail.append("NO_TRADE with non-NONE direction")
        if not why_nt or len(why_nt) < 10:
            buckets.append("missing_no_trade_reason")
            no_trade_quality_ok = False
        elif not any(
            tok in why_nt
            for tok in (
                "uncertain",
                "uncertainty",
                "chop",
                "conflict",
                "volatility",
                "invalidation",
                "edge",
                "no edge",
                "thin",
                "weak",
                "unclear",
                "contradict",
                "indeterminate",
            )
        ):
            no_trade_quality_ok = False
            detail.append("no_trade reason too generic")

    learn = parsed.get("learning_record_candidate") or {}
    learn_missing = [k for k in LEARNING_FIELDS if k not in learn]
    learn_valid = True
    if learn_missing:
        learn_valid = False
        buckets.append("invalid_learning_record")
        detail.append(f"learning_record missing: {learn_missing}")
    else:
        if not str(learn.get("setup_signature") or "").strip():
            learn_valid = False
            buckets.append("invalid_learning_record")
        if not str(learn.get("lesson_if_win") or "").strip() or not str(learn.get("lesson_if_loss") or "").strip():
            learn_valid = False
            buckets.append("invalid_learning_record")
        if not isinstance(learn.get("promotion_candidate"), bool):
            learn_valid = False
            buckets.append("invalid_learning_record")
        elif learn.get("promotion_candidate") is False and not str(learn.get("do_not_promote_reason") or "").strip():
            learn_valid = False
            buckets.append("invalid_learning_record")

    text_blob = json.dumps(parsed).lower() + " " + raw.lower()
    leak_hits = [p for p in FUTURE_LEAK_PHRASES if p in text_blob]
    if leak_hits:
        buckets.append("future_leakage_language")

    schema_ok = (
        not missing
        and decision in ("ENTER", "NO_TRADE")
        and direction in ("LONG", "SHORT", "NONE")
        and isinstance(confidence, (int, float))
        and 0.0 <= float(confidence) <= 1.0
        and not risk_missing
    )
    risk_ok = decision == "NO_TRADE" or (not risk_missing and bool(invalidation))

    return {
        "schema_valid": schema_ok,
        "future_leakage": bool(leak_hits),
        "future_leak_phrases": leak_hits,
        "risk_complete": risk_ok,
        "no_trade_quality": (decision != "NO_TRADE") or no_trade_quality_ok,
        "learning_record_valid": learn_valid,
        "buckets": sorted(set(buckets)),
        "detail": "; ".join(detail) if detail else "",
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def classify_readiness(metrics: dict[str, float], thresholds: dict[str, float]) -> str:
    """Per revised directive (2026-05-01): only three classifications.

    Determinism / consistency intentionally NOT a gate at this phase.
    Primary gate: learning_record_valid_rate (learning-record generation
    capability — if invalid, the system is not learning).
    """
    schema = metrics["schema_valid_rate"]
    leakage = metrics["future_leakage_count"]
    risk = metrics["risk_reasoning_rate"]
    learn = metrics["learning_record_valid_rate"]

    if schema < thresholds["schema"] or learn < thresholds["learning"]:
        return "BASELINE_BLOCKED_BY_SCHEMA_OR_LEARNING_RECORDS"
    if leakage > thresholds["leakage_max"] or risk < thresholds["risk"]:
        return "BASELINE_NOT_READY_FOR_PROMOTION"
    return "BASELINE_READY_FOR_BEHAVIOR_TUNING"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    m = report["metrics"]
    cat = report["category_distribution"]
    fails = report["failure_buckets"]
    lines = [
        "# FinQuant v0.05 — Baseline Report",
        "",
        f"- **Run timestamp:** {report['run_started_utc']} → {report['run_finished_utc']}",
        f"- **Host:** {report['host']}",
        f"- **Repo path:** {report['repo_path']}",
        f"- **DB path:** {report['db_path']}",
        f"- **Table:** {report['table']}",
        f"- **Symbol:** {report['symbol']}",
        f"- **5m row count:** {report['data_profile']['rows_for_symbol']}",
        f"- **First/last 5m:** {report['data_profile']['first_ts_utc']} → {report['data_profile']['last_ts_utc']}",
        f"- **15m bars after resample:** {report['bars_15m_count']}",
        f"- **Model endpoint:** {report['ollama_url']}",
        f"- **Model name:** {report['model']}",
        f"- **Cases:** {report['cases_total']} (smoke={report['smoke']})",
        "",
        "## Category Distribution (truth, hidden from model)",
        "",
        "| Category | Count |",
        "|---|---|",
    ]
    for c in CATEGORIES:
        lines.append(f"| {c} | {cat.get(c, 0)} |")

    lines += [
        "",
        "## Metrics",
        "",
        f"- schema_valid_rate: **{m['schema_valid_rate']:.3f}**",
        f"- future_leakage_count: **{m['future_leakage_count']}**",
        f"- risk_reasoning_rate: **{m['risk_reasoning_rate']:.3f}**",
        f"- no_trade_quality_rate: **{m['no_trade_quality_rate']:.3f}**",
        f"- learning_record_valid_rate: **{m['learning_record_valid_rate']:.3f}**  *(primary gate)*",
        f"- decision_distribution: {m['decision_distribution']}",
        "",
        "_Consistency / determinism scoring intentionally OUT OF SCOPE (revised directive 2026-05-01)._ ",
        "",
        "## Failure Buckets",
        "",
        "| Bucket | Count |",
        "|---|---|",
    ]
    for k, v in sorted(fails.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Readiness Classification",
        "",
        f"**{report['readiness_classification']}**",
        "",
        "## Hard-Rule Confirmations",
        "",
        f"- NO_TRAINING_PERFORMED={str(report['no_training_performed']).lower()}",
        f"- READ_ONLY_DB_ACCESS={str(report['read_only_db_access']).lower()}",
        f"- WROTE_ONLY_UNDER_RUN_DIR={str(report['wrote_only_under_run_dir']).lower()}",
        "",
        f"**{report['final_line']}**",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="FinQuant v0.05 baseline harness (no training)")
    p.add_argument("--db", default="data/sqlite/market_data.db")
    p.add_argument("--table", default="market_bars_5m")
    p.add_argument("--symbol", default=None, help="Override symbol (default: most-populated)")
    p.add_argument("--ollama-url", default="http://172.20.2.230:11434")
    p.add_argument("--model", required=True)
    p.add_argument("--cases", type=int, default=100)
    p.add_argument("--lookback", type=int, default=96, help="15m candles, default 96 (24h)")
    p.add_argument("--hidden", type=int, default=16, help="15m candles, default 16 (4h)")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--num-predict", type=int, default=1200)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--smoke", action="store_true", help="Smoke mode: 10 cases")
    p.add_argument("--seed", type=int, default=20260501)
    p.add_argument("--out", default=DEFAULT_OUT_DIR)
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = p.parse_args()

    if args.smoke:
        args.cases = min(args.cases, 10)

    repo_root = Path(args.repo_root).resolve()
    db_path = (Path(args.db) if Path(args.db).is_absolute() else repo_root / args.db).resolve()
    out_root = (Path(args.out) if Path(args.out).is_absolute() else repo_root / args.out).resolve()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_root / f"baseline_{ts}"
    for sub in ("cases", "raw_outputs", "failures", "reports", "debug"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    if repo_root not in run_dir.parents and run_dir != repo_root:
        # safety: must be inside repo (no escape)
        pass
    if not str(run_dir).startswith(str(repo_root)):
        raise SystemExit("SAFETY_FAIL — run_dir is outside repo_root")

    run_started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=" * 72)
    print("FINQUANT v0.05 BASELINE — DRY-RUN HARNESS (no training, no production writes)")
    print(f"  host: {socket.gethostname()}  repo: {repo_root}  out: {run_dir}")
    print(f"  db: {db_path}  table: {args.table}  ollama: {args.ollama_url}  model: {args.model}")
    print("=" * 72)

    # ---------- PHASE 1
    print("\nPHASE_01_DATA_LOAD")
    conn = open_ro(db_path)
    cols = resolve_columns(conn, args.table)
    bars5, profile = load_bars_5m(conn, args.table, cols, args.symbol)
    conn.close()
    print(f"  resolved columns: {cols}")
    print(f"  rows={profile['rows_for_symbol']} symbol={profile['symbol']} "
          f"first={profile['first_ts_utc']} last={profile['last_ts_utc']}")
    if profile["vol_warnings"]:
        print(f"  WARN: {profile['vol_warnings']} bars without volume — set to 0.0")
    print("  DATA_LOAD_PASS")

    # ---------- PHASE 2
    print("\nPHASE_02_RESAMPLE_15M")
    bars15, incomplete = resample_to_15m(bars5)
    print(f"  bars_15m={len(bars15)} incomplete_buckets_skipped={incomplete}")
    if len(bars15) < args.lookback + args.hidden + 5:
        print("  RESAMPLE_15M_FAIL — not enough 15m bars for lookback+hidden")
        return 2
    print("  RESAMPLE_15M_PASS")

    # ---------- PHASE 3
    print("\nPHASE_03_FEATURE_BUILD")
    features = build_features(bars15)
    if len(features) != len(bars15):
        print("  FEATURE_BUILD_FAIL")
        return 2
    print(f"  features built: {len(features)}")
    print("  FEATURE_BUILD_PASS")

    # ---------- PHASE 4
    print("\nPHASE_04_CASE_GENERATION")
    indices = select_case_indices(len(bars15), args.lookback, args.hidden, args.cases, args.seed)
    cases = build_cases(
        bars15, features, indices, args.lookback, args.hidden, profile["symbol"], POLICY_RULES_DEFAULT
    )
    cat_counts: dict[str, int] = {c: 0 for c in CATEGORIES}
    for c in cases:
        cat_counts[c["category_truth_hidden"]] = cat_counts.get(c["category_truth_hidden"], 0) + 1
    cases_path = run_dir / "cases" / "baseline_cases.jsonl"
    with cases_path.open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, separators=(",", ":")) + "\n")
    print(f"  cases={len(cases)} -> {cases_path}")
    print(f"  category_distribution={cat_counts}")
    print("  CASE_GENERATION_PASS")

    # ---------- PHASE 5
    print("\nPHASE_05_MODEL_CALLS")
    endpoint_info = ping_ollama(args.ollama_url, args.model)
    print(f"  endpoint OK; selected={endpoint_info['selected_model']}")

    raw_path = run_dir / "raw_outputs" / "model_outputs.jsonl"
    fail_path = run_dir / "failures" / "failures.jsonl"
    raw_fh = raw_path.open("w", encoding="utf-8")
    fail_fh = fail_path.open("w", encoding="utf-8")

    parsed_outputs: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}
    decisions = {"ENTER": 0, "NO_TRADE": 0, "OTHER": 0}

    for i, case in enumerate(cases, 1):
        prompt = build_prompt(case)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        try:
            text, meta = call_ollama(
                args.ollama_url, args.model, prompt, args.temperature, args.top_p, args.num_predict, args.timeout
            )
            error = None
        except (urlerror.URLError, socket.timeout, json.JSONDecodeError, TimeoutError) as e:
            text, meta, error = "", {"elapsed_s": None}, f"endpoint_error:{e}"

        parsed, parse_err = (None, "no_call") if error else extract_json(text)
        if error:
            v = {
                "schema_valid": False, "future_leakage": False, "risk_complete": False,
                "no_trade_quality": False, "learning_record_valid": False,
                "buckets": ["endpoint_error"], "detail": error,
            }
        else:
            v = validate_output(case, parsed, text)
            if parsed is None and "invalid_json" not in v["buckets"]:
                v["buckets"].append("invalid_json")
            if parse_err and parse_err.startswith("json_decode") and "invalid_json" not in v["buckets"]:
                v["buckets"].append("invalid_json")

        for b in v["buckets"]:
            bucket_counts[b] = bucket_counts.get(b, 0) + 1
        d = parsed.get("decision") if isinstance(parsed, dict) else None
        decisions[d if d in decisions else "OTHER"] += 1

        record = {
            "case_id": case["case_id"],
            "prompt_hash": prompt_hash,
            "model_meta": meta,
            "raw_response_excerpt": text[:4000],
            "parsed": parsed,
            "validation": v,
            "category_truth_hidden": case["category_truth_hidden"],
        }
        raw_fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        if v["buckets"]:
            fail_fh.write(
                json.dumps(
                    {
                        "case_id": case["case_id"],
                        "prompt_hash": prompt_hash,
                        "buckets": v["buckets"],
                        "detail": v.get("detail", ""),
                        "raw_excerpt": text[:1500],
                        "parsed": parsed,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
        parsed_outputs.append(parsed if isinstance(parsed, dict) else {})
        validations.append(v)

        if i % 5 == 0 or i == len(cases):
            print(f"  [{i}/{len(cases)}] {case['case_id']} buckets={v['buckets']} dt={meta.get('elapsed_s')}s")

    raw_fh.close()
    fail_fh.close()

    # ---------- PHASE 6
    print("\nPHASE_06_VALIDATION")
    n = len(validations) or 1
    schema_valid_rate = sum(1 for v in validations if v["schema_valid"]) / n
    risk_reasoning_rate = sum(1 for v in validations if v["risk_complete"]) / n
    no_trade_quality_rate = sum(1 for v in validations if v["no_trade_quality"]) / n
    learning_record_valid_rate = sum(1 for v in validations if v["learning_record_valid"]) / n
    future_leakage_count = sum(1 for v in validations if v["future_leakage"])
    print(
        f"  schema={schema_valid_rate:.3f} risk={risk_reasoning_rate:.3f} "
        f"no_trade_q={no_trade_quality_rate:.3f} learn={learning_record_valid_rate:.3f} "
        f"leak={future_leakage_count}"
    )

    # ---------- PHASE 7 (consistency replay intentionally omitted — directive 2026-05-01)
    print("\nPHASE_07_REPORT_WRITE")
    metrics = {
        "schema_valid_rate": round(schema_valid_rate, 4),
        "future_leakage_count": int(future_leakage_count),
        "risk_reasoning_rate": round(risk_reasoning_rate, 4),
        "no_trade_quality_rate": round(no_trade_quality_rate, 4),
        "learning_record_valid_rate": round(learning_record_valid_rate, 4),
        "decision_distribution": decisions,
    }
    thresholds = {
        "schema": 0.98,
        "leakage_max": 0,
        "risk": 0.95,
        "learning": 0.95,
    }
    classification = classify_readiness(metrics, thresholds)

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_started_utc": run_started,
        "run_finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "host": socket.gethostname(),
        "repo_path": str(repo_root),
        "db_path": str(db_path),
        "table": args.table,
        "symbol": profile["symbol"],
        "data_profile": profile,
        "bars_15m_count": len(bars15),
        "ollama_url": args.ollama_url,
        "model": args.model,
        "cases_total": len(cases),
        "smoke": bool(args.smoke),
        "thresholds": thresholds,
        "metrics": metrics,
        "category_distribution": cat_counts,
        "failure_buckets": bucket_counts,
        "readiness_classification": classification,
        "no_training_performed": True,
        "read_only_db_access": True,
        "wrote_only_under_run_dir": True,
        "consistency_scoring_in_scope": False,
        "directive_revision": "2026-05-01_determinism_descoped",
        "final_line": "FINQUANT_V005_BASELINE_MEASURED_NO_TRAINING_PERFORMED",
    }
    (run_dir / "reports" / "finquant_v005_baseline_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    write_markdown(report, run_dir / "reports" / "finquant_v005_baseline_report.md")
    (run_dir / "debug" / "run_config.json").write_text(json.dumps(vars(args), indent=2), encoding="utf-8")
    (run_dir / "debug" / "data_profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")

    print(f"  report.json: {run_dir / 'reports' / 'finquant_v005_baseline_report.json'}")
    print(f"  report.md:   {run_dir / 'reports' / 'finquant_v005_baseline_report.md'}")
    print(f"  classification: {classification}")
    print(f"  NO_TRAINING_PERFORMED=true")
    print(f"\nFINQUANT_V005_BASELINE_MEASURED_NO_TRAINING_PERFORMED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
