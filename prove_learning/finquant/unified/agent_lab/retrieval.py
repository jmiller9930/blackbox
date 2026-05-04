"""
FinQuant Unified Agent Lab — Retrieval (RMv2 quality-gated).

Single entry: ``retrieve_eligible``.

1. **Governed memory** (optional): JSONL scan or ``learning_memory`` SQLite when enabled.
2. **Pattern memory** (optional): STM/LTM vector similarity in ``pattern_memory_v1`` — probabilistic
   neighborhood context layered on top of exact gates.

Companion DB: ``*.jsonl`` → ``*.db`` (see ``companion_memory_sqlite_path``).
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


def companion_memory_sqlite_path(shared_store_path: str | Path | None) -> Path | None:
    """
    Canonical pairing: ``records.jsonl`` → ``records.db``.
    Non-.jsonl paths have no companion DB (JSONL-only).
    """
    if not shared_store_path:
        return None
    p = Path(shared_store_path)
    if p.suffix.lower() != ".jsonl":
        return None
    return p.with_suffix(".db")


def _sqlite_learning_rowcount(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        return int(conn.execute("SELECT COUNT(*) FROM learning_memory").fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _merge_pattern_memory_vectors(
    eligible: list[dict[str, Any]],
    db_path: Path | None,
    case: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Append STM/LTM similarity hits as synthetic records (bounded)."""
    trace_out: list[dict[str, Any]] = []
    narrative = (case.get("context_narrative_v1") or "").strip()
    if not narrative or not config.get("memory_vector_enabled_v1"):
        return eligible, trace_out
    if db_path is None or not db_path.is_file():
        trace_out.append(_trace_entry(reason="pattern_memory_db_absent"))
        return eligible, trace_out

    from rmv2.embeddings import embed_for_memory
    from rmv2.memory_tiers import pattern_hits_to_synthetic_records, prune_expired_stm, search_similar_patterns

    prune_expired_stm(db_path)
    qvec, _backend = embed_for_memory(narrative[:12000], config)
    k_stm = int(config.get("memory_vector_k_stm_v1") or 2)
    k_ltm = int(config.get("memory_vector_k_ltm_v1") or 2)
    min_sim = float(config.get("memory_vector_min_sim_v1") or 0.22)
    hits, ht = search_similar_patterns(
        db_path,
        qvec,
        symbol=case.get("symbol", ""),
        case_regime=case.get("regime_v1"),
        k_stm=k_stm,
        k_ltm=k_ltm,
        min_similarity=min_sim,
    )
    trace_out.extend(ht)
    synth = pattern_hits_to_synthetic_records(hits)
    max_extra = int(config.get("memory_vector_max_extra_v1") or 4)
    synth = synth[:max_extra]
    trace_out.append(_trace_entry(reason="pattern_memory_merged", detail=f"synth_rows={len(synth)}"))
    return list(eligible) + synth, trace_out


def retrieve_eligible(
    shared_store_path: str | Path | None,
    case: dict[str, Any],
    config: dict[str, Any],
    max_records: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Return (eligible_records, retrieval_trace_entries).

    Governed retrieval runs when enabled; vector pattern memory merges when enabled
    (independent — can supply synthetic neighbors even if governed retrieval is off).
    """
    trace: list[dict[str, Any]] = []

    if not shared_store_path:
        trace.append(_trace_entry(reason="no_memory_store_path"))
        merged, vtr = _merge_pattern_memory_vectors([], None, case, config)
        trace.extend(vtr)
        return merged, trace

    eligible: list[dict[str, Any]] = []

    if config.get("retrieval_enabled_default_v1", False):
        db_path = companion_memory_sqlite_path(shared_store_path)
        if db_path is not None and _sqlite_learning_rowcount(db_path) > 0:
            from rmv2.memory_index import retrieve_eligible_sqlite

            eligible, trace = retrieve_eligible_sqlite(db_path, case, config, max_records)
        else:
            eligible, trace = _retrieve_eligible_jsonl(shared_store_path, case, config, max_records)
    else:
        trace.append(_trace_entry(reason="governed_retrieval_disabled"))

    db_path = companion_memory_sqlite_path(shared_store_path)
    extra_eligible, vtrace = _merge_pattern_memory_vectors(eligible, db_path, case, config)
    trace.extend(vtrace)
    return extra_eligible, trace


def _retrieve_eligible_jsonl(
    shared_store_path: str | Path | None,
    case: dict[str, Any],
    config: dict[str, Any],
    max_records: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cap = int(max_records if max_records is not None else config.get("retrieval_max_records_v1") or 5)
    if cap < 1:
        cap = 1

    min_obs = int(config.get("retrieval_min_obs_v1") or DEFAULT_MIN_OBS)
    min_win_rate = float(config.get("retrieval_min_win_rate_v1") or DEFAULT_MIN_WIN_RATE)

    store_path = Path(shared_store_path)
    if not store_path.exists():
        return [], [_trace_entry(reason="shared_store_not_found", path=str(store_path))]

    trace: list[dict] = []
    symbol = case.get("symbol", "")
    case_regime = case.get("regime_v1")

    lines: list[str] = []
    with open(store_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)

    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            trace.append(_trace_entry(reason="parse_error"))
            continue

        if not rec.get("retrieval_enabled_v1", False):
            trace.append(_trace_entry(reason="retrieval_disabled", record_id=rec.get("record_id")))
            continue

        if rec.get("symbol") != symbol:
            trace.append(_trace_entry(
                reason="symbol_mismatch",
                record_id=rec.get("record_id"),
                detail=f"wanted={symbol} got={rec.get('symbol')}",
            ))
            continue

        total_obs = int(rec.get("pattern_total_obs_v1") or 0)
        if total_obs < min_obs:
            trace.append(_trace_entry(
                reason="quality_insufficient_obs",
                record_id=rec.get("record_id"),
                detail=f"obs={total_obs} < required={min_obs}",
            ))
            continue

        win_rate = float(rec.get("pattern_win_rate_v1") or 0.0)
        if win_rate < min_win_rate:
            trace.append(_trace_entry(
                reason="quality_low_win_rate",
                record_id=rec.get("record_id"),
                detail=f"win_rate={win_rate:.3f} < required={min_win_rate:.3f}",
            ))
            continue

        status = str(rec.get("pattern_status_v1") or "candidate")
        allow_candidate = bool(config.get("retrieval_allow_candidate_v1", False))
        effective_disqualified = {"retired"} if allow_candidate else _DISQUALIFIED_STATUSES
        if status in effective_disqualified:
            trace.append(_trace_entry(
                reason="quality_disqualified_status",
                record_id=rec.get("record_id"),
                detail=f"status={status}",
            ))
            continue

        rec_regime = rec.get("regime_v1")
        if case_regime and rec_regime and case_regime != rec_regime:
            trace.append(_trace_entry(
                reason="regime_mismatch",
                record_id=rec.get("record_id"),
                detail=f"case_regime={case_regime} rec_regime={rec_regime}",
            ))
            continue

        candidates.append((i, win_rate, rec))

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
        trace.append(_trace_entry(
            reason="retrieved",
            record_id=rec.get("record_id"),
            detail=f"win_rate={wr:.3f} obs={rec.get('pattern_total_obs_v1')} status={rec.get('pattern_status_v1')}",
        ))

    return eligible, trace


def _trace_entry(
    reason: str,
    record_id: str | None = None,
    path: str | None = None,
    detail: str | None = None,
    memory_id: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"reason": reason}
    if record_id:
        entry["record_id"] = record_id
    if memory_id:
        entry["memory_id"] = memory_id
    if path:
        entry["path"] = path
    if detail:
        entry["detail"] = detail
    return entry
