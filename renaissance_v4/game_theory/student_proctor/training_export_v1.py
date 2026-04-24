"""
GT_DIRECTIVE_022 — Training readiness export: **promoted** learning rows only.

Read-only over ``student_learning_records_v1.jsonl`` + scorecard enrichment.
Does **not** train models, change LLM behavior, or alter 018 classification logic.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.exam_run_contract_v1 import (
    STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
)
from renaissance_v4.game_theory.pml_runtime_layout import pml_runtime_root
from renaissance_v4.game_theory.scorecard_drill import find_scorecard_entry_by_job_id
from renaissance_v4.game_theory.student_proctor.contracts_v1 import (
    CONTRACT_VERSION_STUDENT_PROCTOR_V1,
    validate_student_output_directional_thesis_required_for_llm_profile_v1,
    validate_student_output_v1,
)
from renaissance_v4.game_theory.student_proctor.learning_memory_promotion_v1 import (
    GOVERNANCE_PROMOTE,
    fingerprint_from_scorecard_entry_v1,
)
from renaissance_v4.game_theory.student_proctor.student_learning_store_v1 import (
    load_student_learning_records_v1,
)

SCHEMA_TRAINING_RECORD_V1 = "training_record_v1"
CONTRACT_VERSION_TRAINING_EXPORT_V1 = 1

MATERIALIZE_TRAINING_DATASET_CONFIRM_V1 = "MATERIALIZE_TRAINING_DATASET_V1"


def default_training_dataset_jsonl_path_v1() -> Path:
    """
    Default: ``<pml_runtime_root>/student_learning/training_dataset_v1.jsonl``.

    Override: ``PATTERN_GAME_TRAINING_DATASET_V1`` — absolute or repo-relative ``*.jsonl``.
    """
    override = (os.environ.get("PATTERN_GAME_TRAINING_DATASET_V1") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    root = pml_runtime_root() / "student_learning"
    root.mkdir(parents=True, exist_ok=True)
    return root / "training_dataset_v1.jsonl"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_status_done_v1(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    st = str(entry.get("status") or "").strip().lower()
    return st == "done"


def _brain_profile_from_scorecard_v1(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(
        entry.get("student_brain_profile_v1") or entry.get("student_reasoning_mode") or ""
    ).strip()


def _llm_model_from_scorecard_v1(entry: dict[str, Any] | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    llm = entry.get("student_llm_v1")
    if isinstance(llm, dict):
        m = str(llm.get("llm_model") or "").strip()
        return m or None
    return None


def _directional_thesis_subset_v1(so: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "student_action_v1",
        "confidence_band",
        "supporting_indicators",
        "conflicting_indicators",
        "context_fit",
        "invalidation_text",
    )
    return {k: so.get(k) for k in keys if k in so}


def learning_row_eligible_for_training_export_v1(
    row: dict[str, Any],
    *,
    scorecard_entry: dict[str, Any] | None,
) -> tuple[bool, str]:
    """
    Eligibility for **training_record_v1** (GT_DIRECTIVE_022).

    Promote-only; run ``status == done`` on scorecard; full thesis for LLM profile.
    ``promote`` from 018 already excluded critical L3 reject paths at classification time.
    """
    if not isinstance(row, dict):
        return False, "not_dict"
    lg = row.get("learning_governance_v1")
    if not isinstance(lg, dict):
        return False, "missing_learning_governance_v1"
    if str(lg.get("decision") or "").strip().lower() != GOVERNANCE_PROMOTE:
        return False, "not_promote"
    if not _run_status_done_v1(scorecard_entry):
        return False, "run_not_done_or_missing_scorecard"
    so = row.get("student_output")
    if not isinstance(so, dict):
        return False, "missing_student_output"
    if validate_student_output_v1(so):
        return False, "student_output_invalid"
    prof = _brain_profile_from_scorecard_v1(scorecard_entry)
    if prof == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        if validate_student_output_directional_thesis_required_for_llm_profile_v1(so):
            return False, "thesis_incomplete_for_llm_profile"
    return True, ""


def build_training_record_v1(
    row: dict[str, Any],
    *,
    scorecard_entry: dict[str, Any] | None,
    exported_at_utc: str | None = None,
) -> dict[str, Any] | None:
    """One ``training_record_v1`` dict, or ``None`` if ineligible."""
    ok, _why = learning_row_eligible_for_training_export_v1(row, scorecard_entry=scorecard_entry)
    if not ok:
        return None
    lg = row.get("learning_governance_v1")
    if not isinstance(lg, dict):
        return None
    so = row["student_output"]
    assert isinstance(so, dict)
    raw_fp = str(lg.get("fingerprint") or "").strip() or fingerprint_from_scorecard_entry_v1(
        scorecard_entry
    )
    fp = str(raw_fp or "")
    prof = _brain_profile_from_scorecard_v1(scorecard_entry)
    llm_model = _llm_model_from_scorecard_v1(scorecard_entry)
    entry = scorecard_entry if isinstance(scorecard_entry, dict) else {}
    outcome_summary: dict[str, Any] = {
        "exam_e_score_v1": entry.get("exam_e_score_v1"),
        "exam_p_score_v1": entry.get("exam_p_score_v1"),
        "exam_pass_v1": entry.get("exam_pass_v1"),
        "expectancy_per_trade": entry.get("expectancy_per_trade"),
    }
    optional: dict[str, Any] = {}
    mpc = row.get("memory_promotion_context_v1")
    if isinstance(mpc, dict):
        ids: list[str] = []
        for k in ("thesis_fields_present_v1",):
            v = mpc.get(k)
            if isinstance(v, list):
                ids.extend(str(x) for x in v if x is not None)
        if ids:
            optional["memory_promotion_context_keys_v1"] = sorted(set(ids))
    out: dict[str, Any] = {
        "schema": SCHEMA_TRAINING_RECORD_V1,
        "contract_version": CONTRACT_VERSION_TRAINING_EXPORT_V1,
        "student_proctor_contract_version": CONTRACT_VERSION_STUDENT_PROCTOR_V1,
        "source_learning_record_id": str(row.get("record_id") or "").strip(),
        "run_id": str(row.get("run_id") or "").strip(),
        "graded_unit_id": str(row.get("graded_unit_id") or "").strip(),
        "created_utc": str(row.get("created_utc") or "").strip(),
        "exported_at_utc": exported_at_utc or _utc_iso(),
        "fingerprint_sha256_40": fp,
        "student_brain_profile_v1": prof,
        "llm_model": llm_model,
        "student_output_v1": so,
        "directional_thesis_v1": _directional_thesis_subset_v1(so),
        "outcome_summary_v1": outcome_summary,
        "promotion_decision": GOVERNANCE_PROMOTE,
        "learning_governance_v1": dict(lg),
    }
    if optional:
        out["optional_enrichment_v1"] = optional
    return out


def _sort_key_training_source_row_v1(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("run_id") or "").strip(),
        str(row.get("graded_unit_id") or "").strip(),
        str(row.get("record_id") or "").strip(),
    )


def build_training_export_payload_v1(
    *,
    store_path: Path | str,
    scorecard_path: Path | None = None,
    preview_limit: int = 5,
) -> dict[str, Any]:
    """
    Deterministic export summary + preview.

    ``preview_limit`` clamped to ``0..500``.
    """
    lim = max(0, min(500, int(preview_limit)))
    rows = load_student_learning_records_v1(store_path)
    rows_sorted = sorted(rows, key=_sort_key_training_source_row_v1)
    stats: dict[str, int] = {
        "store_rows_valid": len(rows_sorted),
        "eligible_promote_done_thesis": 0,
        "filtered_not_promote": 0,
        "filtered_missing_governance": 0,
        "filtered_run_not_done": 0,
        "filtered_thesis_incomplete": 0,
        "filtered_student_output_invalid": 0,
    }
    eligible: list[dict[str, Any]] = []
    exported_at = _utc_iso()
    for row in rows_sorted:
        jid = str(row.get("run_id") or "").strip()
        sc = find_scorecard_entry_by_job_id(jid, path=scorecard_path) if jid else None
        ok, why = learning_row_eligible_for_training_export_v1(row, scorecard_entry=sc)
        if ok:
            tr = build_training_record_v1(row, scorecard_entry=sc, exported_at_utc=exported_at)
            if tr is not None:
                stats["eligible_promote_done_thesis"] += 1
                eligible.append(tr)
            continue
        if why == "missing_learning_governance_v1":
            stats["filtered_missing_governance"] += 1
        elif why == "not_promote":
            stats["filtered_not_promote"] += 1
        elif why == "run_not_done_or_missing_scorecard":
            stats["filtered_run_not_done"] += 1
        elif why == "thesis_incomplete_for_llm_profile":
            stats["filtered_thesis_incomplete"] += 1
        elif why in ("missing_student_output", "student_output_invalid"):
            stats["filtered_student_output_invalid"] += 1
        else:
            stats["filtered_student_output_invalid"] += 1
    preview = eligible[:lim] if lim else []
    return {
        "ok": True,
        "schema": "training_export_response_v1",
        "eligible_count": len(eligible),
        "preview_limit": lim,
        "preview": preview,
        "filter_stats_v1": stats,
        "training_record_schema": SCHEMA_TRAINING_RECORD_V1,
        "default_materialize_path": str(default_training_dataset_jsonl_path_v1()),
    }


def iter_training_record_lines_v1(
    *,
    store_path: Path | str,
    scorecard_path: Path | None = None,
    exported_at_utc: str | None = None,
) -> list[str]:
    """NDJSON lines, sorted deterministically (same inputs → same bytes)."""
    rows = load_student_learning_records_v1(store_path)
    rows_sorted = sorted(rows, key=_sort_key_training_source_row_v1)
    ts = exported_at_utc or _utc_iso()
    lines: list[str] = []
    for row in rows_sorted:
        jid = str(row.get("run_id") or "").strip()
        sc = find_scorecard_entry_by_job_id(jid, path=scorecard_path) if jid else None
        tr = build_training_record_v1(row, scorecard_entry=sc, exported_at_utc=ts)
        if tr is not None:
            lines.append(json.dumps(tr, separators=(",", ":"), ensure_ascii=False, sort_keys=True))
    return lines


def materialize_training_dataset_v1(
    *,
    store_path: Path | str,
    scorecard_path: Path | None = None,
    output_path: Path | str | None = None,
    confirm: str | None = None,
) -> dict[str, Any]:
    """
    Write ``training_dataset_v1.jsonl`` (overwrite atomically).

    ``confirm`` must equal ``MATERIALIZE_TRAINING_DATASET_CONFIRM_V1``.
    """
    if str(confirm or "").strip() != MATERIALIZE_TRAINING_DATASET_CONFIRM_V1:
        return {
            "ok": False,
            "error": "confirm must match MATERIALIZE_TRAINING_DATASET_CONFIRM_V1",
        }
    out_p = Path(str(output_path)) if output_path else default_training_dataset_jsonl_path_v1()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    batch_ts = _utc_iso()
    lines = iter_training_record_lines_v1(
        store_path=store_path,
        scorecard_path=scorecard_path,
        exported_at_utc=batch_ts,
    )
    body = "\n".join(lines) + ("\n" if lines else "")
    tmp = out_p.with_suffix(out_p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(out_p)
    return {
        "ok": True,
        "path": str(out_p.resolve()),
        "line_count": len(lines),
        "bytes_written": len(body.encode("utf-8")),
    }


__all__ = [
    "CONTRACT_VERSION_TRAINING_EXPORT_V1",
    "MATERIALIZE_TRAINING_DATASET_CONFIRM_V1",
    "SCHEMA_TRAINING_RECORD_V1",
    "build_training_export_payload_v1",
    "build_training_record_v1",
    "default_training_dataset_jsonl_path_v1",
    "iter_training_record_lines_v1",
    "learning_row_eligible_for_training_export_v1",
    "materialize_training_dataset_v1",
]
