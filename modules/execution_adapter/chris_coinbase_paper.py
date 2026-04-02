"""
Chris Coinbase paper adapter (CANONICAL #137 draft).

Read-only Coinbase status checks + deterministic paper submit mapping:
paper_submitted | venue_unavailable | venue_reject.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from modules.execution_adapter.models import ExecutionAdapterOutcomeV1, ExecutionAdapterRequestV1
from modules.execution_adapter.paper import PaperSubmitResult, PaperVenueScenario, submit_paper_adapter
from modules.execution_adapter.validation import (
    EXA_SCOPE_003,
    AdapterValidationResult,
    _ok,
    validate_execution_adapter_outcome,
    validate_outcome_lineage_for_replay,
)
from modules.execution_artifacts.models import ExecutionIntentV1

USER_AGENT = "blackbox-chris-coinbase-paper/137 (+read-only)"
CHRIS_COINBASE_PAPER_LANE = "chris_coinbase_paper_v1"


@dataclass(frozen=True)
class CoinbasePaperStatusV1:
    candles_state: str  # healthy | stale | down
    lob_state: str  # healthy | unavailable
    last_checked_at: str
    reason_code: str | None


@dataclass(frozen=True)
class CoinbaseCandle5mV1:
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class CoinbaseL2SampleV1:
    best_bid: float
    best_ask: float
    spread: float
    depth_rows: int


@dataclass(frozen=True)
class ChrisCoinbasePaperSubmitResult:
    outcome: ExecutionAdapterOutcomeV1 | None
    result: AdapterValidationResult
    status: CoinbasePaperStatusV1


def validate_chris_coinbase_paper_handoff(
    req: ExecutionAdapterRequestV1,
    intent: ExecutionIntentV1,
) -> AdapterValidationResult:
    if req.interaction_path != CHRIS_COINBASE_PAPER_LANE:
        return AdapterValidationResult(
            ok=False,
            reason_code=EXA_SCOPE_003,
            reason="ExecutionAdapterRequestV1.interaction_path must be chris_coinbase_paper_v1 for Chris paper lane",
        )
    if intent.interaction_path != CHRIS_COINBASE_PAPER_LANE:
        return AdapterValidationResult(
            ok=False,
            reason_code=EXA_SCOPE_003,
            reason="ExecutionIntentV1.interaction_path must be chris_coinbase_paper_v1 for Chris paper lane",
        )
    if req.interaction_path != intent.interaction_path:
        return AdapterValidationResult(
            ok=False,
            reason_code=EXA_SCOPE_003,
            reason="interaction_path mismatch between request and intent for Chris paper lane",
        )
    return _ok()


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_coinbase_time(ts: Any) -> datetime | None:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    if isinstance(ts, str):
        t = ts.strip()
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(t)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _f(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _get_json(url: str, *, timeout: float) -> Any:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_coinbase_5m_candles(
    *,
    product_id: str = "SOL-USD",
    timeout: float = 20.0,
) -> list[CoinbaseCandle5mV1]:
    """
    Required 12th-grade paper dataset contract:
    timestamp_utc, open, high, low, close, volume (5m candles).
    """
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles?granularity=300"
    raw = _get_json(url, timeout=timeout)
    if not isinstance(raw, list):
        return []
    out: list[CoinbaseCandle5mV1] = []
    for row in raw:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts = _parse_coinbase_time(row[0])
        low = _f(row[1])
        high = _f(row[2])
        opn = _f(row[3])
        close = _f(row[4])
        vol = _f(row[5])
        if ts is None or None in (low, high, opn, close, vol):
            continue
        out.append(
            CoinbaseCandle5mV1(
                timestamp_utc=_iso_utc(ts),
                open=float(opn),
                high=float(high),
                low=float(low),
                close=float(close),
                volume=float(vol),
            )
        )
    # Coinbase can return newest-first; normalize oldest->newest.
    out.sort(key=lambda c: c.timestamp_utc)
    return out


def fetch_coinbase_l2_sample(
    *,
    product_id: str = "SOL-USD",
    timeout: float = 20.0,
) -> CoinbaseL2SampleV1 | None:
    """
    Optional market-structure sample:
    best_bid, best_ask, spread, depth_rows.
    """
    url = f"https://api.exchange.coinbase.com/products/{product_id}/book?level=2"
    raw = _get_json(url, timeout=timeout)
    if not isinstance(raw, dict):
        return None
    bids = raw.get("bids")
    asks = raw.get("asks")
    if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
        return None
    bb = _f(bids[0][0] if isinstance(bids[0], list) and bids[0] else None)
    ba = _f(asks[0][0] if isinstance(asks[0], list) and asks[0] else None)
    if bb is None or ba is None:
        return None
    spread = ba - bb
    depth_rows = min(len(bids), len(asks))
    return CoinbaseL2SampleV1(best_bid=bb, best_ask=ba, spread=spread, depth_rows=depth_rows)


def fetch_coinbase_paper_status(
    *,
    product_id: str = "SOL-USD",
    max_candle_age_sec: float = 1200.0,
    timeout: float = 20.0,
) -> CoinbasePaperStatusV1:
    """
    Read-only health check used by Chris paper lane.

    - candles_state is required: healthy/stale/down
    - lob_state is optional: healthy/unavailable
    """
    last_checked = _iso_now()
    try:
        candles = fetch_coinbase_5m_candles(product_id=product_id, timeout=timeout)
        if not candles:
            return CoinbasePaperStatusV1(
                candles_state="down",
                lob_state="unavailable",
                last_checked_at=last_checked,
                reason_code="COIN-PAPER-CANDLES-EMPTY",
            )
        t0 = _parse_coinbase_time(candles[-1].timestamp_utc)
        if t0 is None:
            return CoinbasePaperStatusV1(
                candles_state="down",
                lob_state="unavailable",
                last_checked_at=last_checked,
                reason_code="COIN-PAPER-CANDLES-TIME",
            )
        age = (datetime.now(timezone.utc) - t0).total_seconds()
        candles_state = "healthy" if age <= max_candle_age_sec else "stale"
        reason_code = None if candles_state == "healthy" else "COIN-PAPER-CANDLES-STALE"
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return CoinbasePaperStatusV1(
            candles_state="down",
            lob_state="unavailable",
            last_checked_at=last_checked,
            reason_code="COIN-PAPER-CANDLES-DOWN",
        )

    lob_state = "unavailable"
    try:
        lob = fetch_coinbase_l2_sample(product_id=product_id, timeout=timeout)
        if lob is not None:
            lob_state = "healthy"
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        lob_state = "unavailable"

    return CoinbasePaperStatusV1(
        candles_state=candles_state,
        lob_state=lob_state,
        last_checked_at=last_checked,
        reason_code=reason_code,
    )


def submit_chris_coinbase_paper_adapter(
    req: ExecutionAdapterRequestV1,
    intent: ExecutionIntentV1,
    *,
    now_utc: datetime,
    idempotency_registry: dict[tuple[str, str, str], str],
    scenario: PaperVenueScenario,
    outcome_id: str,
    venue_order_id: str,
    submitted_at_utc: str,
    coinbase_status: CoinbasePaperStatusV1 | None = None,
) -> ChrisCoinbasePaperSubmitResult:
    """
    Chris lane handoff + read-only status gate + deterministic paper submit mapping.
    """
    st = coinbase_status if coinbase_status is not None else fetch_coinbase_paper_status()
    h = validate_chris_coinbase_paper_handoff(req, intent)
    if not h.ok:
        return ChrisCoinbasePaperSubmitResult(outcome=None, result=h, status=st)

    if st.candles_state == "down":
        forced = PaperVenueScenario.UNAVAILABLE
    else:
        forced = scenario

    r: PaperSubmitResult = submit_paper_adapter(
        req,
        intent,
        now_utc=now_utc,
        venue_name=CHRIS_COINBASE_PAPER_LANE,
        idempotency_registry=idempotency_registry,
        scenario=forced,
        outcome_id=outcome_id,
        venue_order_id=venue_order_id,
        submitted_at_utc=submitted_at_utc,
    )
    if not r.result.ok or r.outcome is None:
        return ChrisCoinbasePaperSubmitResult(outcome=None, result=r.result, status=st)

    vo = validate_execution_adapter_outcome(r.outcome)
    if not vo.ok:
        return ChrisCoinbasePaperSubmitResult(outcome=None, result=vo, status=st)
    lr = validate_outcome_lineage_for_replay(r.outcome, req, intent)
    if not lr.ok:
        return ChrisCoinbasePaperSubmitResult(outcome=None, result=lr, status=st)
    return ChrisCoinbasePaperSubmitResult(outcome=r.outcome, result=r.result, status=st)

