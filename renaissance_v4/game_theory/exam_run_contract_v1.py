"""
GT_DIRECTIVE_015 — exam run contract: reasoning modes, scorecard metadata, skip-cold audit.

Parallel replay **still executes** for every batch in v1; ``skip_cold_baseline`` records whether a
**prior comparable baseline** existed (apples-to-apples comparison validity), not a physical skip
of the Referee engine (two-phase cold vs Anna split is future work).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent

# Canonical modes (engineering brief + legacy aliases in normalize).
STUDENT_REASONING_MODE_COLD_BASELINE_V1 = "cold_baseline"
STUDENT_REASONING_MODE_REPEAT_ANNA_V1 = "repeat_anna_memory_context"
STUDENT_REASONING_MODE_LLM_QWEN_V1 = "llm_assisted_anna_qwen"
STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1 = "llm_assisted_anna_deepseek_r1_14b"

CANONICAL_STUDENT_REASONING_MODES_V1: frozenset[str] = frozenset(
    {
        STUDENT_REASONING_MODE_COLD_BASELINE_V1,
        STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
        STUDENT_REASONING_MODE_LLM_QWEN_V1,
        STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1,
    }
)

# Includes legacy input tokens accepted by ``normalize_student_reasoning_mode_v1``.
STUDENT_REASONING_MODES_V1: frozenset[str] = frozenset(
    CANONICAL_STUDENT_REASONING_MODES_V1
    | {
        "memory_context_only",
        "llm_qwen2_5_7b",
        "llm_deepseek_r1_14b",
    }
)

_MODE_ALIASES_V1: dict[str, str] = {
    "memory_context_only": STUDENT_REASONING_MODE_REPEAT_ANNA_V1,
    "llm_qwen2_5_7b": STUDENT_REASONING_MODE_LLM_QWEN_V1,
    "llm_deepseek_r1_14b": STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1,
}

_LLM_BINDING_V1: dict[str, dict[str, Any]] = {
    STUDENT_REASONING_MODE_LLM_QWEN_V1: {
        "llm_used": True,
        "llm_model": "qwen2.5:7b",
    },
    STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1: {
        "llm_used": True,
        "llm_model": "deepseek-r1:14b",
    },
}


def default_ollama_base_url_v1() -> str:
    return (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/")


def normalize_student_reasoning_mode_v1(raw: str | None) -> str:
    """Return canonical mode id; default matches historical “Anna repeat + Student seam” runs."""
    s = (raw or "").strip()
    if not s:
        return STUDENT_REASONING_MODE_REPEAT_ANNA_V1
    if s in _MODE_ALIASES_V1:
        return _MODE_ALIASES_V1[s]
    if s in CANONICAL_STUDENT_REASONING_MODES_V1:
        return s
    return s  # unknown token — ``validate`` rejects unless added to aliases


def validate_student_reasoning_mode_v1(mode: str | None) -> str | None:
    """Return error message if mode is unknown (after normalization)."""
    m = normalize_student_reasoning_mode_v1(mode if isinstance(mode, str) else None)
    if m not in CANONICAL_STUDENT_REASONING_MODES_V1:
        return f"unknown student_reasoning_mode: {mode!r}"
    return None


def preview_run_config_fingerprint_sha256_40_v1(
    scenarios: list[dict[str, Any]],
    operator_batch_audit: dict[str, Any],
) -> str:
    """
    Same recipe as ``build_memory_context_impact_audit_v1`` fingerprint (ok_rows ordering),
    using submitted scenarios so the UI can detect anchors **before** workers return.
    """
    oba = operator_batch_audit or {}
    ok_rows = [x for x in scenarios if isinstance(x, dict)]
    fp_parts = [
        str(oba.get("operator_recipe_id") or ""),
        str(oba.get("evaluation_window_effective_calendar_months") or ""),
        str(oba.get("manifest_path_primary") or ""),
        str(oba.get("policy_framework_path") or ""),
    ]
    for r in sorted(ok_rows, key=lambda x: str(x.get("scenario_id") or "")):
        fp_parts.append(str(r.get("scenario_id") or ""))
        mp = r.get("manifest_path")
        if mp:
            fp_parts.append(str(mp))
    return hashlib.sha256("\n".join(fp_parts).encode("utf-8")).hexdigest()[:40]


def find_prior_baseline_job_id_for_fingerprint_v1(
    fp: str,
    *,
    scorecard_path: Path | None = None,
    limit: int = 800,
) -> str | None:
    """
    Oldest completed scorecard line with the same fingerprint (Sys BL anchor semantics).

    ``student_reasoning_mode`` absent on legacy rows counts as a baseline-capable anchor.
    """
    if not fp:
        return None
    rows = read_batch_scorecard_recent(limit, path=scorecard_path)
    chronological = list(reversed(rows))
    oldest: str | None = None
    for r in chronological:
        if str(r.get("status") or "") != "done":
            continue
        mci = r.get("memory_context_impact_audit_v1")
        if not isinstance(mci, dict):
            continue
        rfp = str(mci.get("run_config_fingerprint_sha256_40") or "").strip()
        if rfp != fp:
            continue
        jid = str(r.get("job_id") or "").strip()
        if not jid:
            continue
        oldest = jid
        break
    return oldest


def _memory_context_used_flag_v1(operator_batch_audit: dict[str, Any] | None) -> bool:
    oba = operator_batch_audit or {}
    cmem = str(oba.get("context_signature_memory_mode") or "").strip().lower()
    return cmem in ("read", "read_write")


def parse_exam_run_contract_request_v1(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """
    Parse optional ``exam_run_contract_v1`` (or flat keys) from POST /api/run-parallel body.

    Returns ``(request_dict, error)``.
    """
    src = data.get("exam_run_contract_v1")
    if isinstance(src, dict):
        block = dict(src)
    else:
        block = {}
    # Flat overrides (convenience for scripts)
    if data.get("student_reasoning_mode") is not None:
        block["student_reasoning_mode"] = data.get("student_reasoning_mode")
    if data.get("skip_cold_baseline_if_anchor") is not None:
        block["skip_cold_baseline_if_anchor"] = data.get("skip_cold_baseline_if_anchor")
    if data.get("prompt_version") is not None:
        block["prompt_version"] = data.get("prompt_version")
    if data.get("retrieved_context_ids") is not None:
        block["retrieved_context_ids"] = data.get("retrieved_context_ids")

    mode_raw = block.get("student_reasoning_mode")
    err = validate_student_reasoning_mode_v1(mode_raw if isinstance(mode_raw, str) else None)
    if err:
        return None, err
    mode = normalize_student_reasoning_mode_v1(mode_raw if isinstance(mode_raw, str) else None)

    skip_req = block.get("skip_cold_baseline_if_anchor")
    if isinstance(skip_req, str):
        skip_req = skip_req.strip().lower() in ("1", "true", "yes", "on")
    skip_req = bool(skip_req)

    pv = block.get("prompt_version")
    if pv is None or str(pv).strip() == "":
        pv = "shadow_student_stub_v1"
    else:
        pv = str(pv).strip()[:256]

    rcids = block.get("retrieved_context_ids")
    if rcids is None:
        rcids_out: list[str] = []
    elif isinstance(rcids, list):
        rcids_out = [str(x).strip() for x in rcids if str(x).strip()][:128]
    else:
        return None, "retrieved_context_ids must be a list of strings when set"

    if mode in (STUDENT_REASONING_MODE_LLM_QWEN_V1, STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1):
        base = default_ollama_base_url_v1()
        if not base or not (base.startswith("http://") or base.startswith("https://")):
            return None, "ollama_base_url_invalid_or_unset_for_llm_assisted_mode"

    out = {
        "schema": "exam_run_contract_request_v1",
        "contract_version": 1,
        "student_reasoning_mode": mode,
        "skip_cold_baseline_if_anchor": skip_req,
        "prompt_version": pv,
        "retrieved_context_ids": rcids_out,
    }
    return out, None


def build_exam_run_line_meta_v1(
    *,
    request: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    fingerprint_sha256_40: str | None,
    job_id: str,
    student_seam_observability_v1: dict[str, Any] | None,
    batch_status: str,
) -> dict[str, Any]:
    """
    Fields merged onto ``pattern_game_batch_scorecard_v1`` (top-level) for GT_DIRECTIVE_015.

    ``fingerprint_sha256_40`` should be post-run MCI fingerprint when available; else preview.
    """
    req = request or {}
    mode = normalize_student_reasoning_mode_v1(str(req.get("student_reasoning_mode") or ""))
    seam = student_seam_observability_v1 or {}
    oba = operator_batch_audit or {}

    llm_used = False
    llm_model: str | None = None
    if mode in _LLM_BINDING_V1:
        llm_used = bool(_LLM_BINDING_V1[mode]["llm_used"])
        llm_model = str(_LLM_BINDING_V1[mode]["llm_model"])
    # Student path today is stub unless LLM mode selected (explicit contract for future wire-up).
    shadow_on = bool(seam.get("shadow_student_enabled"))
    if mode in (STUDENT_REASONING_MODE_LLM_QWEN_V1, STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1):
        llm_note = "llm_mode_declared_student_stub_until_ollama_wired"
    else:
        llm_note = None

    ollama_url = default_ollama_base_url_v1() if llm_used else None

    fp = (fingerprint_sha256_40 or "").strip()
    anchor = find_prior_baseline_job_id_for_fingerprint_v1(fp) if fp else None
    # This job is not on disk yet; anchor may equal a prior run only.
    skip_req = bool(req.get("skip_cold_baseline_if_anchor"))
    skip_applicable = (
        skip_req
        and mode != STUDENT_REASONING_MODE_COLD_BASELINE_V1
        and fp
        and anchor is not None
        and batch_status == "done"
    )
    if mode == STUDENT_REASONING_MODE_COLD_BASELINE_V1:
        skip_cold = False
        skip_reason = "mode_is_cold_baseline"
    elif not skip_req:
        skip_cold = False
        skip_reason = "skip_not_requested"
    elif not fp:
        skip_cold = False
        skip_reason = "fingerprint_unavailable"
    elif anchor is None:
        skip_cold = False
        skip_reason = "cold_required_no_prior_anchor_same_fingerprint"
    elif not skip_applicable:
        skip_cold = False
        skip_reason = "skip_not_applicable_batch_not_done" if batch_status != "done" else "skip_not_applicable"
    else:
        skip_cold = True
        skip_reason = f"prior_anchor_job_id={anchor}"

    mem_ctx = _memory_context_used_flag_v1(oba)
    if seam.get("student_retrieval_matches"):
        mem_ctx = True

    line: dict[str, Any] = {
        "student_reasoning_mode": mode,
        "llm_used": llm_used,
        "llm_model": llm_model,
        "ollama_base_url": ollama_url,
        "prompt_version": str(req.get("prompt_version") or "shadow_student_stub_v1")[:256],
        "memory_context_used": mem_ctx,
        "retrieved_context_ids": list(req.get("retrieved_context_ids") or []),
        "skip_cold_baseline": skip_cold,
        "skip_reason": skip_reason,
        "cold_baseline_anchor_job_id_v1": anchor,
        "run_config_fingerprint_sha256_40_echo_v1": fp or None,
        "system_baseline_captured_v1": bool(
            mode == STUDENT_REASONING_MODE_COLD_BASELINE_V1 and batch_status == "done"
        ),
    }
    if llm_note:
        line["student_llm_contract_note_v1"] = llm_note
    if shadow_on is not None:
        line["shadow_student_enabled_echo_v1"] = shadow_on
    _ = job_id  # reserved for future self-exclusion in anchor scan
    return line


__all__ = [
    "STUDENT_REASONING_MODES_V1",
    "STUDENT_REASONING_MODE_COLD_BASELINE_V1",
    "STUDENT_REASONING_MODE_REPEAT_ANNA_V1",
    "STUDENT_REASONING_MODE_LLM_QWEN_V1",
    "STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1",
    "build_exam_run_line_meta_v1",
    "default_ollama_base_url_v1",
    "find_prior_baseline_job_id_for_fingerprint_v1",
    "normalize_student_reasoning_mode_v1",
    "parse_exam_run_contract_request_v1",
    "preview_run_config_fingerprint_sha256_40_v1",
    "validate_student_reasoning_mode_v1",
]
