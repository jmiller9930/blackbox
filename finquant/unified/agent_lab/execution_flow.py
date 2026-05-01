"""
FinQuant Unified Agent Lab — shared execution flow.

Used by both the single-case runner and the multi-run training cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def execute_case(
    *,
    case_path: str,
    config: dict[str, Any],
    output_dir: str,
) -> dict[str, Any]:
    from case_loader import load_case
    from lifecycle_engine import LifecycleEngine
    from evaluation import evaluate_lifecycle
    from memory_store import MemoryStore
    from retrieval import retrieve_eligible

    case = load_case(case_path)
    store = MemoryStore(config=config, base_output_dir=output_dir)

    prior_records, retrieval_trace = retrieve_eligible(
        shared_store_path=config.get("memory_store_path"),
        case=case,
        config=config,
    )
    store.append_retrieval_trace(retrieval_trace)

    engine = LifecycleEngine(config=config)
    decisions = engine.run_case(case, prior_records=prior_records)
    store.append_decisions(decisions)

    evaluation = evaluate_lifecycle(case=case, decisions=decisions)
    record = store.write_learning_record(case=case, evaluation=evaluation)
    run_id = store.finalize(case=case, evaluation=evaluation)
    run_dir = store.get_run_dir()

    return {
        "case": case,
        "case_path": case_path,
        "config": dict(config),
        "decisions": decisions,
        "evaluation": evaluation,
        "learning_record": record,
        "retrieval_trace": retrieval_trace,
        "prior_records": prior_records,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "shared_store_path": str(store.get_shared_store_path()) if store.get_shared_store_path() else None,
    }
