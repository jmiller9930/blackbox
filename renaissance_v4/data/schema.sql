CREATE TABLE IF NOT EXISTS market_bars_5m (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER NOT NULL,
    quote_volume REAL,
    trade_count INTEGER,
    taker_base_volume REAL,
    taker_quote_volume REAL,
    UNIQUE(symbol, open_time)
);

CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    bar_time INTEGER NOT NULL,
    regime TEXT NOT NULL,
    direction TEXT NOT NULL,
    fusion_score REAL NOT NULL,
    confidence_score REAL NOT NULL,
    edge_score REAL NOT NULL,
    risk_budget REAL NOT NULL,
    execution_allowed INTEGER NOT NULL,
    reason_trace_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_bars_5m_symbol_open_time
ON market_bars_5m(symbol, open_time);
