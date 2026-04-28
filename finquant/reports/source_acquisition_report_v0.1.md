# FinQuant-1 Source Acquisition Report v0.1

**Training:** not started (dataset construction only).

## Paths

- Base: `/Users/bigmac/Documents/code_projects/blackbox/finquant`
- Output JSONL: `/Users/bigmac/Documents/code_projects/blackbox/finquant/datasets/finquant_source_v0.1.jsonl`
- Manifest: `/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/manifest.json`
- Market DB used: `/Users/bigmac/Documents/code_projects/blackbox/data/sqlite/market_data.db`

## What was pulled

See `sources/manifest.json` for HTTP/HF outcomes. Inline snapshot (may be truncated):

```json
{
  "ts": 1777403844.805713,
  "base": "/Users/bigmac/Documents/code_projects/blackbox/finquant",
  "exchange_docs": [
    {
      "slug": "binance",
      "url": "https://binance-docs.github.io/apidocs/futures/en/",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/binance.html",
      "http_status": 200,
      "sha256": "a317413c70327c3b457c24b6619cecbfa842082201c832ffaec6dd1e4aff1af2",
      "bytes": 325
    },
    {
      "slug": "binance_mark_price",
      "url": "https://binance-docs.github.io/apidocs/futures/en/#mark-price",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/binance_mark_price.html",
      "http_status": 200,
      "sha256": "a317413c70327c3b457c24b6619cecbfa842082201c832ffaec6dd1e4aff1af2",
      "bytes": 325
    },
    {
      "slug": "binance_funding",
      "url": "https://binance-docs.github.io/apidocs/futures/en/#funding-rate",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/binance_funding.html",
      "http_status": 200,
      "sha256": "a317413c70327c3b457c24b6619cecbfa842082201c832ffaec6dd1e4aff1af2",
      "bytes": 325
    },
    {
      "slug": "binance_liquidation",
      "url": "https://binance-docs.github.io/apidocs/futures/en/#liquidation-orders",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/binance_liquidation.html",
      "http_status": 200,
      "sha256": "a317413c70327c3b457c24b6619cecbfa842082201c832ffaec6dd1e4aff1af2",
      "bytes": 325
    },
    {
      "slug": "deribit",
      "url": "https://docs.deribit.com/",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/deribit.html",
      "http_status": 200,
      "sha256": "5c6b417455c3327308d249f8d36c7ae02451e68bf18713470b39e44b080e2a05",
      "bytes": 946621
    },
    {
      "slug": "deribit_public",
      "url": "https://docs.deribit.com/#public-methods",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/deribit_public.html",
      "http_status": 200,
      "sha256": "5c6b417455c3327308d249f8d36c7ae02451e68bf18713470b39e44b080e2a05",
      "bytes": 946621
    },
    {
      "slug": "bybit",
      "url": "https://bybit-exchange.github.io/docs/",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/bybit.html",
      "http_status": 200,
      "sha256": "bd3437f59469e82531140055a121ebe6c585e18e33f96692dcb4b881b79bfc6f",
      "bytes": 22204
    },
    {
      "slug": "bybit_linear",
      "url": "https://bybit-exchange.github.io/docs/v5/market/mark-kline",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/bybit_linear.html",
      "http_status": 200,
      "sha256": "15af12563825281070d67b0e4708147941a5281c332352aa60bd581ba25258d1",
      "bytes": 75386
    },
    {
      "slug": "kraken",
      "url": "https://docs.kraken.com/api/",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/exchange_docs/kraken.html",
      "http_status": 200,
      "sha256": "81c1d0123231559942a24489e3ec03062f80a5c3223743b07cdd4018c1245ede",
      "bytes": 14243
    },
    {
      "slug": "kraken_futures",
      "url": "https://docs.kraken.com/api/docs/futures-api/trading/introduction/",
      "error": "<HTTPError 404: 'Not Found'>"
    }
  ],
  "wikipedia_rest": [
    {
      "title": "Z-score",
      "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Z-score",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/wikipedia_rest/Z-score.json",
      "http_status": 200,
      "sha256": "ebcb5657cde5016bd6ce32303223f4f2ffcb94e401231b00bffcc5636fba94a6"
    },
    {
      "title": "Volatility_(finance)",
      "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Volatility_%28finance%29",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/wikipedia_rest/Volatility_(finance).json",
      "http_status": 200,
      "sha256": "06dcaa4eb23d924f6d5c8b044e2271a7236ae203647fd2271b620d9578836f8d"
    },
    {
      "title": "Cointegration",
      "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Cointegration",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/wikipedia_rest/Cointegration.json",
      "http_status": 200,
      "sha256": "f54315afd075f901e3faaf8c56610ff640a428d3609bf94ec19d775f74f28654"
    },
    {
      "title": "Relative_strength_index",
      "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Relative_strength_index",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/wikipedia_rest/Relative_strength_index.json",
      "http_status": 200,
      "sha256": "4551d58186ce8e863700348c2bf7e0f16170965222a6fb7d9886703e624858a3"
    },
    {
      "title": "Average_true_range",
      "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Average_true_range",
      "path": "/Users/bigmac/Documents/code_projects/blackbox/finquant/sources/raw/wikipedia_rest/Average_true_range.json",
      "http_status": 200,
      "sha256": "a78a17ea4b5f154215fb2f785625fac2793911780a8d08fa71f6d6b05d73a8fc"
    }
  ],
  "investopedia": [
    {
      "url": "https://www.investopedia.com/terms/r/rsi.asp",
      "http_status": 200,
      "bytes": 835276
    },
    {
      "url": "https://www.investopedia.com/terms/a/atr.asp",
      "http_status": 200,
      "bytes": 826226
    }
  ],
  "huggingface": [
    {
      "dataset": "ibm-research/finqa",
      "splits": [
        "train",
        "validation",
        "test"
      ],
      "elapsed_s": 166.96,
      "ok": true
    },
    {
      "dataset": "hendrycks/competition_math",
      "ok": false,
      "error": "DatasetNotFoundError(\"Dataset 'hendrycks/competition_math' doesn't exist on the Hub or cannot be accessed.\")",
      "elapsed_s": 0.31
    },
    {
      "dataset": "AI-MO/NuminaMath-CoT",
      "splits": [
        "train",
        "test"
      ],
      "elapsed_s": 148.75,
      "ok": true
    }
  ]
}
```

## Transformation

- **sql:** Aggregates from `market_ticks` / optional `market_bars_5m`. No raw price sequences exported — only summary JSON in `input`. If price legs are NULL, scenarios flag ingestion gaps explicitly.
- **synthetic:** Deterministic adversarial finance traps (seeded).
- **finqa:** `ibm-research/finqa`; competition math via **`EleutherAI/hendrycks_math`** (`algebra` config — canonical Hub mirror when `hendrycks/competition_math` is unavailable); `AI-MO/NuminaMath-CoT` (streaming subset); Wikipedia REST summaries. Schema uses `source`: `finqa` for this bucket — HF dataset ids appear in `input`.
- **exchange_docs:** HTML under `sources/raw/exchange_docs/` from venue documentation URLs; QA from on-disk excerpts.

## Record counts

| source | count |
|--------|------:|
| `exchange_docs` | 50 |
| `finqa` | 450 |
| `sql` | 500 |
| `synthetic` | 500 |

## Samples

### source=sql
```json
{
  "instruction": "[sql-scenario-0] Given ONLY aggregate statistics from our warehouse (no raw candle strings exported), state whether mean-reversion assumptions are justified. Symbol lens: SOL-USD. Training record uses aggregated warehouse stats only.",
  "input": "MARKET_STATE_AGGREGATE_JSON:\n{\n  \"note\": \"primary_price comparators empty \\u2014 DATA ingestion issue; refuse price-level inference.\",\n  \"t_first\": \"2026-04-04T20:49:16+00:00\",\n  \"t_last\": \"2026-04-09T19:47:35+00:00\",\n  \"tick_count\": 8,\n  \"ticks_with_primary_price\": 0\n}\n\nNOT EXPORTED: raw tick sequence / full OHLCV history (policy: aggregates only).",
  "output": "Claim reviewed: Interpret regime from aggregates for SOL-USD.\nMath verdict: Volatility proxy from log returns is finite; sample size n_ticks=8.\nRisk/PnL verdict: Position sizing needs fresh VAR \u2014 aggregates insufficient alone.\nIndicator validity: RSI proxy may be unreliable when tick_count < 15; flag if needed.\nRegime considerations: regime_vol_bucket=None.\nFailure modes: Sparse ticks; missing comparator; stale inserted_at vs decision time.\nDATA evidence required: Re-query latest ticks and bars with explicit time window.\nFinal verifier status: needs proof unless live query confirms.",
  "source": "sql"
}
```

### source=synthetic
```json
{
  "instruction": "[adv-0] Challenge this quantitative claim (adversarial trap).",
  "input": "Claim bundle #0: Analyst claims annualized Sharpe 4.2 from 6 daily samples without subtracting risk-free rate.",
  "output": "Verdict: fail / needs proof.\nReasoning: Reject: insufficient sample; Sharpe definition mis-applied; needs full return series and rf curve.\nFailure modes: cherry-picked windows, fee omission, regime shift.\nDATA requirements: Download labeled fills and marks from venue API for full window.",
  "source": "synthetic"
}
```

### source=finqa
```json
{
  "instruction": "Solve the financial QA task using the provided table. Show reasoning steps; cite cells conceptually.",
  "input": "hf_dataset=ibm-research/finqa row_index=3125\nQuestion:\nwhat was the dividend increase between july 31 2014 and november 6 2014?\n\nTable:\n[['dividend amount', 'declaration date', 'record date', 'payment date'], ['$ 0.0425', 'february 12 2014', 'february 25 2014', 'march 10 2014'], ['$ 0.0425', 'may 8 2014', 'may 27 2014', 'june 10 2014'], ['$ 0.0425', 'july 31 2014', 'august 25 2014', 'september 10 2014'], ['$ 0.0675', 'november 6 2014', 'november 25 2014', 'december 10 2014']]",
  "output": "Reference answer (supervision target from dataset): 0.25\nTrainee must verify arithmetic against table cells; failure modes: wrong row lookup, unit mismatch.",
  "source": "finqa"
}
```

### source=exchange_docs
```json
{
  "instruction": "[exchange-docs-0] List failure modes when relying on default REST polling frequency.",
  "input": "local_doc_file=bybit_linear.html\nsha256_prompt=verify_on_disk\nexcerpt:\nGet Mark Price Kline | Bybit API Documentation Skip to main content V5 API P2P Trading Bybit Pay Tax API V3 Extras Pilot Features Changelog API Explorer FAQ Self Match Prevention How To Start Copy Trading DMM Listing English English \u4e2d\u6587\uff08\u53f0\u7063\uff09 Search Integration Guidance Bybit Platform Market Get Bybit Server Time Get Kline Get Mark Price Kline Get Index Price Kline Get Premium Index Price Kline Get Instruments Info Get Orderbook Get RPI Orderbook Get Tickers Get Funding Rate History Get Recent Public Trades Get Open Interest Get Historical Volatility Get Insurance Pool Get Risk Limit Get Delivery Price Get New Delivery Price Get Long Short Ratio Get Index Price Components Get Order Price Limit Get ADL Alert Get Fee Group Structure Trade Spot Margin Trade Position Account Asset User Spread Trading RFQ Trading Affiliate Crypto Loan Institutional Loan Broker Finance Bybit Card Web3 SBE Pre-upgrade WebSocket Stream Rate Limit Enums Definitions Error Codes Abandoned Endpoints Market Get Mark Price Kline On this page Get Mark Price Kline Query for historical mark price klines. Charts are returned in groups based on the requested interval. Covers: USDT contract / USDC contract / Inverse contract / Options HTTP Request \u200b GET /v5/market/mark-price-kline Copy Request Parameters \u200b Parameter Required Type Comments category false string Product type. linear , inverse , option When category is not passed, use linear by default symbol true string Symbol name, like BTCUSDT , uppercase only interval true string Kline interval. 1 , 3 , 5 , 15 , 30 , 60 , 120 , 240 , 360 , 720 , D , M , W start false integer The start timestamp (ms) end false integer The end timestamp (ms) limit false integer Limit for data size per page. futures: [ 1 , 1000 ] , option: [ 1 , 500 ] . Default: 200 Response Parameters \u200b Parameter Type Comments category string Product type symbol string Symbol name list array An string array of individual candle Sort in reverse by startTime &gt; list [0] : startTime string Start time of the candle (ms) &gt; list [1] : openPrice string Open price &gt; list [2] : highPrice string Highest price &gt; list [3] : lowPrice string Lowest price &gt; list [4] : closePrice string Close price. Is the last traded price when the candle is not closed RUN &gt;&gt; Request Example \u200b HTTP Python Go Java Node.js GET /v5/market/mark-price-kline?category=linear&amp;symbol=BTCUSDT&amp;interval=15&amp;start=1670601600000&amp;end=1670608800000&amp;limit=1 HTTP/1.1 Host : api-testnet.bybit.com from pybit . unified_trading import HTTP session = HTTP ( testnet = True ) print ( session . get_mark_price_kline ( category = &quot;linear&quot; , symbol = &quot;BTCUSDT&quot; , interval = 15 , start = 1670601600000 , end = 1670608800000 , limit = 1 , ) ) import ( &quot;context&quot; &quot;fmt&quot; bybit &quot;github.com/bybit-exchange/bybit.go.api&quot; ) client := bybit . NewBybitHttpClient ( &quot;&quot; , &quot;&quot; , bybit . WithBaseURL ( bybit . TESTNET ) ) params := map [ string ] interface { } { &quot;category&quot; : &quot;spot&quot; , &quot;symbol&quot; : &quot;BTCUSDT&quot; , &quot;interval&quot; : &quot;1&quot; } client . NewUtaBybitServiceWithParams ( params ) . GetMarkPriceKline ( context . Background ( ) ) import com . byb
```


## Gaps / follow-ups

- Investopedia often blocks automated fetch — use browser export if human-curated RSI/ATR copy required.
- Funding / open interest not in default `market_data.db` schema — add venue futures tables if needed.
- Expand exchange pulls beyond landing pages for liquidation/fee formulas.
- Deploy: copy `finquant/training/source_to_training.py` to `/data/finquant-1/training/` on the lab host; set `FINQUANT_BASE=/data/finquant-1`.

## Readiness

Sources are real (HF + REST + on-disk docs + DB telemetry). Suitable for QA review before training.
