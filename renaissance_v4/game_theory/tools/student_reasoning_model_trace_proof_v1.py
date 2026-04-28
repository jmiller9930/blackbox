#!/usr/bin/env python3
"""
Hard validation: one Student ``job_id`` must show a **complete per-trade** reasoning trace.

Reads ``learning_trace_events_v1.jsonl`` (default: ``renaissance_v4/game_theory/learning_trace_events_v1.jsonl``
or ``PATTERN_GAME_MEMORY_ROOT`` / ``path`` override).

Exit **0** only if:

* every ``student_output_sealed`` trade has the required stages **with the same** ``scenario_id`` + ``trade_id``;
* count of ``student_decision_authority_v1`` events equals count of sealed trades;
* each authority payload includes ``referee_safety_check_v1`` and (when mandate) ``decision_source_v1``;
* each ``student_output_sealed`` evidence includes ``decision_source_v1`` = ``reasoning_model``.

Usage::

    python3 -m renaissance_v4.game_theory.tools.student_reasoning_model_trace_proof_v1 <job_id> [path_to_jsonl]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.learning_trace_events_v1 import read_learning_trace_events_for_job_v1
from renaissance_v4.game_theory.memory_paths import default_learning_trace_events_jsonl
from renaissance_v4.game_theory.student_proctor.student_decision_authority_v1 import (
    DECISION_SOURCE_REASONING_MODEL_V1,
)

REQUIRED_STAGES_V1 = frozenset(
    {
        "candle_timeframe_nexus_v1",  # student_packet nexus — context path into seam
        "memory_retrieval_completed",
        "market_data_loaded",
        "indicator_context_eval_v1",
        "perps_state_model_evaluated_v1",
        "memory_context_evaluated",
        "prior_outcomes_evaluated",
        "risk_reward_evaluated",
        "decision_synthesis_v1",
        "entry_reasoning_validated",
        "entry_reasoning_sealed_v1",
        "reasoning_router_decision_v1",
        "reasoning_cost_governor_v1",
        "student_decision_authority_v1",
        "student_output_sealed",
    }
)


def _key(scenario_id: str | None, trade_id: str | None) -> str | None:
    s = str(scenario_id or "").strip()
    t = str(trade_id or "").strip()
    if not s or not t:
        return None
    return f"{s}\t{t}"


def validate_student_reasoning_model_trace_for_job_v1(
    job_id: str,
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    jid = str(job_id or "").strip()
    evs = read_learning_trace_events_for_job_v1(jid, path=path)
    by_key: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    sealed_keys: list[str] = []
    for ev in evs:
        st = str(ev.get("stage") or "")
        k = _key(ev.get("scenario_id"), ev.get("trade_id"))
        if k is None:
            continue
        by_key[k][st].append(ev)
        if st == "student_output_sealed":
            sealed_keys.append(k)
    sealed_set = sorted(set(sealed_keys))
    errors: list[str] = []
    if not sealed_set:
        errors.append("no student_output_sealed events with scenario_id+trade_id for this job_id")
    auth_n = sum(len(by_key[k].get("student_decision_authority_v1", [])) for k in sealed_set)
    if len(sealed_set) != auth_n:
        errors.append(
            f"authority_event_count_mismatch_v1: sealed_trades={len(sealed_set)} authority_events={auth_n}"
        )
    examples: dict[str, Any] = {}
    for k in sealed_set[:3]:
        stages = by_key[k]
        missing = sorted(REQUIRED_STAGES_V1 - frozenset(stages.keys()))
        if missing:
            errors.append(f"{k!r}: missing stages: {missing}")
        nxs = stages.get("candle_timeframe_nexus_v1") or []
        if not any(
            str((r.get("evidence_payload") or {}).get("candle_timeframe_nexus") or "") == "student_packet"
            for r in nxs
        ):
            errors.append(f"{k!r}: missing candle_timeframe_nexus_v1 student_packet row")
        auth_rows = stages.get("student_decision_authority_v1") or []
        if not auth_rows:
            errors.append(f"{k!r}: no student_decision_authority_v1")
        else:
            pl = (auth_rows[-1].get("evidence_payload") or {}).get("student_decision_authority_v1") or {}
            if not isinstance(pl, dict):
                errors.append(f"{k!r}: authority evidence not a dict")
            else:
                ref = pl.get("referee_safety_check_v1")
                if not isinstance(ref, dict) or "passed_v1" not in ref:
                    errors.append(f"{k!r}: referee_safety_check_v1 missing or incomplete")
                if pl.get("decision_source_v1") != DECISION_SOURCE_REASONING_MODEL_V1:
                    errors.append(
                        f"{k!r}: trace payload decision_source_v1 expected {DECISION_SOURCE_REASONING_MODEL_V1!r} "
                        f"got {pl.get('decision_source_v1')!r}"
                    )
        mem = (stages.get("memory_retrieval_completed") or [{}])[-1]
        mev = mem.get("evidence_payload") if isinstance(mem.get("evidence_payload"), dict) else {}
        if "retrieved_lifecycle_learning_026c_slice_count_v1" not in mev:
            errors.append(f"{k!r}: memory_retrieval_completed missing retrieved_lifecycle_learning_026c_slice_count_v1")
        seal_rows = stages.get("student_output_sealed") or []
        if seal_rows:
            sev = seal_rows[-1].get("evidence_payload") if isinstance(seal_rows[-1].get("evidence_payload"), dict) else {}
            if sev.get("decision_source_v1") != DECISION_SOURCE_REASONING_MODEL_V1:
                errors.append(
                    f"{k!r}: student_output_sealed missing decision_source_v1="
                    f"{DECISION_SOURCE_REASONING_MODEL_V1!r}"
                )
        if k not in examples:
            examples[k] = {st: rows[-1] for st, rows in stages.items() if rows}

    return {
        "schema": "student_reasoning_model_trace_proof_v1",
        "job_id": jid,
        "sealed_trade_count_v1": len(sealed_set),
        "student_decision_authority_event_count_v1": auth_n,
        "counts_match_v1": len(sealed_set) == auth_n and len(sealed_set) > 0,
        "ok_v1": len(errors) == 0,
        "errors_v1": errors,
        "example_trace_rows_by_trade_v1": examples,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: student_reasoning_model_trace_proof_v1.py <job_id> [learning_trace_events_v1.jsonl]",
            file=sys.stderr,
        )
        return 2
    p = Path(argv[2]).expanduser().resolve() if len(argv) > 2 else default_learning_trace_events_jsonl()
    rep = validate_student_reasoning_model_trace_for_job_v1(argv[1], path=p)
    print(json.dumps(rep, indent=2, default=str))
    return 0 if rep.get("ok_v1") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
