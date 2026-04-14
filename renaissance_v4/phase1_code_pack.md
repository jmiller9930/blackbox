# RenaissanceV4 — Phase 1 Code Pack
**System:** BlackBox  
**Authority:** Architect  
**Purpose:** Phase 1 implementation document for the RenaissanceV4 research foundation  
**Scope:** Binance historical data ingestion, SQLite storage, validation, and deterministic replay  
**Status:** Build now

---

# 1. Objective

Phase 1 builds the minimum real foundation for RenaissanceV4.

This phase does **not** build a full trading system yet.

It builds the research base required for everything that comes after:

- pull Binance historical 5m candles
- store them locally
- validate the dataset
- replay bars one at a time
- create the canonical decision path shell

If this phase is weak, all later work is fake.

---

# 2. What Phase 1 Includes

Phase 1 includes only:

1. project folder structure  
2. SQLite database helper  
3. schema creation  
4. Binance historical ingest  
5. bar validator  
6. deterministic replay runner  
7. canonical decision contract  

Phase 1 does **not** include:

- live trading
- signal tuning
- multi-exchange data
- advanced routing
- position sizing logic
- production execution

---

# 3. Folder Structure

```text
renaissance_v4/
├── core/
│   └── decision_contract.py
├── data/
│   ├── binance_ingest.py
│   ├── bar_validator.py
│   ├── init_db.py
│   └── schema.sql
├── research/
│   └── replay_runner.py
└── utils/
    └── db.py
```

---

# 4. Build Order

Build in this exact order:

1. `utils/db.py`
2. `data/schema.sql`
3. `data/init_db.py`
4. `core/decision_contract.py`
5. `data/binance_ingest.py`
6. `data/bar_validator.py`
7. `research/replay_runner.py`

Do not skip around.

---

# 5. CAT Blocks

## 5.1 Create `renaissance_v4/utils/db.py`

```bash
cat > renaissance_v4/utils/db.py << 'EOF'
"""
db.py

Purpose:
Provide SQLite connection helpers for RenaissanceV4.

Usage:
Imported by database setup, ingestion, validation, and replay modules.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("renaissance_v4/data/renaissance_v4.sqlite3")


def get_connection() -> sqlite3.Connection:
    """
    Open a SQLite connection to the RenaissanceV4 database.
    Prints the resolved path so the operator can verify the exact file in use.
    """
    print(f"[db] Opening database at: {DB_PATH.resolve()}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection
EOF
```

---

## 5.2 Create `renaissance_v4/data/schema.sql`

```bash
cat > renaissance_v4/data/schema.sql << 'EOF'
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
EOF
```

---

## 5.3 Create `renaissance_v4/data/init_db.py`

```bash
cat > renaissance_v4/data/init_db.py << 'EOF'
"""
init_db.py

Purpose:
Initialize the RenaissanceV4 SQLite database using the schema.sql file.

Usage:
Run directly to create all required Phase 1 tables.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

from pathlib import Path

from renaissance_v4.utils.db import get_connection

SCHEMA_PATH = Path("renaissance_v4/data/schema.sql")


def main() -> None:
    """
    Load the SQL schema from disk and apply it to the SQLite database.
    Prints each major action to the screen for visible validation.
    """
    print(f"[init_db] Using schema file: {SCHEMA_PATH.resolve()}")

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"[init_db] Schema file not found: {SCHEMA_PATH}")

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection = get_connection()

    print("[init_db] Applying schema to database")
    connection.executescript(schema_sql)
    connection.commit()
    print("[init_db] Database initialization complete")


if __name__ == "__main__":
    main()
EOF
```

---

## 5.4 Create `renaissance_v4/core/decision_contract.py`

```bash
cat > renaissance_v4/core/decision_contract.py << 'EOF'
"""
decision_contract.py

Purpose:
Define the canonical Phase 1 decision contract for RenaissanceV4.

Usage:
Used by replay and later live evaluation code to keep one consistent output structure.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DecisionContract:
    """
    Canonical decision object for one evaluation cycle.
    This starts simple in Phase 1 and will expand in later phases.
    """
    decision_id: str
    symbol: str
    timestamp: int
    market_regime: str
    direction: str
    fusion_score: float
    confidence_score: float
    edge_score: float
    risk_budget: float
    execution_allowed: bool
    reason_trace: dict[str, Any] = field(default_factory=dict)
EOF
```

---

## 5.5 Create `renaissance_v4/data/binance_ingest.py`

```bash
cat > renaissance_v4/data/binance_ingest.py << 'EOF'
"""
binance_ingest.py

Purpose:
Download historical Binance 5-minute klines and store them in SQLite.

Usage:
Run directly to backfill approximately two years of SOLUSDT 5m data.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from renaissance_v4.utils.db import get_connection

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "SOLUSDT"
INTERVAL = "5m"
LIMIT = 1000
FIVE_MINUTES_MS = 5 * 60 * 1000


def fetch_klines(symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> list[list]:
    """
    Fetch one batch of klines from Binance.
    Prints the request URL and response size for debugging.
    """
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time_ms,
        "endTime": end_time_ms,
        "limit": LIMIT,
    }
    url = f"{BINANCE_KLINES_URL}?{urlencode(params)}"
    print(f"[ingest] Requesting: {url}")

    with urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    print(f"[ingest] Received {len(payload)} bars")
    return payload


def insert_klines(connection: sqlite3.Connection, symbol: str, klines: list[list]) -> None:
    """
    Insert bars into SQLite using INSERT OR IGNORE so reruns stay safe.
    """
    print(f"[ingest] Inserting {len(klines)} rows into market_bars_5m")
    connection.executemany(
        """
        INSERT OR IGNORE INTO market_bars_5m (
            symbol, open_time, open, high, low, close, volume, close_time,
            quote_volume, trade_count, taker_base_volume, taker_quote_volume
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                symbol,
                row[0],
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
                row[6],
                float(row[7]),
                int(row[8]),
                float(row[9]),
                float(row[10]),
            )
            for row in klines
        ],
    )
    connection.commit()
    print("[ingest] Commit complete")


def main() -> None:
    """
    Backfill approximately two years of 5-minute SOLUSDT bars from Binance.
    This routine advances forward in time one batch at a time and prints progress.
    """
    connection = get_connection()

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=730)
    cursor_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    print(f"[ingest] Starting ingest for {SYMBOL}")
    print(f"[ingest] From: {start.isoformat()}")
    print(f"[ingest] To:   {now.isoformat()}")

    while cursor_ms < end_ms:
        batch = fetch_klines(SYMBOL, INTERVAL, cursor_ms, end_ms)

        if not batch:
            print("[ingest] No more bars returned; stopping")
            break

        insert_klines(connection, SYMBOL, batch)

        last_open_time = int(batch[-1][0])
        next_cursor_ms = last_open_time + FIVE_MINUTES_MS

        if next_cursor_ms <= cursor_ms:
            raise RuntimeError("[ingest] Cursor failed to advance; aborting")

        cursor_ms = next_cursor_ms
        print(f"[ingest] Advanced cursor to: {cursor_ms}")
        time.sleep(0.25)

    print("[ingest] Historical ingest completed successfully")


if __name__ == "__main__":
    main()
EOF
```

---

## 5.6 Create `renaissance_v4/data/bar_validator.py`

```bash
cat > renaissance_v4/data/bar_validator.py << 'EOF'
"""
bar_validator.py

Purpose:
Validate that historical Binance 5-minute bars in SQLite are evenly spaced and ordered.

Usage:
Run after ingestion to catch missing bars or timestamp problems before replay work begins.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

from renaissance_v4.utils.db import get_connection

SYMBOL = "SOLUSDT"
EXPECTED_SPACING_MS = 5 * 60 * 1000


def main() -> None:
    """
    Verify that each adjacent bar is exactly 5 minutes apart.
    Prints any gap to the screen and fails loudly if issues are found.
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT open_time
        FROM market_bars_5m
        WHERE symbol = ?
        ORDER BY open_time ASC
        """,
        (SYMBOL,),
    ).fetchall()

    print(f"[validator] Loaded {len(rows)} bars for {SYMBOL}")

    if not rows:
        raise RuntimeError("[validator] No bars found to validate")

    issues = 0

    for index in range(1, len(rows)):
        previous_open = rows[index - 1]["open_time"]
        current_open = rows[index]["open_time"]
        delta = current_open - previous_open

        if delta != EXPECTED_SPACING_MS:
            issues += 1
            print(
                "[validator] Spacing issue detected: "
                f"index={index} previous_open={previous_open} current_open={current_open} delta={delta}"
            )

    if issues:
        raise RuntimeError(f"[validator] Validation failed with {issues} spacing issues")

    print("[validator] Validation passed with no spacing issues")


if __name__ == "__main__":
    main()
EOF
```

---

## 5.7 Create `renaissance_v4/research/replay_runner.py`

```bash
cat > renaissance_v4/research/replay_runner.py << 'EOF'
"""
replay_runner.py

Purpose:
Run a deterministic bar-by-bar replay over historical 5-minute bars.

Usage:
Run directly after database initialization and validation to confirm replay can process the dataset.

Version:
v1.0

Change History:
- v1.0 Initial Phase 1 implementation.
"""

from __future__ import annotations

import uuid

from renaissance_v4.core.decision_contract import DecisionContract
from renaissance_v4.utils.db import get_connection


def main() -> None:
    """
    Iterate through historical bars in strict chronological order.
    For Phase 1, generate a placeholder no-trade decision object per bar to prove the replay path works.
    """
    connection = get_connection()
    rows = connection.execute(
        """
        SELECT symbol, open_time, open, high, low, close, volume
        FROM market_bars_5m
        ORDER BY open_time ASC
        """
    ).fetchall()

    print(f"[replay] Loaded {len(rows)} bars")

    if not rows:
        raise RuntimeError("[replay] No historical bars found")

    for index, row in enumerate(rows, start=1):
        decision = DecisionContract(
            decision_id=str(uuid.uuid4()),
            symbol=row["symbol"],
            timestamp=row["open_time"],
            market_regime="unknown",
            direction="no_trade",
            fusion_score=0.0,
            confidence_score=0.0,
            edge_score=0.0,
            risk_budget=0.0,
            execution_allowed=False,
            reason_trace={
                "phase": "phase_1_foundation",
                "note": "Replay pipeline shell only; no signal logic yet",
                "close": row["close"],
                "volume": row["volume"],
            },
        )

        if index % 5000 == 0:
            print(
                "[replay] Progress: "
                f"processed={index} symbol={decision.symbol} "
                f"timestamp={decision.timestamp} direction={decision.direction}"
            )

    print("[replay] Replay completed successfully")


if __name__ == "__main__":
    main()
EOF
```

---

# 6. Run Sequence

Run these commands in order:

```bash
python3 renaissance_v4/data/init_db.py
python3 renaissance_v4/data/binance_ingest.py
python3 renaissance_v4/data/bar_validator.py
python3 renaissance_v4/research/replay_runner.py
```

---

# 7. Expected Proof

Phase 1 is complete only when:

- database file is created  
- schema loads successfully  
- Binance bars are ingested  
- validator reports no spacing issues  
- replay runner processes the entire dataset without failure  

---

# 8. What Comes After Phase 1

Only after this passes do we move to:

- MarketState builder
- Feature engine
- Regime classifier
- Signal base class
- first real signal modules

That will be Phase 2.

---

# 9. Final Statement

Phase 1 is the point where RenaissanceV4 stops being a concept and starts being an actual machine.

If this phase is clean, later phases can be trusted.

If this phase is sloppy, everything built on top of it will lie.
