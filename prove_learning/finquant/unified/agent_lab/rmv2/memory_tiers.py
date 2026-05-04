"""
RMv2 — short-term (STM) and long-term (LTM) pattern memory.

STM: recent narrative + embedding (probabilistic similarity; TTL expiry).
LTM: promoted STM rows or outcome-linked snapshots (longer horizon).

Stored in the companion SQLite DB (``pattern_memory_v1``). Retrieval merges
vector neighbors with governed learning records inside ``retrieval.retrieve_eligible``.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from rmv2.embeddings import blob_to_floats, floats_to_blob, embed_for_memory


def _utc_iso_hours_from_now(hours: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def prune_expired_stm(db_path: str | Path) -> int:
    from rmv2.memory_index import ensure_db

    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            DELETE FROM pattern_memory_v1
            WHERE tier = 'stm'
              AND expires_stm_at IS NOT NULL
              AND expires_stm_at < datetime('now')
            """
        )
        conn.commit()
        return int(cur.rowcount)
    finally:
        conn.close()


def count_pattern_memory_for_symbol(db_path: str | Path, symbol: str) -> int:
    """Rows in ``pattern_memory_v1`` for ``symbol`` (STM + LTM)."""
    path = Path(db_path)
    sym = (symbol or "").strip()
    if not path.is_file() or not sym:
        return 0
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM pattern_memory_v1 WHERE symbol = ?",
            (sym,),
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def insert_stm(
    db_path: str | Path,
    *,
    symbol: str,
    regime_v1: str,
    bar_timestamp: str | None,
    narrative_text: str,
    config: dict[str, Any],
    decision_action: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Append STM row; returns memory_id."""
    if not narrative_text.strip():
        return None
    from rmv2.memory_index import ensure_db

    ensure_db(db_path)
    vec, _backend = embed_for_memory(narrative_text[:12000], config)
    dim = len(vec)
    mid = f"pm_{uuid.uuid4().hex[:16]}"
    ttl_h = int(config.get("stm_ttl_hours_v1") or 72)
    expires = _utc_iso_hours_from_now(ttl_h)

    meta = dict(metadata or {})
    if decision_action:
        meta["decision_action_v1"] = decision_action

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO pattern_memory_v1 (
                memory_id, tier, symbol, regime_v1, bar_timestamp,
                narrative_text, embedding_dim, embedding_blob,
                outcome_hint, metadata_json, expires_stm_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mid,
                "stm",
                symbol,
                regime_v1,
                bar_timestamp,
                narrative_text[:12000],
                dim,
                floats_to_blob(vec),
                "pending",
                json.dumps(meta, default=str),
                expires,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return mid


def promote_stm_to_ltm(
    db_path: str | Path,
    memory_id: str,
    *,
    outcome_hint: str,
    linked_record_id: str | None = None,
) -> None:
    """STM → LTM after falsification or validation."""
    from rmv2.memory_index import ensure_db

    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            UPDATE pattern_memory_v1
            SET tier = 'ltm',
                outcome_hint = ?,
                expires_stm_at = NULL,
                linked_record_id = COALESCE(?, linked_record_id)
            WHERE memory_id = ?
            """,
            (outcome_hint, linked_record_id, memory_id),
        )
        conn.commit()
    finally:
        conn.close()


def insert_ltm_direct(
    db_path: str | Path,
    *,
    symbol: str,
    regime_v1: str,
    bar_timestamp: str | None,
    narrative_text: str,
    config: dict[str, Any],
    outcome_hint: str,
    linked_record_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Insert LTM without passing through STM (e.g. from promoted learning record)."""
    from rmv2.memory_index import ensure_db

    ensure_db(db_path)
    vec, _ = embed_for_memory(narrative_text[:12000], config)
    dim = len(vec)
    mid = f"pm_{uuid.uuid4().hex[:16]}"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO pattern_memory_v1 (
                memory_id, tier, symbol, regime_v1, bar_timestamp,
                narrative_text, embedding_dim, embedding_blob,
                outcome_hint, linked_record_id, metadata_json, expires_stm_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)
            """,
            (
                mid,
                "ltm",
                symbol,
                regime_v1,
                bar_timestamp,
                narrative_text[:12000],
                dim,
                floats_to_blob(vec),
                outcome_hint,
                linked_record_id,
                json.dumps(metadata or {}, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return mid


def search_similar_patterns(
    db_path: str | Path,
    query_vec: list[float],
    *,
    symbol: str,
    case_regime: str | None,
    k_stm: int,
    k_ltm: int,
    min_similarity: float,
    scan_cap: int = 1500,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (hits_sorted_by_similarity, trace_entries).

    Regime match adds a small bonus to similarity (probabilistic soft match).
    """
    trace: list[dict[str, Any]] = []
    path = Path(db_path)
    if not path.is_file():
        return [], [_trace("pattern_memory_db_missing", path=str(path))]

    qdim = len(query_vec)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT memory_id, tier, symbol, regime_v1, bar_timestamp, narrative_text,
                   embedding_dim, embedding_blob, outcome_hint, metadata_json, created_at
            FROM pattern_memory_v1
            WHERE symbol = ? AND embedding_dim = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (symbol, qdim, scan_cap),
        ).fetchall()
    finally:
        conn.close()

    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        blob = row["embedding_blob"]
        dim = int(row["embedding_dim"])
        try:
            vec = blob_to_floats(blob, dim)
        except Exception:
            trace.append(_trace("embedding_decode_skip", memory_id=row["memory_id"]))
            continue
        sim = cosine_similarity(query_vec, vec)
        reg = row["regime_v1"]
        if case_regime and reg and case_regime == reg:
            sim = min(1.0, sim + 0.08)
        if sim < min_similarity:
            continue
        scored.append(
            (
                sim,
                {
                    "memory_id": row["memory_id"],
                    "tier": row["tier"],
                    "symbol": row["symbol"],
                    "regime_v1": reg,
                    "bar_timestamp": row["bar_timestamp"],
                    "narrative_text": row["narrative_text"],
                    "outcome_hint": row["outcome_hint"],
                    "similarity_v1": round(sim, 5),
                    "metadata_json": row["metadata_json"],
                },
            )
        )

    scored.sort(key=lambda t: -t[0])
    stm_hits = [h for _, h in scored if h["tier"] == "stm"][: max(0, k_stm)]
    ltm_hits = [h for _, h in scored if h["tier"] == "ltm"][: max(0, k_ltm)]
    ordered = stm_hits + ltm_hits
    for h in ordered:
        trace.append(
            _trace(
                "pattern_memory_hit",
                memory_id=h["memory_id"],
                detail=f"tier={h['tier']} sim={h['similarity_v1']}",
            )
        )
    return ordered, trace


def pattern_hits_to_synthetic_records(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Shape vector hits like learning records for prompt formatting / P-4."""
    out: list[dict[str, Any]] = []
    for h in hits:
        tier = h.get("tier", "")
        sim = float(h.get("similarity_v1") or 0.0)
        lesson = (
            f"[{tier.upper()} pattern similarity={sim:.3f}] "
            f"{h.get('narrative_text', '')[:1800]}"
        )
        oh = h.get("outcome_hint") or ""
        if oh and oh != "pending":
            lesson += f" | outcome_hint={oh}"
        out.append(
            {
                "record_id": h.get("memory_id"),
                "symbol": h.get("symbol"),
                "regime_v1": h.get("regime_v1"),
                "lesson_v1": lesson,
                "entry_action_v1": "NO_TRADE",
                "retrieval_enabled_v1": True,
                "pattern_total_obs_v1": 0,
                "pattern_win_rate_v1": 0.5,
                "pattern_status_v1": "vector_probe_v1",
                "memory_source_v1": f"pattern_memory_{tier}",
                "pattern_similarity_v1": sim,
            }
        )
    return out


def _trace(reason: str, memory_id: str | None = None, path: str | None = None, detail: str | None = None) -> dict[str, Any]:
    e: dict[str, Any] = {"reason": reason}
    if memory_id:
        e["memory_id"] = memory_id
    if path:
        e["path"] = path
    if detail:
        e["detail"] = detail
    return e
