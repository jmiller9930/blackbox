"""
Directive 09 — Operator **execution seam**: after a parallel batch, run Student packet → shadow output
→ reveal → append ``student_learning_record_v1`` for each closed trade.

* Does not import replay_runner.
* Soft-fail: per-trade errors are collected; batch Referee results remain authoritative.
* Disable with env ``PATTERN_GAME_STUDENT_LOOP_SEAM=0`` (operations kill-switch; no UI toggle required).
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from renaissance_v4.core.outcome_record import OutcomeRecord, outcome_record_from_jsonable
from renaissance_v4.game_theory.student_proctor.reveal_layer_v1 import (
    build_reveal_v1_from_outcome_and_student,
)
from renaissance_v4.game_theory.student_proctor.shadow_student_v1 import (
    emit_shadow_stub_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.cross_run_retrieval_v1 import (
    build_student_decision_packet_v1_with_cross_run_retrieval,
)
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    append_student_learning_record_v1,
    build_student_learning_record_v1_from_reveal,
    default_student_learning_store_path_v1,
)
from renaissance_v4.utils.db import DB_PATH

_NS_RECORD = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _env_seam_enabled() -> bool:
    v = (os.environ.get("PATTERN_GAME_STUDENT_LOOP_SEAM") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _signature_key_for_trade(o: OutcomeRecord) -> str:
    """v1 match key: symbol + entry bar time (retrieval groups similar entry context)."""
    return f"student_entry_v1:{o.symbol}:{o.entry_time}"


def _record_id_for_trade(*, run_id: str, scenario_id: str, trade_id: str) -> str:
    return str(uuid.uuid5(_NS_RECORD, f"{run_id}:{scenario_id}:{trade_id}"))


def _student_output_fingerprint_v1(so: dict[str, Any]) -> str:
    canonical = json.dumps(so, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def student_loop_seam_after_parallel_batch_v1(
    *,
    results: list[dict[str, Any]],
    run_id: str,
    db_path: Path | str | None = None,
    store_path: Path | str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """
    For each successful scenario row with ``replay_outcomes_json``, process each trade.

    Returns an audit dict suitable for merging into API ``result`` payloads (Directive 11 fields).
    """
    if not _env_seam_enabled():
        return {
            "schema": "student_loop_seam_audit_v1",
            "skipped": True,
            "reason": "PATTERN_GAME_STUDENT_LOOP_SEAM disabled",
            "student_learning_rows_appended": 0,
            "student_retrieval_matches": 0,
            "student_output_fingerprint": None,
            "shadow_student_enabled": False,
        }

    db = Path(str(db_path)) if db_path else DB_PATH
    store = Path(str(store_path)) if store_path else default_student_learning_store_path_v1()

    errors: list[str] = []
    appended = 0
    trades_seen = 0
    retrieval_matches_total = 0
    primary_trade_shadow_student_v1: dict[str, Any] | None = None
    primary_student_output_v1: dict[str, Any] | None = None

    for row in results:
        if not row.get("ok"):
            continue
        sid = str(row.get("scenario_id") or "unknown")
        raw_list = row.get("replay_outcomes_json")
        if not isinstance(raw_list, list) or not raw_list:
            continue
        for raw in raw_list:
            if not isinstance(raw, dict):
                errors.append(f"{sid}: non-dict outcome")
                continue
            try:
                o = outcome_record_from_jsonable(raw)
            except (TypeError, ValueError) as e:
                errors.append(f"{sid}: outcome_from_json {e!r}")
                continue
            trades_seen += 1
            sk = _signature_key_for_trade(o)
            ctx_sig = {"schema": "context_signature_v1", "signature_key": sk}
            try:
                pkt, perr = build_student_decision_packet_v1_with_cross_run_retrieval(
                    db_path=db,
                    symbol=o.symbol,
                    decision_open_time_ms=int(o.entry_time),
                    store_path=store,
                    retrieval_signature_key=sk,
                )
                if perr or pkt is None:
                    errors.append(f"{sid} trade={o.trade_id}: packet {perr!r}")
                    continue
                rx = pkt.get(FIELD_RETRIEVED_STUDENT_EXPERIENCE_V1)
                n_rx = len(rx) if isinstance(rx, list) else 0
                retrieval_matches_total += n_rx
                so, soe = emit_shadow_stub_student_output_v1(
                    pkt,
                    graded_unit_id=o.trade_id,
                    decision_at_ms=int(o.entry_time),
                )
                if soe or so is None:
                    errors.append(f"{sid} trade={o.trade_id}: student_output {'; '.join(soe)}")
                    continue
                if primary_trade_shadow_student_v1 is None and isinstance(so, dict):
                    primary_student_output_v1 = so
                    pr_ids = so.get("pattern_recipe_ids")
                    primary_trade_shadow_student_v1 = {
                        "scenario_id": sid,
                        "trade_id": o.trade_id,
                        "signature_key_used": sk,
                        "retrieval_slice_count": n_rx,
                        "student_decision_ref": so.get("student_decision_ref"),
                        "pattern_recipe_ids": list(pr_ids) if isinstance(pr_ids, list) else pr_ids,
                        "confidence_01": so.get("confidence_01"),
                    }
                rev, re = build_reveal_v1_from_outcome_and_student(
                    student_output=so,
                    outcome=o,
                )
                if re or rev is None:
                    errors.append(f"{sid} trade={o.trade_id}: reveal {'; '.join(re)}")
                    continue
                rid = _record_id_for_trade(run_id=run_id, scenario_id=sid, trade_id=o.trade_id)
                lr, lre = build_student_learning_record_v1_from_reveal(
                    rev,
                    run_id=run_id,
                    record_id=rid,
                    context_signature_v1=ctx_sig,
                    strategy_id=strategy_id,
                )
                if lre or lr is None:
                    errors.append(f"{sid} trade={o.trade_id}: learning_row {'; '.join(lre)}")
                    continue
                try:
                    append_student_learning_record_v1(store, lr)
                    appended += 1
                except ValueError as ve:
                    if "record_id already present" in str(ve):
                        errors.append(
                            f"{sid} trade={o.trade_id}: skip duplicate record_id "
                            f"(replay or prior append): {rid}"
                        )
                    else:
                        raise
            except ValueError as ve:
                errors.append(f"{sid} trade={o.trade_id}: {ve!r}")
            except OSError as oe:
                errors.append(f"{sid} trade={o.trade_id}: {type(oe).__name__}: {oe}")

    out_fp: str | None = None
    if primary_student_output_v1 is not None:
        out_fp = _student_output_fingerprint_v1(primary_student_output_v1)

    return {
        "schema": "student_loop_seam_audit_v1",
        "run_id": run_id,
        "student_learning_store_path": str(store.resolve()),
        "database_path_used": str(db.resolve()),
        "trades_considered": trades_seen,
        "student_learning_rows_appended": appended,
        "student_retrieval_matches": retrieval_matches_total,
        "student_output_fingerprint": out_fp,
        "shadow_student_enabled": True,
        "primary_trade_shadow_student_v1": primary_trade_shadow_student_v1,
        "errors": errors,
        "soft_fail": bool(errors and appended == 0 and trades_seen > 0),
    }


__all__ = [
    "student_loop_seam_after_parallel_batch_v1",
]
