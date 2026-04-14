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

CREATE TABLE IF NOT EXISTS trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT NOT NULL UNIQUE,
    decision_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_time INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_time INTEGER,
    exit_price REAL,
    stop_price REAL NOT NULL,
    target_price REAL NOT NULL,
    pnl_usd REAL,
    mae REAL,
    mfe REAL,
    friction_cost REAL,
    exit_reason TEXT
);

CREATE TABLE IF NOT EXISTS signal_scorecard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_name TEXT NOT NULL UNIQUE,
    lifecycle_state TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    win_rate REAL NOT NULL,
    expectancy REAL NOT NULL,
    avg_mae REAL NOT NULL,
    avg_mfe REAL NOT NULL,
    degradation_ratio REAL NOT NULL,
    updated_at TEXT NOT NULL
);
