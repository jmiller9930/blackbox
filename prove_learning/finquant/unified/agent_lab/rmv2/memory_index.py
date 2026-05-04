"""
RMv2 — indexed learning memory (SQLite).

Part of the ``rmv2`` package (Reasoning Module v2). JSONL remains the audit spine;
this layer adds queryable rows for pattern retrieval and future RAG/embeddings.

Public API:
  - ensure_db(path)
  - upsert_learning_record(path, record)
  - ingest_jsonl(jsonl_path, db_path) -> row count
  - retrieve_eligible_sqlite(db_path, case, config, max_records)
  - insert_context_snapshot(...)  — optional decision-time context audit

Retrieval routing is solely ``retrieval.retrieve_eligible`` (JSONL + companion ``.db``).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_ENTRY_PRIO = {"ENTER_LONG": 0, "ENTER_SHORT": 1, "NO_TRADE": 2}
DEFAULT_MIN_OBS = 5
DEFAULT_MIN_WIN_RATE = 0.55
_DISQUALIFIED_STATUSES = {"candidate", "retired"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS learning_memory (
    record_id           TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    regime_v1           TEXT,
    retrieval_enabled   INTEGER NOT NULL DEFAULT 0,
    pattern_total_obs   INTEGER NOT NULL DEFAULT 0,
    pattern_win_rate    REAL NOT NULL DEFAULT 0,
    pattern_status      TEXT NOT NULL DEFAULT 'candidate',
    entry_action_v1     TEXT,
    lesson_excerpt      TEXT,
    record_json         TEXT NOT NULL,
    inserted_at         TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_lm_symbol_retrieval
    ON learning_memory(symbol, retrieval_enabled, pattern_win_rate DESC);

CREATE INDEX IF NOT EXISTS idx_lm_symbol_status
    ON learning_memory(symbol, pattern_status);

CREATE TABLE IF NOT EXISTS context_snapshots (
    snapshot_id         TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    bar_timestamp       TEXT,
    regime_v1           TEXT,
    snapshot_json       TEXT NOT NULL,
    prompt_hash_v1      TEXT,
    inserted_at         TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cs_symbol_ts ON context_snapshots(symbol, bar_timestamp);
"""


def ensure_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def upsert_learning_record(db_path: str | Path, record: dict[str, Any]) -> None:
    """Insert or replace one governed learning row (full JSON preserved)."""
    ensure_db(db_path)
    rid = str(record.get("record_id") or "")
    if not rid:
        return
    symbol = str(record.get("symbol") or "")
    regime = record.get("regime_v1")
    regime_s = str(regime) if regime is not None else None
    retr = 1 if record.get("retrieval_enabled_v1") else 0
    obs = int(record.get("pattern_total_obs_v1") or 0)
    wr = float(record.get("pattern_win_rate_v1") or 0.0)
    status = str(record.get("pattern_status_v1") or "candidate")
    entry = record.get("entry_action_v1")
    entry_s = str(entry) if entry is not None else None
    lesson = record.get("lesson_v1")
    if isinstance(lesson, str):
        excerpt = lesson[:2000]
    else:
        excerpt = json.dumps(lesson)[:2000] if lesson is not None else None
    blob = json.dumps(record, separators=(",", ":"), default=str)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO learning_memory (
                record_id, symbol, regime_v1, retrieval_enabled,
                pattern_total_obs, pattern_win_rate, pattern_status,
                entry_action_v1, lesson_excerpt, record_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(record_id) DO UPDATE SET
                symbol=excluded.symbol,
                regime_v1=excluded.regime_v1,
                retrieval_enabled=excluded.retrieval_enabled,
                pattern_total_obs=excluded.pattern_total_obs,
                pattern_win_rate=excluded.pattern_win_rate,
                pattern_status=excluded.pattern_status,
                entry_action_v1=excluded.entry_action_v1,
                lesson_excerpt=excluded.lesson_excerpt,
                record_json=excluded.record_json,
                inserted_at=datetime('now')
            """,
            (rid, symbol, regime_s, retr, obs, wr, status, entry_s, excerpt, blob),
        )
        conn.commit()
    finally:
        conn.close()


def ingest_jsonl(jsonl_path: str | Path, db_path: str | Path) -> int:
    """Backfill DB from an existing shared learning JSONL file."""
    jp = Path(jsonl_path)
    if not jp.is_file():
        return 0
    ensure_db(db_path)
    n = 0
    with open(jp, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            upsert_learning_record(db_path, rec)
            n += 1
    return n


def insert_context_snapshot(
    db_path: str | Path,
    *,
    snapshot_id: str,
    symbol: str,
    bar_timestamp: str | None,
    regime_v1: str | None,
    snapshot: dict[str, Any],
    prompt_hash_v1: str | None = None,
) -> None:
    """Optional audit trail: structured context packet per decision (for replay / training)."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO context_snapshots (
                snapshot_id, symbol, bar_timestamp, regime_v1, snapshot_json, prompt_hash_v1
            ) VALUES (?,?,?,?,?,?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                snapshot_json=excluded.snapshot_json,
                prompt_hash_v1=excluded.prompt_hash_v1,
                inserted_at=datetime('now')
            """,
            (
                snapshot_id,
                symbol,
                bar_timestamp,
                regime_v1,
                json.dumps(snapshot, separators=(",", ":"), default=str),
                prompt_hash_v1,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _trace_entry(
    reason: str,
    record_id: str | None = None,
    path: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"reason": reason}
    if record_id:
        entry["record_id"] = record_id
    if path:
        entry["path"] = path
    if detail:
        entry["detail"] = detail
    return entry


def retrieve_eligible_sqlite(
    db_path: str | Path,
    case: dict[str, Any],
    config: dict[str, Any],
    max_records: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Same semantics as retrieval.retrieve_eligible for JSONL — SQL prefilter + Python gates
    for regime and status edge cases.
    """
    cap = int(max_records if max_records is not None else config.get("retrieval_max_records_v1") or 5)
    if cap < 1:
        cap = 1

    path = Path(db_path)
    if not path.is_file():
        return [], [_trace_entry(reason="sqlite_store_not_found", path=str(path))]

    min_obs = int(config.get("retrieval_min_obs_v1") or DEFAULT_MIN_OBS)
    min_win_rate = float(config.get("retrieval_min_win_rate_v1") or DEFAULT_MIN_WIN_RATE)
    allow_candidate = bool(config.get("retrieval_allow_candidate_v1", False))
    effective_bad = {"retired"} if allow_candidate else _DISQUALIFIED_STATUSES

    symbol = case.get("symbol", "")
    case_regime = case.get("regime_v1")

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    trace: list[dict[str, Any]] = []
    try:
        cur = conn.execute(
            """
            SELECT record_json, inserted_at, rowid
            FROM learning_memory
            WHERE symbol = ?
              AND retrieval_enabled = 1
              AND pattern_total_obs >= ?
              AND pattern_win_rate >= ?
            ORDER BY rowid DESC
            LIMIT 5000
            """,
            (symbol, min_obs, min_win_rate),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for row in rows:
        try:
            rec = json.loads(row["record_json"])
        except json.JSONDecodeError:
            trace.append(_trace_entry(reason="parse_error"))
            continue

        status = str(rec.get("pattern_status_v1") or "candidate")
        if status in effective_bad:
            trace.append(
                _trace_entry(
                    reason="quality_disqualified_status",
                    record_id=rec.get("record_id"),
                    detail=f"status={status}",
                )
            )
            continue

        rec_regime = rec.get("regime_v1")
        if case_regime and rec_regime and case_regime != rec_regime:
            trace.append(
                _trace_entry(
                    reason="regime_mismatch",
                    record_id=rec.get("record_id"),
                    detail=f"case_regime={case_regime} rec_regime={rec_regime}",
                )
            )
            continue

        win_rate = float(rec.get("pattern_win_rate_v1") or 0.0)
        rid = row["rowid"]
        candidates.append((int(rid), win_rate, rec))

    candidates.sort(
        key=lambda t: (
            _ENTRY_PRIO.get(str(t[2].get("entry_action_v1") or ""), 9),
            -t[1],
            -t[0],
        )
    )
    picked = candidates[:cap]
    picked.sort(key=lambda t: t[0])

    eligible = [t[2] for t in picked]
    for _, wr, rec in picked:
        trace.append(
            _trace_entry(
                reason="retrieved_sqlite",
                record_id=rec.get("record_id"),
                detail=f"win_rate={wr:.3f} obs={rec.get('pattern_total_obs_v1')} status={rec.get('pattern_status_v1')}",
            )
        )

    return eligible, trace
