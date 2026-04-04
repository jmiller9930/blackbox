# Event-centric market training view — backend framework (draft)

**Status:** Framework + API contract proposal. **Not fully wired** in `UIUX.Web/api_server.py`; use this to align UI, data owners, and wiring tasks.

**Purpose:** One screen (or route) keyed by **`market_event_id`** (canonical 5m bar identity): **chart (OHLC)** + **all strategies’ actions for that candle** (baseline + Anna) + **decision context** (indicators, narrative). This matches the Training Advisor mock’s *data* goals, not its ASCII layout.

---

## 1. What the UI should receive (v1 contract)

Rough JSON shape the front end can depend on once implemented:

```json
{
  "ok": true,
  "market_event_id": "SOL-PERP_5m_2026-04-01T19:55:00Z",
  "symbol": "SOL-PERP",
  "timeframe": "5m",
  "candle": {
    "open_utc": "2026-04-01T19:55:00Z",
    "close_utc": "2026-04-01T20:00:00Z",
    "open": 83.97,
    "high": 84.50,
    "low": 83.80,
    "close": 84.20,
    "price_source": "…",
    "tick_count": 42
  },
  "trades": [
    {
      "trade_id": "…",
      "lane": "baseline",
      "strategy_id": "baseline",
      "mode": "paper",
      "side": "long",
      "entry_price": 83.97,
      "exit_price": 84.20,
      "size": 1.0,
      "exit_reason": "CLOSE",
      "pnl_usd": 0.23,
      "economic": true,
      "context_snapshot": {}
    },
    {
      "lane": "anna",
      "strategy_id": "monopoly",
      "mode": "paper_stub",
      "side": "long",
      "entry_price": 84.0,
      "exit_price": 84.0,
      "pnl_usd": null,
      "economic": false,
      "synthetic": { "stub_result": "lost", "stub_pnl_usd": -0.12 },
      "context_snapshot": { "synthetic": true, "stub_result": "lost", "stub_pnl_usd": -0.12, "bar": {} }
    }
  ],
  "strategies_absent": [],
  "indicators": {
    "rsi": null,
    "supertrend": null,
    "atr_ratio": null,
    "price_vs_ema200": null,
    "source": "not_wired"
  },
  "narrative": {
    "signal_breakdown": null,
    "source": "not_wired"
  },
  "meta": {
    "ledger_path": null,
    "bar_query": "market_bars_5m + market_event_id"
  }
}
```

**UI rules (align with ledger policy):**

- **`economic`**: `true` only when `mode` is `live` or `paper` and `pnl_usd` is derivable (see `modules/anna_training/execution_ledger.py` — `is_economic_mode`).
- **`paper_stub`**: show **non-dollar** synthetic fields from `context_snapshot` (e.g. `stub_pnl_usd`) as **classification / experiment**, not as portfolio P&amp;L.

**“NO TRADE” for a strategy:** Today there is often **no row** in `execution_trades`. The API can either omit that strategy or list it under **`strategies_absent`** / **`catalog_strategies`** with `outcome: "no_row"` — **product choice** (see §5).

---

## 2. Backend layers (conceptual)

| Layer | Responsibility | Ground truth today |
|--------|----------------|---------------------|
| **Identity** | `market_event_id`, symbol, timeframe | `scripts/runtime/market_data/market_event_id.py`; column on `market_bars_5m` |
| **OHLC bar** | Single closed 5m candle | `data/sqlite/market_data.db` → `market_bars_5m` (`scripts/runtime/market_data/bar_lookup.py`, `store.py`) |
| **Execution rows** | Baseline + per-strategy fills for that event | `data/sqlite/execution_ledger.db` → `execution_trades` (`modules/anna_training/execution_ledger.py`) |
| **Indicators / overlays** | RSI, Supertrend, EMA200, ATR, etc. | **Not** a first-class column on the ledger; may exist inside **Anna analysis** snapshots **per tick**, not necessarily **per historical event** — **gap** |
| **Narrative / signal breakdown** | Human-readable “why” | Optional JSON in `context_snapshot` or future `narrative` table — **gap** |

---

## 3. Proposed API surface (to implement)

| Method | Path (proposal) | Role |
|--------|------------------|------|
| `GET` | `/api/v1/anna/market-event/{market_event_id}` | **Single event** payload (§1) for chart + table + context strip |
| `GET` | `/api/v1/anna/market-events?symbol=SOL-PERP&limit=50` | **Recent events** (for picker / back navigation) — optional v2 |

**Where to wire:** `UIUX.Web/api_server.py` — mirror patterns used for `GET /api/v1/anna/training-dashboard` (same auth/CORS assumptions as today).

**Server-side assembly (new module, suggested):**

- `modules/anna_training/market_event_view.py` (or `execution_ledger_view.py`):
  - `load_market_event_bundle(market_event_id: str) -> dict`  
  - Reads: `fetch_bar_by_market_event_id` or `bar_lookup` + `query_trades_by_market_event_id` + `parse_market_event_id` for sanity.
  - Maps rows to **`economic`** / **`synthetic`** for the UI.
  - **`indicators` / `narrative`**: return structured `null` + `source: "not_wired"` until a feed exists (§4).

**CLI (optional, for operators without UI):**

- `anna_training_cli.py market-event-show --id SOL-PERP_5m_...` → same JSON to stdout (helps clawbot/debug).

---

## 4. Wiring checklist (files and gaps)

| Piece | Location | Status |
|--------|-----------|--------|
| Canonical bar by id | `scripts/runtime/market_data/store.py` — `fetch_bar_by_market_event_id` | **Exists** — use for `candle` block |
| Latest bar / id | `scripts/runtime/market_data/bar_lookup.py` | **Exists** |
| Trades for event | `modules/anna_training/execution_ledger.py` — `query_trades_by_market_event_id` | **Exists** |
| PnL policy / economic flag | `execution_ledger.py` — `is_economic_mode`, `compute_pnl_usd` | **Exists** |
| Aggregate bundle for API | New helper + route in `api_server.py` | **TODO** |
| Indicators keyed by `market_event_id` | No single table in repo | **TODO** — options: (a) snapshot at write time into `context_snapshot`, (b) join batch job table `market_event_features`, (c) recompute from ticks (heavy) |
| “Last tick” analysis | Training dashboard already exposes **`analysis_snapshot`** | **Per tick**, not per arbitrary **historical** event — **partial** |
| Auth | Same as existing `/api/v1/anna/*` | **Confirm** with operator (internal-only vs session) |

---

## 5. Decisions to confirm (pushback / open questions)

1. **Scope of v1:** Ship **single-event** GET first with **bar + trades** only, and **`indicators`/`narrative` as explicit nulls** — or wait until one indicator source is wired?
2. **Strategies with no row:** Prefer **implicit** (only strategies that have rows) or **explicit** list (**catalog** strategies minus rows ⇒ “NO TRADE”)?
3. **Hosting:** Same process as `UIUX.Web/api_server.py` on clawbot/lab only, or also expose via another gateway?
4. **Chart data:** v1 **single candle + markers** only, or require **N bars of history** around the event for chart libraries (extra query on `market_bars_5m`)?

Once (1)–(4) are answered, the API handler can be stubbed to return §1 with real `candle` + `trades` and placeholder `indicators`, then filled incrementally.

---

## 6. Related docs / code

- Execution ledger schema: `data/sqlite/schema_execution_ledger.sql`
- PnL integrity: `modules/anna_training/execution_ledger.py`
- Training dashboard (rolling, not event-centric): `GET /api/v1/anna/training-dashboard` in `UIUX.Web/api_server.py`
- School / ledger overview: `docs/architect/ANNA_GOES_TO_SCHOOL.md`
