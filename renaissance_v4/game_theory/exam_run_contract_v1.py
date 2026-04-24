"""
GT_DIRECTIVE_015 — exam run contract: **Student brain profile**, nested LLM metadata, scorecard fields.

**Student brain profile** (primary): ``baseline_no_memory_no_llm`` | ``memory_context_student`` |
``memory_context_llm_student``. Legacy ``student_reasoning_mode`` **input** strings (cold baseline,
repeat Anna, Qwen/DeepSeek lane labels) are still accepted and normalized to a profile.

**LLM** is metadata under the ``memory_context_llm_student`` profile: ``student_llm_v1`` with
``llm_provider``, ``llm_model``, ``llm_role``. Model choice is **secondary** to the profile
(primary question: does memory + context + governed LLM reasoning improve under the Referee?).

Parallel replay **still executes** for every batch in v1; ``skip_cold_baseline`` records whether a
**prior comparable baseline** existed (comparison validity), not a physical skip of Referee work.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.batch_scorecard import read_batch_scorecard_recent

# --- Canonical Student brain profiles (GT_DIRECTIVE_015 v2) ---

STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 = "baseline_no_memory_no_llm"
STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1 = "memory_context_student"
STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1 = "memory_context_llm_student"

CANONICAL_STUDENT_BRAIN_PROFILES_V1: frozenset[str] = frozenset(
    {
        STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
        STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    }
)

# Legacy **input** tokens (UI/API/scripts). Normalize maps these → brain profile.
LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1 = "cold_baseline"
LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1 = "repeat_anna_memory_context"
LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1 = "memory_context_only"
LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1 = "llm_assisted_anna_qwen"
LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1 = "llm_qwen2_5_7b"
LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1 = "llm_assisted_anna_deepseek_r1_14b"
LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1 = "llm_deepseek_r1_14b"

LEGACY_STUDENT_REASONING_INPUTS_V1: frozenset[str] = frozenset(
    {
        LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1,
        LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1,
        LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1,
        LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1,
    }
)

# Back-compat names for imports (values are legacy **inputs**, not persisted profile ids).
STUDENT_REASONING_MODE_COLD_BASELINE_V1 = LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1
STUDENT_REASONING_MODE_REPEAT_ANNA_V1 = LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1
STUDENT_REASONING_MODE_LLM_QWEN_V1 = LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1
STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1 = LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1

STUDENT_REASONING_MODES_V1: frozenset[str] = frozenset(
    CANONICAL_STUDENT_BRAIN_PROFILES_V1 | LEGACY_STUDENT_REASONING_INPUTS_V1
)

_LEGACY_INPUT_TO_PROFILE_V1: dict[str, str] = {
    LEGACY_STUDENT_REASONING_INPUT_COLD_BASELINE_V1: STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1,
    LEGACY_STUDENT_REASONING_INPUT_REPEAT_ANNA_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_MEMORY_CONTEXT_ONLY_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
    LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1: STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1,
}

_DEFAULT_LLM_ROLE_V1 = "single_shot_student_output_v1"
_DEFAULT_LLM_PROVIDER_V1 = "ollama"
_DEFAULT_LLM_MODEL_WHEN_OMITTED_V1 = "qwen2.5:7b"

_LLM_HINT_FROM_LEGACY_INPUT_V1: dict[str, str] = {
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_V1: "qwen2.5:7b",
    LEGACY_STUDENT_REASONING_INPUT_LLM_QWEN_ALIAS_V1: "qwen2.5:7b",
    LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_V1: "deepseek-r1:14b",
    LEGACY_STUDENT_REASONING_INPUT_LLM_DEEPSEEK_ALIAS_V1: "deepseek-r1:14b",
}


def default_ollama_base_url_v1() -> str:
    """Student parallel LLM — same routing chain as PML lightweight (``172.20.2.230`` lab default)."""
    from renaissance_v4.game_theory.ollama_role_routing_v1 import student_ollama_base_url_v1

    return student_ollama_base_url_v1()


def normalize_student_reasoning_mode_v1(raw: str | None) -> str:
    """
    Return canonical **Student brain profile** id.

    Legacy ``student_reasoning_mode`` **lane** strings (Qwen vs DeepSeek labels) still map here;
    use ``student_llm_v1.llm_model`` (and scorecard ``llm_model``) for model-level attribution.
    """
    s = (raw or "").strip()
    if not s:
        return STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1
    if s in CANONICAL_STUDENT_BRAIN_PROFILES_V1:
        return s
    if s in _LEGACY_INPUT_TO_PROFILE_V1:
        return _LEGACY_INPUT_TO_PROFILE_V1[s]
    return s


def validate_student_reasoning_mode_v1(mode: str | None) -> str | None:
    """Return error message if input is unknown (legacy lane string or brain profile)."""
    s = (mode or "").strip()
    if not s:
        return None
    if s in CANONICAL_STUDENT_BRAIN_PROFILES_V1 or s in LEGACY_STUDENT_REASONING_INPUTS_V1:
        return None
    return f"unknown student_reasoning_mode or student_brain_profile_v1: {mode!r}"


def _infer_llm_model_from_legacy_reasoning_input_v1(raw: str | None) -> str | None:
    s = (raw or "").strip()
    return _LLM_HINT_FROM_LEGACY_INPUT_V1.get(s)


def _normalize_student_llm_block_v1(
    block: dict[str, Any],
    *,
    profile: str,
    legacy_reasoning_input: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Returns ``(student_llm_v1_dict, error)``."""
    if profile != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return {}, None
    raw = block.get("student_llm_v1")
    slm: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    model = str(slm.get("llm_model") or "").strip()
    if not model:
        hint = _infer_llm_model_from_legacy_reasoning_input_v1(legacy_reasoning_input)
        if hint:
            model = hint
        else:
            model = _DEFAULT_LLM_MODEL_WHEN_OMITTED_V1
    if len(model) > 128:
        return None, "llm_model too long"
    provider = str(slm.get("llm_provider") or _DEFAULT_LLM_PROVIDER_V1).strip().lower() or _DEFAULT_LLM_PROVIDER_V1
    if provider != "ollama":
        return None, "llm_provider must be ollama in v1"
    role = str(slm.get("llm_role") or _DEFAULT_LLM_ROLE_V1).strip() or _DEFAULT_LLM_ROLE_V1
    if len(role) > 128:
        return None, "llm_role too long"
    return {
        "schema": "student_llm_v1",
        "llm_provider": provider,
        "llm_model": model,
        "llm_role": role,
    }, None


def resolved_llm_for_exam_contract_v1(req: dict[str, Any] | None) -> tuple[str | None, str, dict[str, Any]]:
    """
    For ``memory_context_llm_student``: Ollama model tag, base URL, and normalized ``student_llm_v1`` echo.
    Otherwise: ``(None, default_url, {})``.
    """
    r = dict(req or {})
    prof = normalize_student_reasoning_mode_v1(
        str(r.get("student_brain_profile_v1") or r.get("student_reasoning_mode") or "")
    )
    if prof != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return None, default_ollama_base_url_v1(), {}
    slm = r.get("student_llm_v1")
    if not isinstance(slm, dict):
        slm = {}
    model = str(slm.get("llm_model") or "").strip() or _DEFAULT_LLM_MODEL_WHEN_OMITTED_V1
    out_slm = {
        "schema": "student_llm_v1",
        "llm_provider": str(slm.get("llm_provider") or _DEFAULT_LLM_PROVIDER_V1).strip().lower()
        or _DEFAULT_LLM_PROVIDER_V1,
        "llm_model": model,
        "llm_role": str(slm.get("llm_role") or _DEFAULT_LLM_ROLE_V1).strip() or _DEFAULT_LLM_ROLE_V1,
    }
    return model, default_ollama_base_url_v1(), out_slm


def resolved_llm_model_and_url_for_student_mode_v1(mode: str) -> tuple[str | None, str]:
    """Backward-compat shim: treat legacy **lane** string as hint for model under LLM profile."""
    m = normalize_student_reasoning_mode_v1(mode)
    if m != STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        return None, default_ollama_base_url_v1()
    hint = _infer_llm_model_from_legacy_reasoning_input_v1(mode)
    model = hint or _DEFAULT_LLM_MODEL_WHEN_OMITTED_V1
    return model, default_ollama_base_url_v1()


def preview_run_config_fingerprint_sha256_40_v1(
    scenarios: list[dict[str, Any]],
    operator_batch_audit: dict[str, Any],
) -> str:
    oba = operator_batch_audit or {}
    ok_rows = [x for x in scenarios if isinstance(x, dict)]
    fp_parts = [
        str(oba.get("operator_recipe_id") or ""),
        str(oba.get("evaluation_window_effective_calendar_months") or ""),
        str(oba.get("candle_timeframe_minutes") or ""),
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
    Parse ``exam_run_contract_v1`` (or flat keys). Primary: ``student_brain_profile_v1``;
    ``student_reasoning_mode`` is accepted as legacy **or** mirror of profile.
    """
    src = data.get("exam_run_contract_v1")
    if isinstance(src, dict):
        block = dict(src)
    else:
        block = {}
    if data.get("student_brain_profile_v1") is not None:
        block["student_brain_profile_v1"] = data.get("student_brain_profile_v1")
    if data.get("student_reasoning_mode") is not None:
        block["student_reasoning_mode"] = data.get("student_reasoning_mode")
    if data.get("student_llm_v1") is not None:
        block["student_llm_v1"] = data.get("student_llm_v1")
    if data.get("skip_cold_baseline_if_anchor") is not None:
        block["skip_cold_baseline_if_anchor"] = data.get("skip_cold_baseline_if_anchor")
    if data.get("prompt_version") is not None:
        block["prompt_version"] = data.get("prompt_version")
    if data.get("retrieved_context_ids") is not None:
        block["retrieved_context_ids"] = data.get("retrieved_context_ids")

    raw_profile = block.get("student_brain_profile_v1")
    raw_mode = block.get("student_reasoning_mode")
    pick = raw_profile if isinstance(raw_profile, str) and raw_profile.strip() else raw_mode
    err = validate_student_reasoning_mode_v1(pick if isinstance(pick, str) else None)
    if err:
        return None, err
    profile = normalize_student_reasoning_mode_v1(pick if isinstance(pick, str) else None)
    legacy_input = (
        str(raw_mode).strip()
        if isinstance(raw_mode, str) and raw_mode.strip() in LEGACY_STUDENT_REASONING_INPUTS_V1
        else None
    )
    slm, slm_err = _normalize_student_llm_block_v1(block, profile=profile, legacy_reasoning_input=legacy_input)
    if slm_err:
        return None, slm_err

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

    if profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1:
        base = default_ollama_base_url_v1()
        if not base or not (base.startswith("http://") or base.startswith("https://")):
            return None, "ollama_base_url_invalid_or_unset_for_llm_assisted_mode"

    out: dict[str, Any] = {
        "schema": "exam_run_contract_request_v1",
        "contract_version": 1,
        "student_brain_profile_v1": profile,
        "student_reasoning_mode": profile,
        "student_llm_v1": slm,
        "skip_cold_baseline_if_anchor": skip_req,
        "prompt_version": pv,
        "retrieved_context_ids": rcids_out,
    }
    euid = block.get("exam_unit_id")
    if euid is None and isinstance(data.get("exam_unit_id"), str):
        euid = data.get("exam_unit_id")
    if isinstance(euid, str) and euid.strip():
        out["exam_unit_id"] = euid.strip()[:256]
    return out, None


def build_exam_run_line_meta_v1(
    *,
    request: dict[str, Any] | None,
    operator_batch_audit: dict[str, Any] | None,
    fingerprint_sha256_40: str | None,
    job_id: str,
    student_seam_observability_v1: dict[str, Any] | None,
    batch_status: str,
    seam_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    req = request or {}
    profile = normalize_student_reasoning_mode_v1(
        str(req.get("student_brain_profile_v1") or req.get("student_reasoning_mode") or "")
    )
    seam = student_seam_observability_v1 or {}
    oba = operator_batch_audit or {}

    llm_used = profile == STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1
    slm_req = req.get("student_llm_v1") if isinstance(req.get("student_llm_v1"), dict) else {}
    llm_model: str | None = str(slm_req.get("llm_model") or "").strip() or None if llm_used else None
    ollama_url = default_ollama_base_url_v1() if llm_used else None

    fp = (fingerprint_sha256_40 or "").strip()
    anchor = find_prior_baseline_job_id_for_fingerprint_v1(fp) if fp else None
    skip_req = bool(req.get("skip_cold_baseline_if_anchor"))
    skip_applicable = (
        skip_req
        and profile != STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1
        and fp
        and anchor is not None
        and batch_status == "done"
    )
    if profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1:
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
        "student_brain_profile_v1": profile,
        "student_reasoning_mode": profile,
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
            profile == STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1 and batch_status == "done"
        ),
    }
    if llm_used and isinstance(req.get("student_llm_v1"), dict):
        line["student_llm_v1"] = dict(req["student_llm_v1"])
    shadow_on = bool(seam.get("shadow_student_enabled"))
    if shadow_on is not None:
        line["shadow_student_enabled_echo_v1"] = shadow_on
    _ = job_id

    sa = seam_audit if isinstance(seam_audit, dict) else {}
    lx = sa.get("student_llm_execution_v1")
    if isinstance(lx, dict) and lx.get("schema") == "student_llm_execution_v1":
        line["student_llm_execution_v1"] = lx
        if lx.get("ollama_any_attempt") is True:
            line["llm_used"] = True
        if isinstance(lx.get("model_resolved"), str) and lx["model_resolved"].strip():
            line["llm_model"] = lx["model_resolved"].strip()
        if isinstance(lx.get("base_url_resolved"), str) and lx["base_url_resolved"].strip():
            line["ollama_base_url"] = lx["base_url_resolved"].strip()
        if isinstance(lx.get("prompt_version_resolved"), str) and lx["prompt_version_resolved"].strip():
            line["prompt_version"] = lx["prompt_version_resolved"].strip()[:256]
        if isinstance(lx.get("student_brain_profile_echo_v1"), str) and lx["student_brain_profile_echo_v1"].strip():
            line["student_brain_profile_v1"] = lx["student_brain_profile_echo_v1"].strip()
            line["student_reasoning_mode"] = line["student_brain_profile_v1"]
    eid = req.get("exam_unit_id")
    if isinstance(eid, str) and eid.strip():
        line["exam_unit_id"] = eid.strip()[:256]
    return line


__all__ = [
    "STUDENT_REASONING_MODES_V1",
    "STUDENT_REASONING_MODE_COLD_BASELINE_V1",
    "STUDENT_REASONING_MODE_REPEAT_ANNA_V1",
    "STUDENT_REASONING_MODE_LLM_QWEN_V1",
    "STUDENT_REASONING_MODE_LLM_DEEPSEEK_V1",
    "STUDENT_BRAIN_PROFILE_BASELINE_NO_MEMORY_NO_LLM_V1",
    "STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_STUDENT_V1",
    "STUDENT_BRAIN_PROFILE_MEMORY_CONTEXT_LLM_STUDENT_V1",
    "CANONICAL_STUDENT_BRAIN_PROFILES_V1",
    "LEGACY_STUDENT_REASONING_INPUTS_V1",
    "build_exam_run_line_meta_v1",
    "default_ollama_base_url_v1",
    "find_prior_baseline_job_id_for_fingerprint_v1",
    "normalize_student_reasoning_mode_v1",
    "parse_exam_run_contract_request_v1",
    "preview_run_config_fingerprint_sha256_40_v1",
    "resolved_llm_for_exam_contract_v1",
    "resolved_llm_model_and_url_for_student_mode_v1",
    "validate_student_reasoning_mode_v1",
]
