"""Append-only outcome_manifest.jsonl + duplicate_audit.jsonl + versioned sequential_state.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.anna_training.execution_ledger import connect_ledger, default_execution_ledger_path, ensure_execution_ledger_schema
from modules.anna_training.store import utc_now_iso

from .canonical_json import sha256_hex
from .io_paths import duplicate_audit_path, outcome_manifest_path, sequential_state_path
from .sequential_errors import CorruptionError

STATE_SCHEMA_VERSION = "sequential_state_v1"
DUPLICATE_AUDIT_SCHEMA = "duplicate_audit_v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CorruptionError(f"invalid JSON state file {path}: {e}") from e


def _atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _hash_for_duplicate_detection(record: dict[str, Any]) -> str:
    """Hash semantic fields (exclude append-only metadata that differs per line)."""
    core = {
        "market_event_id": record.get("market_event_id"),
        "test_id": record.get("test_id"),
        "outcome": record.get("outcome"),
        "pairing_valid": record.get("pairing_valid"),
        "exclusion_reason": record.get("exclusion_reason"),
        "pnl_candidate": record.get("pnl_candidate"),
        "pnl_baseline": record.get("pnl_baseline"),
        "mae_candidate": record.get("mae_candidate"),
        "mae_baseline": record.get("mae_baseline"),
        "mae_protocol_id": record.get("mae_protocol_id"),
        "candidate_passes_risk": record.get("candidate_passes_risk"),
        "payload_fingerprint": record.get("payload_fingerprint"),
    }
    return sha256_hex(core)


def load_state(test_id: str, *, artifacts_dir: Path | None = None) -> dict[str, Any]:
    p = sequential_state_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "sequential_state.json"
    raw = _read_json(p)
    if not raw:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "test_id": test_id,
            "event_content_hashes": {},
        }
    if raw.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CorruptionError(f"unsupported sequential_state schema: {raw.get('schema_version')}")
    if raw.get("test_id") != test_id:
        raise CorruptionError("state test_id mismatch")
    raw.setdefault("event_content_hashes", {})
    return raw


def append_outcome_record(
    record: dict[str, Any],
    *,
    test_id: str,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Append one outcome to outcome_manifest.jsonl unless duplicate.

    Duplicate same market_event_id + same content hash → idempotent no-op + duplicate_audit line.
    Same market_event_id + different hash → CorruptionError.

    Returns { "status": "appended" | "duplicate_noop", "market_event_id", "line_hash"? }
    """
    mid = (record.get("market_event_id") or "").strip()
    if not mid:
        raise ValueError("market_event_id required")

    record = dict(record)
    record.setdefault("test_id", test_id)
    record.setdefault("recorded_at_utc", utc_now_iso())
    content_hash = _hash_for_duplicate_detection(record)
    record["content_hash"] = content_hash

    manifest = outcome_manifest_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "outcome_manifest.jsonl"
    audit = duplicate_audit_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "duplicate_audit.jsonl"
    state_path = sequential_state_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "sequential_state.json"

    state = load_state(test_id, artifacts_dir=artifacts_dir)
    hashes: dict[str, str] = state["event_content_hashes"]

    prev = hashes.get(mid)
    if prev is not None:
        if prev == content_hash:
            audit_line = {
                "schema": DUPLICATE_AUDIT_SCHEMA,
                "test_id": test_id,
                "market_event_id": mid,
                "content_hash": content_hash,
                "skipped_at_utc": utc_now_iso(),
                "reason": "idempotent_duplicate",
            }
            audit.parent.mkdir(parents=True, exist_ok=True)
            with audit.open("a", encoding="utf-8") as f:
                f.write(json.dumps(audit_line, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
            return {"status": "duplicate_noop", "market_event_id": mid, "content_hash": content_hash}
        raise CorruptionError(
            f"market_event_id {mid!r} already recorded with different content hash "
            f"(existing={prev[:16]}… new={content_hash[:16]}…)"
        )

    manifest.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    with manifest.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    hashes[mid] = content_hash
    state["event_content_hashes"] = dict(sorted(hashes.items()))
    _atomic_write_json(state_path, state)

    return {"status": "appended", "market_event_id": mid, "content_hash": content_hash}


def rebuild_state_hashes_from_manifest(
    test_id: str,
    *,
    artifacts_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Rebuild event_content_hashes from outcome_manifest.jsonl (recovery).

    Fails with CorruptionError if duplicate market_event_id lines disagree.
    """
    manifest = outcome_manifest_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "outcome_manifest.jsonl"
    if not manifest.is_file():
        return {"rebuilt": 0, "hashes": {}}

    seen: dict[str, str] = {}
    with manifest.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            mid = (rec.get("market_event_id") or "").strip()
            ch = rec.get("content_hash")
            if not mid or not ch:
                raise CorruptionError(f"manifest line {line_no}: missing market_event_id or content_hash")
            if mid in seen and seen[mid] != ch:
                raise CorruptionError(f"manifest line {line_no}: conflicting content_hash for {mid!r}")
            seen[mid] = ch

    state_path = sequential_state_path(test_id) if artifacts_dir is None else artifacts_dir / test_id / "sequential_state.json"
    state = load_state(test_id, artifacts_dir=artifacts_dir)
    state["event_content_hashes"] = dict(sorted(seen.items()))
    _atomic_write_json(state_path, state)
    return {"rebuilt": len(seen), "hashes": seen}


def trade_row_hash(trade_id: str, *, db_path: Path | None = None) -> str | None:
    """Stable hash of ledger row for audit (read-only)."""
    if not trade_id:
        return None
    conn = connect_ledger(db_path or default_execution_ledger_path())
    try:
        ensure_execution_ledger_schema(conn)
        cur = conn.execute(
            """
            SELECT trade_id, strategy_id, lane, mode, market_event_id, symbol, timeframe,
                   side, entry_time, entry_price, size, exit_time, exit_price, exit_reason,
                   pnl_usd, context_snapshot_json, notes, created_at_utc
            FROM execution_trades WHERE trade_id = ?
            """,
            (trade_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        d = dict(zip(cols, row))
        return sha256_hex(d)
    finally:
        conn.close()
